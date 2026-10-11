# B-03：编排、断点恢复及 A 接入说明

日期：2026-10-11。本轮使用 Git v1，未改原始数据、共享契约 1.0、A 的应用/数据库/权限/HTTP 或前端。没有 commit/push。

## 已实现

入口为 `RuleAgent.orchestrate(OrchestrateInput, persistence)`；编排实现在 `backend/app/workflow/`。

必须传入 A 已领取 attempt 的具体 RecoveryPort，支持无参数异步 `load_checkpoint()` 和 `heartbeat()`。这两个方法作为具体端口扩展使用，共享 PersistencePort 不变。缺少扩展时拒绝执行，不降级为从头重新生成。

执行顺序：读取 checkpoint → 推荐及保存 → 草稿及版本保存 → 使用已保存版本做物流并保存 → 使用已保存物流 assessment ID 做安全并保存 → 请求 A 路由 → 保存 COMPLETED/SUCCEEDED → 只读刷新 eligibility。

- 推荐、版本、物流、安全、路由已保存时直接复用；即使上次保存成功但返回响应丢失，也不重新计算或换内容复用原 key。
- 未保存步骤才重新执行。所有 write key 来自 A RunScope；业务 ID 和 fingerprint 仍由 A 产生。
- 阶段单调。A checkpoint 已领先某次原子写入时，不倒退回报早期阶段。
- NO_MATCH 是业务结束，不创建行程版本，也不伪造技术失败。
- PLAN 创建首版；REVISE 使用 A 传入的 previous_version 创建新版本；REASSESS 复用 A 为本 run 重新绑定的版本内容，但产生本 run 的新评估。
- requested_requirement_changes 不保存为新版本；返回不可原地 retry 的 REQUEST_NOT_CONFIRMED，需 Camper 重新确认。
- SUCCEEDED 只说明编排/保存完成，可以同时是 BLOCKED、REVISION_REQUIRED 或 ESCALATED，不代表方案最终化。
- 保存阶段失败可记录 FAILED；普通未知异常记录可恢复 AGENT_FAILURE，持久化异常记录可恢复 PERSISTENCE_FAILURE，其他 ContractFailure 保留自身可恢复标识。不把无效输入、变动上下文或不支持的规则无限原地重试。
- FAILED 自身不能保存时抛出异常，注明没有确认失败记录；不返回假装持久化成功的 FAILED。由 A 检查、expire、显式 retry。
- 取消任务不假报成功/已保存失败；清理内部等待任务，A 负责处理放弃的租约。
- 路由回执的 eligibility 早于 SUCCEEDED，结束后重新读 A eligibility，不把过期的 RUN_NOT_SUCCEEDED 留作最终 blockers。结束后的 eligibility 读失败不改写已成功的 run；调用方读取 A 的详情确认状态。

## 输入与上下文登记

`WorkflowConfiguration(dataset, safety_case_ids=(), feedback=None, scenarios=())` 固定本次执行选择，`config.context` 必须交给 A 的 start/claim/retry。不能把 A 旧的 `a-request-normalization-v1` 上下文直接传来执行 B-03。

context 包括六个 Git 业务文件摘要、A 的请求归一化版本、B-01 Adapter 版本、B-02 规则版本、B-03 编排版本，以及明确登记的安全场景 ID 和修订反馈。安全选择、反馈、规则、文件摘要、演示时钟或模式变化时，开启新 run，不原地 retry。

可选的 `scenarios` 是受信调用方提供的明确 ScenarioContext 补充，不是 Agent 猜出的事实。配置深拷贝这些 DTO，并将全部规范化 JSON 输入字节的 SHA-256 保存于 `fixture_digests['b03-explicit-scenarios.canonical.json']`。该摘要明确是规范化 DTO 内容摘要，不能冒充原始 fixture 文件 bytes 的摘要。source_refs、template_id 和适用日期必须由调用方明确提供。若 A 另有原文件摘要，应另外登记并共同扩展配置，而不是删掉字段绕过比较。

装备/车辆/物资的用户确认数据属于 A ConfirmedContext 中的 ProfileSnapshot，与确认需求一起由 A fingerprint 绑定；B 不读取测试夹具补齐它们。

配置为空时仍可执行，但安全缺失。B 不自动从任意测试/说明文件加载事实，也不挑一个看起来能通过的场景。使用 Git 场景须显式提供 safety_case_ids；只取与实际选中营地有关的证据，不把另一个营地的事实套用过来。

多个场景组合时保留原证据及其日期，外层范围使用保守交集；未知日期仍为 null，不填本次行程日期充当覆盖范围。数据/配置 DTO 的公开属性返回独立副本，调用方修改列表不会影响运行快照。

## A 内部调用示例

下面仅示范已有身份和已确认请求的内部接线，不是 HTTP 接口、自动确认或后台调度器：

