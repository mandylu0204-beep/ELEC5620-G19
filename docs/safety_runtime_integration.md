# B → A：A36–A38 安全模型运行时接线

日期：2026-10-17（Australia/Sydney）。分支：`feature/llm-safety-agent`。
共同基线：完整 `338ea23`，包含 A36 存储、A37 组件组合验收、A38 生产注册和
可信事实提供器，保留已验收的 `3510550`；本分支从该完整提交快进开发，未单独挑选接口。

按 [A38 交接](a38_safety_runtime_handoff.md) 实现 B 的 Hybrid／Orchestrator
接线。A 已关闭 R-S01、R-S02 并冻结 A30 组件契约，本次不改变冻结的 schema、prompt、
tool、validation 或文本策略，也不修改共享 schema 1.0。

**默认安全仍为 rules。** 代码具备显式 agent/2.1 模型安全接线能力，不代表已打开用户
配置，也不代表真实校园／浏览器联合验收完成。本轮校园调用为零。

## 1. Hybrid 的真实能力

- 声明 `safety_audit_contract='1.0'`，构造函数接收并保留 A 注册的原始
  `safety_agent` 对象，与可选的 `logistics_agent` 并存。
- 检查实际数据对象、agent/2.1 最终 workflow context、全部登记标记、canonical seed、
  完整配置摘要、最少三轮及 trace／纯回放方法。未登记、错配或缺失能力在推理前拒绝。
- `assess_safety_with_trace(input)` 真正调用 SafetyAgent 的带产物入口，返回
  `SafetyOutcome(assessment, plan, trace)`；模型等待结束后再次检查身份并执行纯校验。
- `validate_safety_artifacts()` 复用冻结组件的纯验证入口，对当前登记的固定快照、
  保存行程和已保存物流进行验证，不调用模型、不写数据库。
- 模型模式的完整正式 SafetyResult 必须等于可信规则基线。**不使用 `_rule_result()`
  添加“该步骤不是 LLM”的说明，也不把模型建议混入正式风险／置信度／blocker。**
  建议、行动优先级、引用和 SAFETY trace 单独保留。
- 共享 AgentPort 的 `assess_safety()` 在模型绑定下委托真实组件；正式编排始终使用
  带产物入口，不能只保存其 result。没有 `last_trace` 或全局模型结果缓存。
- 无模型绑定时，原规则安全和规则步骤标注保持不变。显式模型配置失败不回退规则。

Hybrid 的原有 `b05-hybrid-planning-3` 身份保持不变：默认规则路径语义没有改写；
启用安全角色由 A38 已登记的 `/a-model-safety-audit-v1`、角色 seed 和最终共同
context 区分。不是把新产物强塞进旧 run／旧 write key。

## 2. 编排与正式保存

Orchestrator 声明 `safety_audit_contract='1.0'`，在任何模型／业务写入之前检查全部
已启用角色的 Agent 和 RecoveryPort 能力。安全步骤从确认需求、保存行程和本 run
已保存的 `StoredAssessment(LOGISTICS)` 构建输入，通过配置的固定证据选择器生成场景。
沿用 A 的可信 `safety_facts_provider` 对结果独立复核，不提供新的可信事实来源。

```python
outcome = await agent.assess_safety_with_trace(saved_safety_input)
stored = await recovery_port.save_model_safety_assessment(
    version.version_context,
    outcome.assessment,
    outcome.plan.model_dump(mode='json'),
    outcome.trace.model_dump(mode='json'),
    scope.write_keys['safety'],
)
```

模型与保存调用均由原有 `Orchestrator.call()` 包裹，执行前及异步等待中续租，失去
lease 时取消未完成调用、拒绝迟到产物。安全保存后才依据已保存物流／安全结果路由，
最终业务资格与持久成功仍由 A 判断。数量、费用、证据有效性和最终化守卫未放宽。

