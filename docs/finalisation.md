# A-08 最终化与历史方案

2026-10-10；本地分支 `feature/a08-finalisation`，基于 A-07 本地提交 `b5e84b5`。API 开发版本 0.6.0，共享 Agent DTO/schema 1.0 未改变。

## 用户流程

Camper 查看自己的当前方案，阅读行程、装备、费用和安全依据；只有当前运行成功结束、版本可放行且没有待解决问题时，页面才显示最终保存确认。用户勾选确认后提交，服务器重新检查证据，在同一事务内保存快照、更新 FINALISED 状态与最终版本指针、保存幂等回执。页面在 HTTP 成功后跳转最终快照，不提前显示保存成功。

最终快照保存行程内容、版本及输入指纹、确认需求、采用的 Profile、演示时钟/数据上下文、推荐、两份评估、有效 Founder 审核、保存时 eligibility、阶段事件和保存人/时间。不会保存 B 写入 capability 或会话信息。版本内容、金额和评估来自已保存 DTO，不用测试 expected_* 生成。

`/plans/{plan_id}/finals/{final_id}` 回读完整快照，并明确标注“当前最终方案”或“历史最终方案”。方案列表、当前详情及最终方案记录都提供区分和链接。后续 REVISE 或 REASSESS 开启时，旧快照立即属于历史，即使重评复用了同一个 version_id 也不能当作当前结果。新证据须重新评估、必要时重新审核和最终保存；旧快照不可覆盖。历史 run 可回读当时产物，不显示当前 eligibility。

修改 Camper 当前 Profile 不改动过去确认需求或最终快照。涉及新日期、人数、预算等需求变化，仍须重新建立并确认需求；最终保存不能暗改需求。

## 接口与保存规则

| 接口 | 权限与用途 |
| --- | --- |
| POST `/api/v1/plans/{plan_id}/finalise` | 所属 Camper；会话、客户端 header 和 CSRF 校验；最终保存 |
| GET `/api/v1/plans/{plan_id}/finals/{final_id}` | 所属 Camper；完整不可覆盖快照，以及实时 is_current 标记 |
| GET `/api/v1/plans/{plan_id}` | 增加 finalisation_available、last_final、selected_final、final_history |
| GET `/api/v1/plans` | 每条索引增加 last_final，区分当前最终方案与历史最终方案 |

请求由 `backend/app/storage/finalisation.py::FinaliseInput` 定义：command_key、version_context、assessment_ids（恰好两份且不重复）、expected_review_id（可为 null）、expected_version_revision、expected_run_revision、acknowledged（必须为布尔 true）。禁止客户端传 owner、状态、最终快照或其他额外字段。成功响应包含 final_id、FINALISED、version_context 和 finalised_at。

保存事务核对所有者、当前 version/run/fingerprint、两份评估 ID、有效审核 ID 和 revision；重新计算登记输入的 fingerprint，核对确认请求、成功完成及已保存路由，再运行现有 eligibility 守卫。DRAFT、ASSESSING、REJECTED、BLOCKED、未解决修订、等待审核、stub、NO_MATCH、评估/费用/交通未知、必要证据不足或关闭道路均不能最终化。审批不能绕过这些问题。

证据检查针对 A 登记的不可变运行上下文；源文件或规则变化需由 A/B 工作流登记新 run，不在 finalise 内静默替换 CSV、Profile 或评估。真实数据更新及运行登记仍须在后续 B 联调验证。

同 key 同输入且上下文仍当前时回读原结果；同 key 不同内容冲突。当前上下文校验在回执之前，旧 key 不能授权新版本或新证据。不同 key 不能重复最终化同一次证据。失败使用现有 ErrorEnvelope/trace_id，过期与禁止最终化返回 409，字段错误 422，权限 401/403，保存失败 503。

migration 4 增加 final_commands、同 run/version 的唯一最终记录约束，并禁止更新/删除最终快照。BEGIN IMMEDIATE 事务将快照、状态、指针和回执一起提交；任一步保存失败全部回滚。不会重建或清空已有数据库。

B 持久化端口没有新增最终化权限或签名变化；FINALISED 始终由 A 的 Camper 命令保存。meta.finalisation=true 表示 A 侧保存服务已实现，不表示真实 Agent、规划启动或修订流程已接入。

## 实际检查与边界

完整 `scripts/check.py`：105 passed（新增 23 项最终化测试），1 个已有 Starlette 测试工具弃用提示；共享 schema up to date；TypeScript/Vite 构建成功，49 模块。测试覆盖批准后最终保存、独立正常方案、角色/CSRF/明确确认、旧证据/旧审核/旧版本、必要 blocker、不同状态、stub 与未完成输出、重复提交、竞争保存、故障回滚、不可覆盖快照、同版本重新评估后的历史、新版本历史和 schema 3 升级。

浏览器使用独立保存夹具与隔离数据库 `var/e2e-a08-final-20261010.sqlite3`，端口 8001/5174。验证未勾选不能保存、勾选后成功跳转、批准与完整产物回读、刷新恢复、关闭道路禁用最终化，以及新评估登记后历史标记和当前评估不混用旧审核。新评估通过测试辅助脚本登记，因为公开 B 启动/修订入口尚未接入。

证据：[保存后的当前最终快照](evidence/a08-current-final.png)、[道路关闭不可最终化](evidence/a08-blocked-finalisation.png)、[旧快照成为历史](evidence/a08-historical-final.png)、[当前评估保留历史链接](evidence/a08-reassessment-history.png)。

原始 synthetic 包、副本和默认数据库未改。此阶段为 A 侧保存与历史功能自检，尚无实际 B Agent 输出、四个首轮场景联调、其他成员复核、Jira Done 或干净环境端到端验收。下一项 A-09 处理工作流层的并发、幂等和失败恢复。本轮仅本地提交，尚未推送 GitHub、创建 PR 或运行本轮远端 CI。
