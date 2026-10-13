# B → A：HybridPlanningAgent 实现与接线边界

当前分支更新（2026-10-13）：A16 已合 main；本分支新增模型修订与同版本重评，见 [最新交接](model_revision_reassessment_handoff.md)。以下 PLAN-only 和 trace 待接线描述保留为初版历史，不代表当前代码；新增审计关联语义待 A 复核。

日期：2026-10-13。此前 Coordinator 组件说明见 [campus_llm_handoff_to_a.md](campus_llm_handoff_to_a.md)。本文是 B 的实现交付说明，不表示 A 已确认 trace 保存接口或应用接线已经完成。

## 1. 本次实现

`backend/app/agents/hybrid_planning_agent.py` 实现共享 `AgentPort` 的六个方法：

| 方法 | 执行方式 |
| --- | --- |
| interpret_request | 原请求解释规则；保留显式字段、澄清与人工确认边界 |
| recommend_campsites | 原营地硬约束筛选与规则排序 |
| generate_or_revise_itinerary | 真正调用 CampusModelClient → PlanningCoordinator → 受控营地工具 → 输出校验 |
| assess_gear_and_logistics | 装备与费用确定性算法；整数分/Decimal，不交给模型算钱 |
| assess_safety | 确定性证据、风险与 blocker 检查；绑定同一保存版本的物流评估 |
| orchestrate | 原 Orchestrator + A RecoveryPort，不复制编排或另建数据库 |

运行模式从输入、推荐、行程到评估、RunResult 均为 `agent`。这是混合运行的身份，不表示每个步骤都是 LLM；规则输出的 assumptions 明确注明对应步骤不是 LLM。

没有先把输入改成 deterministic_demo 再改回标签。规则 kernel 新增显式内部 expected_mode 参数，默认仍为 deterministic_demo；原 RuleAgent 和默认行程校验仍拒绝 agent。新包装在校验 agent 上下文后直接调用 kernel。

模型规划失败、缺密钥、非法回复、配置不一致时没有规则/stub 回退，也不会保存冒充模型的版本。推荐无匹配时原编排可以结束为无方案，不会虚构模型调用。

## 2. 首版能力限制

- `supported_operations = frozenset({'PLAN'})`，仅首次 PLAN。
- REVISE / REASSESS 在调用持久化入口前明确拒绝；A 还需在 HTTP/UI 命令入口提前禁用，避免创建不支持的运行。
- 单营地覆盖全部确认晚数，最多 30 晚；保守 CAMP/rest 时间由 host 渲染，不声称模型生成了旅游活动、交通时间或预订。
- 模型不得修改已确认需求；预算超限、缺失证据、封路保持真实评估与最终化限制，不强制改成成功。
- 正常流程可得到 finalisation_available，但 B 不创建最终记录；人工审核、最终化权限仍由 A 管理。

## 3. A 应登记的配置与构造方式

公共 B 入口：

```python
from app.agents.hybrid_planning_agent import (
    HybridPlanningAgent, build_hybrid_configuration,
)

client = CampusModelClient(CampusModelSettings())
client.validate_configuration()  # 离线检查，不收费探测
dataset = SyntheticDatasetV2Adapter(settings.dataset_path).load(
    expected_context=descriptor.context,
)
coordinator = PlanningCoordinator(dataset, client)
base = descriptor.context.model_copy(update={
    'rules_version': descriptor.context.rules_version + '/a-runtime-bindings-v2',
})
configuration = build_hybrid_configuration(
    dataset, coordinator,
    safety_case_ids=settings.workflow_safety_case_ids,
    scenarios=configured_scenarios(settings, descriptor),
    registered_context=base,
)
agent = HybridPlanningAgent(
    dataset, coordinator, workflow_configuration=configuration,
    heartbeat_interval=20,  # A 必须保证小于 lease_seconds / 3
)
# A 工厂返回 AgentBinding(agent, configuration.context)。
# 必须先登记该 context，再保存确认和 start/claim；不能事后改旧 run。
```

以上为待 A 接线示意，不是已注册的应用工厂。本次没有修改 AgentRuntime、注册表、主应用 Settings、HTTP 或前端配置；现有默认 stub/v1、规则 v2 不变。不应把旧 RuleAgent binding 仅改模式标签。

