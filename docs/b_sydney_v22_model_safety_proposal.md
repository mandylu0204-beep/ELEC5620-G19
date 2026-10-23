# B：悉尼数据 2.2 模型安全适配提案

状态：离线盘点及前置边界验证；待 A/B 确认，尚未实现或启用 2.2 模型安全。

当前开发基线：main `180701c5432d03339f12ec593188d7bddb41207d`。
首次离线检查源：`fee6bb7f6832a4697dbee7794aff37319fe5e734`，原结果保留。
开发分支：`feature/sydney-v22-model-safety`。
日期：2026-10-23（Australia/Sydney）。

## 本轮完成与不做的事

- 当前功能分支已从 `fee6bb7` 快进到共同基线 `180701c`；三个未提交文件在快进时保持原样，后续仅更新本文档和补测摘要，不直接修改 main。
- 盘点实际阻断位置、完整身份和旧回放约束，新增纯离线前置检查。
- 不复跑 A88 浏览器流程，不重跑全量，不使用 Actions，不读取个人模型配置，不创建模型客户端或发送校园请求。
- 不修改生产代码、封存数据、个人数据库、环境文件或安全默认值。本轮不引入新迁移或正式审计写入。

## 当前实现的真实边界

| 边界 | 位置 | 现状及适配要求 |
| --- | --- | --- |
| 工厂前置检查 | `backend/app/application/agent_runtime.py::build_v2_hybrid_binding` | safety=model 时只接受 2.1；在读取模型配置、创建客户端之前拒绝 2.2。不能只删除这个条件。 |
| runtime 能力确认 | `backend/app/application/agent_runtime.py::AgentRuntime` | 再检查 2.1、model 标记、审计契约和角色能力；须与工厂使用相同支持矩阵。 |
| Hybrid 绑定 | `backend/app/agents/hybrid_planning_agent.py::_check_configuration` | 只允许 2.1 模型安全；还绑定 Dataset 对象、最终 workflow context、seed、指纹、方法及轮数。 |
| 安全组件 | `backend/app/llm/safety_agent.py::_check_configuration` | 只接受 2.1、有 selector、摘要匹配的快照。 |
| 只读工具及纯回放 | `backend/app/llm/safety_tools.py::SafetyToolset` | 输入必须为 agent/2.1，纯校验器重建同一工具；必须同步处理新调用与正式审计回读。 |
| identity/schema | `backend/app/llm/safety_identity.py`、`safety_contract.py` | seed 的 kernel/rules 配对为闭集，但 seed 本身没有 dataset_version 字段；compose 会把完整 DatasetContext 纳入指纹。2.2 沿用现有规则版本，因此仅 seed/schema 通过不代表 2.2 已注册可用。 |
| 正式保存与历史读取 | `backend/app/application/safety_audit.py`、`llm/safety_validation.py` | A 按已登记 validation_version 选择纯校验器；新写入目前仅接受 v2/current kernel。新增版本必须同时考虑写入、回放和错误关闭。 |
| 默认启动 | `scripts/sydney.py` | 强制 safety=rules，即使父进程继承 model 安全设置也不启用；目前没有 --safety 参数。默认行为保持不变。 |

现有多层拒绝是有意的保护，不是“改一行版本即可”的缺陷。seed 组成函数属于身份表达，不能代替来源验证、生产注册、权限或纯产物校验。

## 建议的兼容策略：独立 v3，而不是改写旧 v2

建议采用新的内部身份三元组，具体命名需 A 确认：

- `campus-safety-advisory-agent-3`
- `safety-read-only-tools-3`
- `safety-advisory-validation-3`

新 v3 首先只为 dataset 2.2.0 的明确支持路径服务，不以 >=2.1、字符串前缀或通用 Adapter 支持列表代替安全角色闭集。新注册要求当前 kernel/rules 的精确配对，且 input.demo_context、dataset、最终 workflow_context 的版本必须一致。

v1/v2 的既有 schema、提示摘要、纯校验与离线档案行为保留；旧 2.1 审计不重标为 v3，不替换原 trace，不用新模型“补齐”旧记录。若需移动旧代码以冻结 v2，必须证明导出 schema、提示摘要和既有档案回放保持一致，而不是简单复制后宣称兼容。

建议继续支持 2.1 使用当前 v2 的既有路径。新增 2.2 使用 v3，A-owned 新写入白名单需按“数据版本 + validation 版本 + kernel/rules”配对判断，不能只把 v2 全局替换成 v3，导致正常 2.1 新写入或历史回读中断。

共享 DTO/schema 保持 1.0，`save_model_safety_assessment` 签名和审计 envelope 暂建议保持 1.0。新版本是内部安全协议版本，不等于新数据库迁移；由 A 确认现有存储能否容纳，不预占迁移号。

## 数据与工具事实边界

