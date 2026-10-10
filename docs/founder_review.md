# A-07 Founder 人工审核

2026-10-10，当前本地分支 `feature/a07-founder-review`，基于未推送的 A-06 提交 `9d74e50`。API 开发版本 0.5.0，共享 Agent DTO/schema 1.0 未改变。

## 已实现的流程

Founder 登录后进入 `/review`，读取已经结束且需要审核/修订/处理 blocker 的当前方案。详情 `/review/{plan_id}` 展示同一 run/version 的行程、装备、费用、安全证据、当前 eligibility、确认需求与当时采用的 Profile 快照。不会读取 Camper 当前资料或其他运行历史。普通无需审核的可放行方案不属于 Founder 详情读取范围。

选择 APPROVE、REJECT 或 REQUEST_REVISION，填写非空理由后提交。页面可展开本次绑定的版本 ID、run_id、input_fingerprint 和两份 assessment IDs。已处理项退出队列，决定与理由保留在 Founder 详情以及所属 Camper 的方案页面。

APPROVE 在保存审核记录的同一事务内重新计算 eligibility；存在道路关闭、必要证据缺失/过期/冲突、未知必要费用、超预算或装备修订问题时失败并回滚，连批准记录也不保留。通过后状态为 ELIGIBLE_FOR_FINALISATION，仍不写 FINALISED。REJECT 设置 REJECTED，REQUEST_REVISION 设置 REVISION_REQUIRED；保留原始版本内容、评估和 blocker，不能据此直接最终化。

审核人来自服务器会话。保存时检查当前 plan/version/run/fingerprint、两份评估 ID、版本 revision、run revision、成功结束和已保存路由。新运行或新版本产生后，旧页面不能提交，旧批准的重试也不能重新授权新证据。评估未结束时不能审核。

## A 的 HTTP 接口

| 接口 | 行为 |
| --- | --- |
| GET `/api/v1/review-queue` | Founder 专用；返回当前待处理方案索引 |
| GET `/api/v1/review/{plan_id}` | Founder 专用；当前审核依据和 review_available |
| POST `/api/v1/review/{plan_id}` | Founder 专用；会话、客户端 header 和 CSRF 校验 |

提交格式由 `backend/app/storage/reviews.py::ReviewInput` 定义：command_key、version_context、assessment_ids（恰好两份且不重复）、expected_version_revision、expected_run_revision、decision、reason。未声明字段禁止提交，不能传 reviewer 或 role。错误使用现有 ErrorEnvelope，包含 code/message/trace_id；过期和冲突为 HTTP 409，权限为 401/403，字段格式为 422。

POST 成功返回 review、status、version_revision、重新计算的 eligibility，以及 revision_execution_available=false、finalisation_available=false。同 key 同内容且上下文仍当前时回读原结果；同 key 不同内容冲突。事务 BEGIN IMMEDIATE 将审核、状态更新和回执一起保存，保存失败全部回滚。migration 3 增加 review_commands，并保护审核及回执不可更新；升级保留已有记录。

B 继续使用原持久化端口 `load_review_result(context, assessment_ids)`，无签名变化。只返回与完整当前上下文、两份评估和 Founder 身份一致的记录。B 不直接写审核或 FINALISED。

## 验证与实际边界

独立测试夹具复用 A-06 的保存辅助方法，不调用 B Agent，不读取测试 oracle，不修改原始 synthetic 数据。浏览器使用隔离数据库 `var/e2e-a07-review-20261010.sqlite3`，端口 8001/5174；默认数据库未改。

新增 14 项后端测试覆盖三种决定、理由必填、角色/CSRF、伪造审核人、读取范围、重复点击、竞争审核、版本/run/fingerprint/评估变化、道路与证据 blocker、超预算、保存失败回滚和升级后回读。最终完整检查结果记录在 [实施状态](implementation_status.md)。浏览器验证理由为空不能提交、批准/拒绝/要求修订、关闭道路禁止批准、批准回读与刷新恢复、已处理项移出队列。

证据：[审核表单](evidence/a07-review-form.png)、[道路关闭的审核表单](evidence/a07-blocked-review.png)、[批准后的 eligibility](evidence/a07-approved.png)。开发时修改 SessionContext 模块触发过一次 Vite 热更新上下文失效，完整刷新恢复；正式构建通过。后端源码修改后须重启服务。

REQUEST_REVISION 当前保存反馈和状态。B 首版、自动修订执行、真实四场景联调仍未提供；日期/人数/预算变化必须由 Camper 建立并重新确认需求，审核不能暗改需求。A-08 最终化、其他成员复核、Jira 记录、干净环境端到端验收尚未完成。此阶段可称 A 侧审核实现与自检，不能称全组 Done 或真实 Agent 验收。

本轮仅本地开发与提交，尚未推送 GitHub、创建 PR 或运行本轮远端 CI。
