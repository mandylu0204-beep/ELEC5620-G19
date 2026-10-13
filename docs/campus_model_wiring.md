# A-16：校园模型应用接线交付

**发布更新：完整A16及正常场景真实验收已快进合入远端main（9996e74），main CI通过；B可直接从更新main开始。新增异常/受控保存恢复验收见 [A17交接](campus_exception_acceptance.md)。下文此前“尚未合main/未发布”的描述保留为阶段历史。**

**最新追加（2026-10-13）：用户配置密钥/连接USYD VPN后，正常场景真实校园HTTP和浏览器闭环已通过，包括最终保存、重启回读和用户隔离。服务返回Qwen/Qwen3.8-27B-FP8，2轮/2次，9625ms。当前结果见 [真实校园验收](campus_live_browser_acceptance.md)。以下发布时未连通/离线验收说明保留为当时记录；其他真实校园失败场景与模型角色仍待完成。**

日期：2026-10-13。完整分支 `feature/a16-campus-wiring` 已推送 GitHub；应用提交 `2d88ad3`，包含 A14/A15、B `5c4a093` 的完整 HybridPlanningAgent 和本次 A16。尚未合入远端 main，也未创建 PR。请使用完整分支集成，不能把 A16 单独摘到缺少 B 组件的旧 main。原确认事项见 [C-01～C-08](campus_llm_a_reply.md)。

发布后本机检查：校园密钥未配置，代理TCP连接超时。用户选择暂时只完成 GitHub 同步与交接，未执行真实模型请求；已生成忽略的本地空密钥配置模板，不提交该文件。校园 HTTP/浏览器联合验收仍待网络和凭据就绪。

应用提交2d88ad3的 [远端CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38322599358) 已通过。给B的完整分支交接见 [发布说明](a16_b_branch_handoff.md)。

## 已实现的边界

| 项目 | 当前实现 |
| --- | --- |
| 注册 | `app.application.agent_runtime.DATASET_AGENT_FACTORIES[(ExecutionMode.AGENT, 'CampMate Synthetic Demo Dataset v2')] = build_v2_hybrid_binding` |
| 构造 | CampusModelSettings/Client → 离线 validate_configuration → 校验登记摘要的 V2Adapter → PlanningCoordinator → build_hybrid_configuration → HybridPlanningAgent |
| 执行身份 | 确认、run、产物、持久化 scope 始终为 agent；RuleAgent 原 deterministic_demo 守卫保留 |
| 能力 | 仅 PLAN、单营地、最多30晚；修订/重评在登记新 run 前拒绝，页面不提供入口；失败 PLAN 仍可重试 |
| 阶段 | 行程由模型生成；需求解释、营地筛选、装备/费用与安全仍使用规则；meta 和页面明确显示 |
| 默认开关 | stub/v1、planning_enabled=false 保持；个人 .env、.env.llm.local 和原数据库未改 |
| ready/meta | 配置与数据检查，不调用模型；ready 成功不代表校园网络已连通 |

缺凭据、数据身份不一致或未注册来源时显式未就绪，不回退为规则/stub。模型配置、Prompt/schema/tool 等身份变化后旧运行不能继续放行。首版模型模式不支持重评，因此须重新创建并确认需求；历史最终快照仍可读取。

## B 可调用的 trace 扩展

实际导入位置是 `app.application.model_audit.ModelPlanningPersistencePort`；该模块已存在。共享 AgentPort、PersistencePort 和 JSON schema 仍为1.0，无 DTO 返回类型变更。实现位于 `app.storage.port.SqlitePersistencePort`，现有 RecoveryPort 继承并提供此方法。

```python
async def append_model_plan(
    self,
    expected_current_version_id: str | None,
    content: ItineraryResult,
    request_id: str,
    reason: str,
    trace: Mapping[str, object],
    write_key: str,
) -> StoredVersion: ...
```

`trace` 使用调用局部的 `outcome.trace.model_dump(mode='json')`，write_key 使用 `scope.write_keys['version']`。A 已修改 Orchestrator：必需 trace 的分支执行 `agent.plan_with_trace`，再调用上述端口；两次 await 均处于原 heartbeat/cancel 包装中。规则模式仍调用普通版本保存；声明必需 trace 的运行不能通过普通保存绕过审计。B 无需使用全局 last_trace，也无需再重复接线此分支。

严格校验 B 当前 PlanningTrace：SHA-256、字段/字符串/列表边界、整数 usage、显式 validation_passed=true、工具和轮数、实际保存推荐中的候选、行程中的选中营地，以及登记的模型/配置/Prompt/tool 身份。usage 未提供时保持未知。只存简短决策摘要和回复哈希，不存密钥、Authorization、原始提示/回复全文或私有推理。

A 审计身份为 `a_model_trace_required=1`、`a_model_trace_contract=1.0`、`a_model_prompt_sha256`、`a_model_tool_version`、`a_model_requested_model`；保留 B 的 `hybrid_agent_version`、`hybrid_kernel_version`、`hybrid_planning_fingerprint` 及 A 的全部数据摘要/选择项。

## SQLite、恢复与查询

迁移6增加 `model_planning_traces`，每个 run 一份，保存 A 派生的 owner/plan/run/version/input_fingerprint/生成 attempt/时间和受控 trace，使用不可更新、不可删除的触发器。迁移5的既有资料及记录保留。