`build_hybrid_configuration`：

- 完整保留 A 的 file_digests、fixture_digests、selection_config 和 rules_version 前缀。
- 追加 hybrid_agent_version、hybrid_kernel_version、hybrid_planning_fingerprint 三个选用身份字段，以及规则身份后缀。
- 指纹来自 Coordinator 的 Prompt、输出 schema、工具/校验版本与模型客户端公开配置；不含密钥。轮换密钥不会改变运行语义身份。
- 与已登记身份冲突时拒绝；Coordinator 必须持有同一个已加载 dataset 对象。
- 费用/装备天气选择直接使用 configuration 中登记的 safety_case_ids，不依赖另行修改 dataset 的可变选择属性。
- 更改模型公开配置、Prompt 或工具校验身份后，旧 run 不得复用旧写入 key 重算；模型等待期间身份漂移也会在返回保存前拒绝。

## 4. 恢复与 heartbeat

仍调用原 Orchestrator，要求 A 提供已有 load_checkpoint() / heartbeat() 扩展。共享契约 1.0 不修改。

- 先读取 checkpoint，再核对确认、scope、配置、模式和保存产物的关联。
- 保存版本存在：跳过模型规划，继续缺失物流/安全/路由；不是重新生成后拿旧 key 写入。
- 写入已提交但回执丢失：重试读取 A 的已保存产物，保持原内容与版本 ID。
- 确认尚未保存的步骤可重新执行；模型生成后版本写入前失败，不声称该模型内容已经持久化。
- 已保存路由：只继续成功完成流程，不重跑任何业务步骤。
- 模型异步等待期间续 heartbeat；失去 lease 时取消等待，不保存迟到结果。过期运行由 A 的 expire/retry 协议恢复。
- 最终成功提交、权限/lease fencing、审核、eligibility、finalisation 继续由 A 控制。

## 5. trace 尚待 A 确认

`await agent.plan_with_trace(ItineraryInput)` 返回已有 `PlanningOutcome(itinerary, trace)`，trace 是调用方持有的本次结果。共享方法 generate_or_revise_itinerary 仍只返回 ItineraryResult。

本次没有增加全局 last_trace、内存审计队列、另一套数据库、表或未经确认的保存 API。当前 orchestrate 不持久化完整 PlanningTrace，因此不能宣称正式运行审计已经完成。

请 A 确认 trace 的正式接口、run/attempt/version 关联、幂等 key 与丢失回执恢复策略，尤其模型结果与版本保存的原子性。确认后 B 再对接；不能依赖重试重跑模型来补原版本 trace。现有行程中保留的模型决策摘要也不替代正式 trace。

## 6. 验证与下一步

`backend/tests/test_hybrid_planning_agent.py` 使用实际 CampusModelClient 和 Coordinator，HTTP 传输为 MockTransport/假密钥；持久化使用 A 既有 SQLite。

覆盖六方法、四套 agent PLAN 场景、规则步骤不调用模型、模式拒绝、无回退、回执丢失与进程包装重建、未保存步骤恢复、配置漂移、heartbeat 与 lease 失效取消。四套中的 budget_revision 本次只测试超预算首轮，不表示模型修订已实现。

这些是离线组件/内部持久化集成测试，不是校园实测或 agent HTTP/browser 验收。原四套规则 HTTP 场景继续由全量测试验证。

2026-10-13 本机验证：

- 新增 Hybrid 回归：25 passed。
- 全量后端：659 passed，0 skipped，0 failed，48.84 秒；保留既有 Starlette TestClient 弃用警告。
- 共享 schema 1.0、前端 TypeScript 类型构建、pip check、git diff --check 通过。
- 数据静态校验：68 passed，0 failed；静态验证器不执行其中 58 条应用验收规格。
- 未读取/输出私人密钥，未访问校园代理；数据包、共享 schema、依赖锁、默认配置和前端代码未改，未 commit/push。

下一步：A 注册 agent 数据工厂、扩展 managed runtime 对 agent 的管理、添加 PLAN-only HTTP/UI 守卫，并确认正式 trace 接口；之后 A/B 联合进行真实校园 HTTP/页面、恢复、人工审核与最终化验收。无需等待 A 才交付本包装，但正式应用闭环仍需这些接线。