| 物流 / 安全配置 | 推理角色（另有规划模型） | 已完成时的评估审计集合 |
| --- | --- | --- |
| rules / rules | 无评估模型 | 空 |
| model / rules | LOGISTICS | LOGISTICS |
| rules / model | SAFETY | SAFETY |
| model / model | LOGISTICS、SAFETY | LOGISTICS、SAFETY |

规划 trace 仍独立于 `model_assessment_audits`。安全没有 gear checklist，必须绑定
本 run／本版本的精确物流 assessment ID。与 A 的源选择、修订反馈及最终共同配置对齐，
没有在物流组件构造后补写安全标记。

## 3. Checkpoint、失败及恢复

期望审计集合 = **已启用模型的角色 ∩ 已保存 assessment 的角色**。校验不再只允许
LOGISTICS：空／部分 checkpoint 不要求未保存的 SAFETY，完整 checkpoint 则必须具备
全部应有审计。额外角色、未保存却出现的审计、缺失审计均拒绝。

检查审计 contract、kind、run／plan／version／assessment 关联、input fingerprint、
非空原始保存 attempt／audit ID／时间、配置与 trace 一致性、精确物流依赖、完整纯
回放及 canonical payload SHA256。A 的保存／读取边界仍独立检查 owner、lease、回执、
不可变记录和私有固定事实；B 的二次检查不代替 A 的鉴权或数据库约束。

| 情况 | 行为 |
| --- | --- |
| PLAN | 规划后执行已启用评估角色，独立保存 trace／audit |
| REVISE | 消费登记反馈生成新版本，再产生本 run 的物流／安全记录 |
| REASSESS | 不调用规划模型、不生成版本；同版本新 run 产生新评估与 SAFETY audit，原规划 trace 不变 |
| NO_MATCH | 不调用规划或评估模型，不生成版本和审计 |
| 安全保存前失败／事务回滚 | 保留已保存版本与物流，仅补缺失安全步骤；未提交推理可能重复 |
| 安全提交后丢回执 | 重启从 checkpoint 复用原 assessment、plan、trace、attempt、receipt，不重跑模型或重写审计 |
| 路由提交后丢回执 | 复用已保存全部产物，只补完成阶段 |
| 已保存审计缺失／损坏／串角色／依赖错误 | 不可恢复 PERSISTENCE_FAILURE、CONTACT_OPERATOR；不生成替代 trace，不提升 RETRY |
| 身份／配置漂移或丢失 lease | STALE_CONTEXT，拒绝迟到产物，保持已有产物 |
| 日切后恢复 | 使用原 run 固定日期／快照和原审计；当前资格过期仍不允许最终化 |

正式保存失败的可恢复性沿用 A 返回的错误；外部模型调用不承诺 exactly-once。
默认规则历史不会新增模型标记。旧 v1／旧内核 v2 归档继续走 A36 的可信保存身份及冻结
纯验证器；本次不把历史数据重标记为新模型结果。

## 4. 测试范围与方法

全部使用实际 CampusModelClient／Coordinator／LogisticsAgent／SafetyAgent、真实
A38 工厂、HTTP 认证／确认／Dispatcher 和独立 SQLite，只有校园 HTTP 回复由
`httpx.MockTransport` 提供。角色选择、工具执行、事实映射和保存／回读校验未被替换。
测试中明确用 agent/2.1；不能继续沿用旧 v2 的 scenario 作为正式安全来源。

- 四种规则／模型组合，以及正常、超预算、资料覆盖缺口、道路关闭四套入口。
- 真实结构化建议与独立审计、修订、同版本重评、最终保存和原规划 trace 保留。
- 两种物流模式下的提交后丢回执、保存前失败和路由后恢复；重启复用已保存字节。
- assessments／model_safety_audits／write_receipts 三处安全事务回滚。
- 非法模型输出和代理暂不可用不得变成规则成功；缺能力必须在推理／业务写入前失败。
- checkpoint 缺失／额外角色、错依赖、关联、attempt、hash、trace 和 plan 篡改，
  不可恢复错误经 Dispatcher 保留原语义，不重跑补审计。