版本、run绑定、当前版本指针、trace、幂等收据在同一事务内保存；trace 写入失败全部回滚。同 key/同内容和 trace 返回原版本，同 key/不同 trace 拒绝。保存前失败可以再次调用模型；已提交但回执丢失则从 checkpoint 恢复原版本和 trace，不重新生成，原生成 attempt 不变。

`load_checkpoint`、方案详情和最终快照新增 `model_planning_trace`，其结构为 A 关联元数据加 `trace` 对象。前端显示模型、服务返回身份、轮数/尝试数、耗时、usage、摘要及关联指纹；最终快照保留原记录。旧规则记录该字段为 null。

缺失、损坏或不属于当前输入的必需 trace 将阻止继续放行。营地合法性、两份评估、审核、blocker、用户隔离、租约和最终化守卫仍适用；模型输出通过结构校验不代表安全或可保存。模型选择缺少覆盖证据的其他合法营地时，仍被规则评估阻止。

异常沿用 `app.contracts.errors.ContractFailure(ContractError(...))`；HTTP 返回 `{"error": {"code": "...", "message": "...", "field_errors": [], "recoverable": false, "allowed_actions": [], "context": {}}, "trace_id": "..."}`。身份变化为 STALE_CONTEXT，非法 trace 为 CONTRACT_INVALID，缺失必需审计为 PERSISTENCE_FAILURE；不支持的操作为 INPUT_INVALID。失败后能否重试由既有工作流恢复状态决定，不能把所有错误都标成可重试。

## 本次验证

最终 `scripts/check.py` 退出0：638 passed、44 skipped、1条既有 Starlette 警告，407.75秒。44项为 Windows 文件符号链接创建权限限制，junction 用例实际通过。共同 schema 同步；TypeScript/Vite 53模块构建通过（1.57秒）；pip check、git diff --check通过。

新增15项实际 HTTP/SQLite 集成测试，覆盖认证、配置与模式、PLAN能力限制、最终保存、用户隔离、trace原子回滚/幂等、保存回执丢失后服务重启恢复、身份变化、恶意/缺失 trace、无匹配及数据库迁移。使用 B 的实际 Client、Coordinator、工具、校验和 Hybrid，只替换模型 HTTP transport 为模拟响应，并显式使用 `_env_file=None`。

独立数据库上的真实浏览器已完成：登录 → 保存演示 Profile → 草稿/解释/明确确认 → 调度 → Wattle Rest/AUD251/两份评估通过 → 明确最终保存 → 刷新回读原 trace。没有修订/重评入口，控制台 error 为空。数据库只读复核为1请求、1run、1版本、1trace、2评估、1最终记录，最终快照 trace 与审计行一致。截图明确标示 `offline-test-only`，不能作为校园网络成功证据。见 [检查摘要](evidence/a16-campus-wiring-check.json) 和 [页面截图](evidence/a16-offline-model-trace.png)。验收服务和标签已关闭。

B 组件的两项 Windows 测试修正也在本分支：大响应参数用短 pytest ID，heartbeat 用同步事件检查等待模型时确实续租；不依赖固定速度/续租次数。旧测试“模型工厂尚未注册”的断言随本次注册更新，RuleAgent 模式限制仍验证。

## 下一轮真实校园联合验收

需要先让 B 取得本完整分支，再联合验证正常场景的真实模型 HTTP 与浏览器；本轮没有读取个人密钥或调用校园代理。B 的既有 CLI 成功文本是组件证据，与本轮离线接线证据分开保留。还未完成三个模型角色、模型修订/重评、真实校园闭环的失败恢复、最新版干净安装、Canvas下载或另一电脑验收。

真实校园启动前，由使用者自行检查根目录 `.env.llm.local`，可参考公共 `config/campus_llm.example`；已有配置不能覆盖。校园端点与 VPN 要求沿用 B 文档，本轮未验证连通性。不要提交或打包此凭据文件。

下面是在一个单独 PowerShell 终端中的明确 opt-in 配置，只作用于该进程；使用独立数据库，不编辑 `.env`。**执行后规划会真实调用校园代理，本轮未执行这些命令。** `scripts/demo.py` 继续用于规则场景，会显式设定 deterministic_demo，不能用它覆盖此模型配置。

```powershell
$env:CAMPMATE_EXECUTION_MODE = 'agent'
$env:CAMPMATE_PLANNING_ENABLED = 'true'
$env:CAMPMATE_DATASET_PATH = 'data/synthetic_demo_v2'
$env:CAMPMATE_DEMO_TODAY = '2026-11-05'
$env:CAMPMATE_WORKFLOW_SAFETY_CASE_IDS = '["safety-15"]'
$env:CAMPMATE_DATASET_SCENARIO_FILES = '[]'
$env:CAMPMATE_DATASET_SELECTION = '{"demo_input":"normal"}'
$env:CAMPMATE_DATABASE_PATH = 'var/demo-campus-normal.sqlite3'
.\.venv\Scripts\python.exe scripts/dev.py
```

输入沿用 `docs/demo/v2_inputs.json` 的 normal 与 Profile：2026-11-06开始、两晚/三天、两人、AUD320、quiet、ready-to-eat meals。每次从实际登录/资料保存/需求确认开始，不预存成功产物。模型可选择另一个合法候选；若实际费用或安全证据不满足要求，必须显示修订/审核/阻断，不能为了演示强制通过。校园调用成功后需单独记录真实 served model、trace、HTTP与浏览器结果，再更新验收状态。