1. 完整身份必须保留原 `file_digests`、fixture 摘要、selection_config、rules_version，包括 `source_catalogue.json`、manifest、runtime evidence 和 daily snapshot 的日期、base identity、policy 标记。任何来源变化都产生不同指纹，不能用缓存隐藏变化。
2. 注册时必须验证实际来源及摘要。compose 对任意调用者给出的 context 重新计算指纹，不等于该 context 已被应用授权；B 纯校验不负责证明所有权或磁盘来源。
3. 当前 2.2 是混合来源：地点、设施和永久限制有封存的来源目录；天气、动态道路和火险仍为有限模拟资料，费用为规划假设。不能宣称模拟天气来自官方实时服务，也不能把全部地点资料说成模型创造的假地点。
4. v3 提示词明确区分静态地点来源与模拟动态条件，只允许依据宿主提供的事实。模型不浏览来源 URL，不自行获取天气、不创造证据、不推断通行许可。共享 SourceRef 的冻结来源族不改名，不冒充 live evidence。
5. 只读工具继续以保存行程、物流结果、确定性安全结论和选择证据为核心，不自动把整个 source_catalogue 或整个资料包发给模型。若新增来源说明投影，须明确最小字段、事实指针和摘要绑定，不改变 finding key 的含义后仍沿用旧工具身份。
6. 完整事实、所有 finding、priority 和允许 action 都必须保留。保持现有字节上限、64 finding 上限、精确 action/schema、模型文本过滤及校验失败保护；超限明确拒绝，不截断资料或静默漏项。
7. 木火禁令不能扩大成所有燃料/电器禁令；明确道路关闭、资料缺失/冲突、未知活动和物流缺口继续由确定性代码决定。建议不能覆盖 blocker、风险、数量、费用、预算或人工审核要求。

## A/B 分工及需要确认的接口

用户转述 A 的最新安排：等待 B 将安全模型接入新数据后，再继续用户测试。因此下一轮实现由 B 推进，A 不必先重复 A88/A90 浏览器测试或现有前置检查。下述跨层所有权分工是建议，不代表 A 已承诺先提交另一套适配实现。

### B 负责

- 新 v3 组件、只读工具、提示/身份/schema 与纯校验器；现有 v1/v2 的回放兼容。
- 不依赖真实模型的合成正常/恶意/超限输入回归，2.2 实际选中营地和资料覆盖边界。
- 先推进独立 v3 组件与 MockTransport 离线验证；涉及 A-owned 注册/审计边界时明确提出最小接线改动，由 A 确认支持矩阵和版本约定后完成组合，保留请求级组件和客户端隔离、checkpoint/heartbeat 及恢复能力。
- 有界传输观测复用已有实现，不记录密钥、完整提示、原始模型回复或私有推理。

### A-owned 边界及复核事项（实施分工待确认）

- 工厂/runtime 的数据版本与角色版本支持矩阵、所有 seed 收齐后绑定最终 context。
- 新写入版本白名单、正式事务保存、回执、回读与 UI 角色能力；确认不需要新迁移及不改变保存签名。
- 每日快照选择、恢复时回到已冻结快照、新重评选择新快照，以及用户/出行方案/评估隔离。
- 后续显式启动选项及验收服务。默认仍 rules，不在本轮改 `scripts/sydney.py` 的默认行为。

待 A 确认：v3 三元组和精确数据支持矩阵；旧 2.1/v2 新写入是否继续支持；validator dispatch 和 new_write 配对；来源说明投影字段；是否保持 audit_contract/shared schema/save port 不变。

## 实施与验证顺序

1. 本轮：离线盘点、拒绝边界和旧档案回放检查，A 复核本提案。不需要 A 重跑 A88 或校园诊断。
2. B 继续实现新组件/契约和离线验证；注册/审计边界由 A 确认后按约定实施，不默认要求 A 先另做一套实现，也不未经确认宣称新协议已冻结。避免双方重复修改同一模块。
3. 组合离线测试：2.1/v1/v2 历史回读、2.2/v3、错误配对、来源/选择/目录/快照篡改、并发隔离和严格拒绝；再测 PLAN/REVISE/REASSESS 及失败恢复的正式审计关联。
4. 离线通过后另行申请有调用上限的真实验收。旧 A64/A88 记录不能作为新的 2.2 模型验收；真实请求不属于本次授权执行内容。

恢复要求：只继续缺失步骤，复用已保存规划/trace、物流/审计；不得重新 PLAN 后复用原写 key，不因日期或身份变化改旧快照绕过守卫，不因失败变成规则成功或制造 trace。

## 本轮离线验证

新增 `backend/tests/test_sydney_safety_preflight.py`。测试主动拦截模型配置读取、模型客户端构建和 httpx 发送；只检查现有拒绝与规则路径，并 mock 启动器子进程，不启动网页。

基线更新核对：`fee6bb7..180701c` 仅包含审核显示修复、对应测试与报告，包括后端 `presentation.py` 的只读状态投影；不是完全没有后端改动。没有修改模型安全组件、Hybrid、工厂/runtime 注册、审计、数据包或启动器，因此本提案的边界盘点仍适用。

原 `fee6bb7`：15 passed / 0 failed / 0 errors / 0 skipped，退出码 0，1.03 秒；共享 schema 检查通过。结果不改写为新源码结果。

补测 `180701c`：同一组 15 项，15 passed / 0 failed / 0 errors / 0 skipped，退出码 0，1.05 秒；共享 schema 检查通过。测试文件 SHA-256 保持 `01ef23ea6a75e5188233a973ac20d0198cb72828427ccaaf9a0b40dcd5ab8712`。补测使用独立临时目录，保留原 JUnit，不新增前端、浏览器或全量验收声明。

精确结果及执行范围见 `evidence/b-sydney-v22-safety-preflight.json`。本轮没有生产适配成功声明，没有真实模型或 2.2 安全审计写入。