```python
from app.adapters import SyntheticDatasetAdapter
from app.agents.rule_agent import RuleAgent
from app.contracts.dto import OrchestrateInput
from app.workflow import WorkflowConfiguration

# settings、workflows、user、confirmed_request_id 都由 A 受信服务提供。
# 每次启动/重试先从当前数据加载并核对配置，不盲用旧缓存冒充当前证据。
dataset = SyntheticDatasetAdapter(settings.dataset_path).load()
config = WorkflowConfiguration(dataset, safety_case_ids=['safety-01'])
agent = RuleAgent(dataset, workflow_configuration=config, heartbeat_interval=20)

scope = workflows.start(
    user, confirmed_request_id, demo, config.context,
    command_key=client_command_key,
)
attempt = workflows.claim(user, scope.run_id, demo, config.context)
port = workflows.port(user, attempt)
confirmed = await port.load_confirmed_context()
result = await agent.orchestrate(
    OrchestrateInput(run_scope=scope, confirmed_context=confirmed), port,
)
```

示例选择 safety-01 不保证推荐出的营地就是 pine-camp，也不保证任何安全事实完整。实际场景选择须与营地适配；无匹配时明确缺失、不能放行。

恢复由 A 先读取 FAILED/revision，再 `retry(... expected_run_revision=..., command_key=新key)`，claim 新 attempt，并传入新的 port。B 不调用 start/retry/claim/expire，不持有数据库，不替 A 生成身份或执行凭证。恢复中的 REVISE 若新版本已保存，不再需要旧版内容参与生成；尚未保存时仍须由 A 提供旧版快照。REASSESS 使用 checkpoint 内本 run 的 VersionContext，不能复用旧 run 的评估和审核。

## 续期与并发边界

B 在每次业务/持久化调用前续期，并在异步等待期间默认每 20 秒续期。建议间隔严格小于 A 配置租约的三分之一：默认 120 秒租约可用 20 秒，更短租约必须相应调整。

续期失效时取消正在等待的内部任务，不继续推进写入；旧 attempt 的迟到写入仍由 A fences 拒绝。不得通过 asyncio 包装长时间阻塞事件循环的同步 LLM/网络调用；后续真实模型使用非阻塞调用或另行设计 worker，A 仍负责进程级调度、重启/过期检查及显式恢复。B 的协作式续期不是通用后台扫描器。

## 与 A 的实际行为、待共同接线

1. A 当前 `AGENT_FACTORIES` 仍只注册 STUB，A data_context 仍使用旧请求规则版本。未自动注册 deterministic_demo：单纯注册但不更新 A 的 context/启动接线会造成 STALE_CONTEXT 或错误地宣称页面可规划。A/B 需一起接入上述配置、工厂、HTTP 启动/重试和调度，再更新页面能力提示。
2. Git v1 无完整证据有效期。B 规则会要求审核，而 A 的必要证据守卫更严格，持久化状态为 BLOCKED，eligibility 保持 false；返回值以 A RouteResult 为准，不为了成功演示改数据或放宽守卫。
3. 高风险且普通修订同时存在时，B 优先建议 ESCALATED；A 仍可能优先 REVISION_REQUIRED。这是既有路由优先级差异，未修改 A。review_required/blockers 仍可读，但审核队列语义需 A/B 对齐。
4. 本轮没有 LLM/API Key、真实爬虫、前端启动按钮/构建或真实用户端到端演示。B-03 后端编排已可内部调用；完整 Stage 2 应用仍需 A 接线、准备明确演示输入及后续功能。

## 验证

从 backend/ 使用项目锁定依赖运行：

```bash
python -m pytest tests/test_rule_orchestration.py --basetemp ../var/pytest-b03
python -m pytest --basetemp ../var/pytest-b03-final
python -m app.export_contracts --check
```

独立测试使用 A 的真实 WorkflowService/RecoveryPort、临时 SQLite、B 实际规则和明确标注的测试 Profile/证据。涵盖正常可计算输入、超预算、证据缺失、道路关闭、NO_MATCH、三种 operation、保存回执丢失、阶段/完成响应丢失、数据库失败、service/agent 重启、阶段单调、上下文变化、取消/续期、旧 attempt 拒绝。原始 Git 数据未改；完整输入是隔离测试，不是默认生产数据或 UI 成功证明。

2026-10-11 实际结果：B-03 44 项通过；完整后端回归 398 项通过，有一条既有 Starlette/httpx 弃用警告；共享 schema、Python 语法和空白检查通过。测试环境是隔离 Python 3.12.14 加仓库 requirements.lock，不改变项目依赖版本。

提交建议：当前 B-01、B-02、B-03 均未提交，可一并使用 [commit message](commit_b01_b03.txt)。不要把忽略的 var 测试数据库/缓存、临时环境或原始数据包放入提交。
