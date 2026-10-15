# A25：物流运行时接线复核

日期：2026-10-15（Australia/Sydney）。复核 B 提交 `bc5c74fff1e606bc1959ac955445ed30155a944b`，PR [#5](https://github.com/LyraWangDev/ELEC5620-G19/pull/5)，对照 main `9b5414347faa8212c2322918e519e00ba68b84d8` 和 A24 冻结约定。

后续真实联合验收发现2048输出截断，已修正公开默认值；缺资料场景仍连续上游502，尚不能合main。以下是此前代码/离线复核结论，最新状态见 [真实联合验收](logistics_live_acceptance.md)。

## 代码复核

本轮未发现阻止进入真实联合验收的代码问题。Hybrid 保留 A 工厂传入的物流组件，并核对组件、数据对象、完整配置与身份 seed；等待模型后重新核对身份。模型模式显式启用，无规则回退；默认 rules、正式持久化签名、数据库迁移及共享 schema 均未改。

PLAN、REVISE 和 REASSESS 的物流步骤使用带 plan/trace 的内部方法，通过 A 的正式端口同事务保存。REVISE 产生新版本；REASSESS 复用行程与原规划记录，只生成本次物流评估及审计；NO_MATCH 跳过两个模型。安全步骤只使用保存后的物流评估。

恢复校验包括审计关联、完整结构化产物、登记输入/配置和载荷摘要；已提交物流复用 checkpoint，不重跑模型补 trace。物流未提交时允许重新调用，因此不承诺外部模型 exactly-once。Orchestrator 已移除按 PERSISTENCE_FAILURE 统一提升 RETRY 的逻辑，与 A24 Dispatcher 一致。

租借、购买和借用建议仍未确认，未知费用保留 null；数量、容量、费用和预算由确定性代码计算，不能用模型建议清除原有 blocker。新增纯校验 helper 与 A 的独立保存校验并存，未替代权限、lease、事务或历史验证器。

Hybrid 身份升级为 `b05-hybrid-planning-3`。旧未完成运行不能跨身份继续，需要重新确认后开启新运行；历史读取继续使用保存的事实及记录。

## 最新 main 的组合验证

GitHub PR CI 已实际测试合并结果，而不只是 B 分支自身。检查 [38566642991](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38566642991) 的 checkout 记录为：`Merge bc5c74f into 9b54143`，临时合并提交 `e2bf90f`。

- 后端：860 passed，1 条既有 Starlette 警告。
- 共享 schema 导出检查、前端构建通过。
- A 本地另建 `feature/a25-logistics-integration`，合并相同两个基线，无冲突；前端 TypeScript/Vite 构建及 schema 导出检查通过。
- A 本机针对性独立复跑：193 passed，1 条既有 Starlette 警告，187.54 秒。覆盖新双模型接线、A24 物流审计、物流组件、最新方案读取、审核和最终保存；校园响应均为离线模拟。

此结果补足 B 交接时尚未验证 `9b54143` 的说明，但仍是离线结果，不代替真实校园调用或浏览器联合验收。

## 下一步与合并边界

暂保留 PR，联合验收完成后再合入 main。使用隔离数据库和本地凭据，显式启用 agent/v2 与模型物流，覆盖正常 PLAN、低成本 REVISE、同版本 REASSESS、缺证据和封路，检查两个独立模型记录、装备未确认标记、最终保存、重启读取与 owner 隔离。保存提交后丢回执的模拟故障需独立记录，不能把离线 MockTransport 结果称作真实模型恢复验收。

本轮未读取个人密钥、发出校园模型请求、修改默认配置/封存数据/已有用户库，未生成 Canvas 提交 ZIP。

文档小项：B 交接末尾“本轮不 commit/push”与已推送提交及开放 PR 的现状不一致，后续更新交接时可删除或改为当时状态；不影响代码验收。