- 等待中实际续租与失租取消，用 Event 同步，不断言精确 heartbeat 次数。
- 身份漂移、重启后历史／最终快照读取、owner 隔离、删除后拒绝读取且保留不可变审计。
- 空、已保存物流、已保存全部 assessment 的精确角色集合；NO_MATCH 零模型请求。
- 每日快照日切后恢复固定原快照，不以新资料替换旧审计。

A38 的注册测试现使用真实 Hybrid，不再用只声明能力的替身；负面就绪测试显式移除
所需能力，继续证明“接线不完整不能启用”。冻结的组件 schema／文本测试仍保留。

**场景差异不能掩盖：** 2.1 正常索引已覆盖原 River Flat 缺天气演示时段，不能把
那个正常结果伪报成缺资料。本轮覆盖缺口测试明确确认 `2026-11-30` 起的两晚行程，
检查日 `2026-11-29`，跨越封存资料有效期，实际产生 WEATHER MISSING／REVIEW。
没有删除或修改封存数据。公共 NO_MATCH 响应可能省略审计字段，应视为空，不能要求
虚构一个安全审计。新测试使用有界 30 秒本地状态等待，未增加模型超时／重试／token。

验证命令与最终结果见 [`evidence/safety-runtime-integration-check.json`](evidence/safety-runtime-integration-check.json)。

- 最终全量后端：**1338 passed、0 failed、0 skipped**，752.91 秒；一条既有
  Starlette TestClient／httpx 弃用警告，包含新增 54 项接线用例（HTTP／恢复 42 项、
  Hybrid 绑定／能力检查 12 项）。最终 JUnit：`var/safety-runtime-final.xml`。
- 冻结组件、旧回放与 A36 存储：324 项通过；既有物流／规则恢复／注册和绑定检查：
  116 项通过。这些属于全量中的重叠子集，不能与全量或新增用例相加。
- 前端 12 项测试、TypeScript／Vite 构建、共享 schema 1.0、内部契约导出、依赖及
  Git 空白检查通过。没有修改依赖或锁文件。

旧 A29／A37／A38 与 R-S01 报告保留各自基线和范围，不作为本轮真实安全模型证据。

## 5. A/B 下一步

无需再等待安全保存接口，本轮已按完整 A36–A38 接线。请 A 复核本分支与相同基线的组合，
确认全量 CI、应用读取和安全建议页面的最终呈现；本次未修改前端，不能据此宣称安全
建议 UI／浏览器验收完成。仍需展示独立优先级／原始事实引用、未验证标签，并与规划
trace、物流 audit 区分，不能把模型建议展示成安全批准。

联合真实验收应另行安排隔离数据库和有限预算，先少量正常 PLAN，再按必要范围验证
REVISE／REASSESS、资料不足／封路、最终保存／回读、权限及丢回执恢复。
仅在隔离验收进程显式使用 `CAMPMATE_EXECUTION_MODE=agent`、agent/2.1 数据和
`CAMPMATE_SAFETY_EXECUTION=model`；物流分别验证 rules/model，不改默认配置文件。
模型实际选择不同合法营地时按真实事实解释，不强制改输出以符合测试。只记录脱敏摘要、调用次数和
必要浏览器证据，不保存凭据、原始私人资料或模型推理。4096 tokens 下的大 findings
输出能力仍未由 mock 证明，不自动增加 token 或重试。

未修改个人环境文件、原用户数据库、封存数据、A 的工厂／Dispatcher／保存接口／
数据库结构；迁移 10 属于 A36，未另建或占用迁移。默认安全仍为 rules。
提交、推送与 CI 状态以 Git／远端记录为准，本次不自动合入 main 或进行真实模型调用。
