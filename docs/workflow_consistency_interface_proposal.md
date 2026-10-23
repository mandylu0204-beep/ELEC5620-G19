# 出行系列与业务一致性：精确接口提案

日期：2026-10-22（Australia/Sydney）。基线：`fix/display-issues` / `74dfad7`，开始时工作区干净。

## 状态与分工确认

**本地实施契约 1.0，尚未经过 A/B 联合复核；不是已部署的接口。**
核对基线时最高数据库迁移编号为 10；用户随后明确确认本轮可使用 11，由本轮实现。
迁移 11 已加入代码，仅在隔离测试数据库执行；未升级运行中的个人数据库。A 合并前应核对其他分支未并行占用 11，并联合复核删除、审核替代语义。
不新建第二套 root/trip_id，不改共享 Agent DTO 1.0、旧输入指纹或冻结安全文本协议。

本轮接通系列接口、后继请求／方案、资料 revision／差异和审核任务分离。按用户后续要求，撤回模型输出中文化，保留原有 Prompt 和组件身份。
全部沿 Database.initialize 正式迁移，不在业务函数中隐式建表，也不占用其他编号。

## 1. 修改前核对的业务基线（不代表修改后的限制）

- `RequestRepository.begin_analysis` 保存 profile_revision 和 profile_snapshot；confirm 在事务内再次核对 revision。
- `Repository.begin_run` 从已确认 request 取资料。REASSESS 保留这个资料快照，不采用用户当前个人资料。
- checkpoint 从 runs.confirmed_context 读取，不从 profiles 获取恢复输入；保留原产物、回执、heartbeat、lease 和审计。
- `ReviewService.queue/detail/submit` 当前接受 ESCALATED、BLOCKED、REVISION_REQUIRED；审核详情范围包含不能批准的方案。
- `SqlitePersistencePort.decision` 用正式评估／证据和精确 review 计算 eligibility，禁止审批解除硬性缺口。不能用 display_status 替代。
- 现有 `final_index` 没有 plan_id，只适用于单方案。系列聚合之前必须补齐所有引用的所属 plan_id。
- 当前 ReplanSession 的草稿创建不支持命令回执；不能宣称它已解决后继创建的丢回执。

## 2. 唯一系列身份与存储边界

服务端数据（名称待评审后冻结）：

| 数据 | 字段和约束 |
| --- | --- |
| trip_series | trip_series_id、owner_id、current_plan_id（可空）、revision、deleted_at、created_at；当前方案必须属于本系列且同 owner |
| plan_series_membership | plan_id 唯一、trip_series_id、predecessor_plan_id（首方案为空）、created_at；关联不可变，禁止跨 owner/系列/循环 |
| successor_request_origins | request_id 唯一、trip_series_id、predecessor_plan_id、精确来源版本/run/revision、创建时 series revision；不是新的根身份 |
| successor_commands | owner_id + command_key 唯一、input_hash、request_id、最初回执；不可变 |
| 系列任务替代记录 | 明确记录旧任务被哪个 plan/run/version 取代；不改旧评估、route、审批、最终快照 |

逻辑设计已由 migration 11 实现：SQL 表为 trip_series、plan_series_members、successor_requests、successor_commands、series_delete_commands、series_replacements。A 联合复核事务、迁移与历史兼容；对外只有 trip_series_id 一套系列身份，SQL 内主键列名 id 不构成第二套根身份。

新建独立出行在首次 PLAN 的事务中创建新系列。历史未关联方案保持独立读取；只有显式创建后继时才把来源作为该系列首方案登记。
不按日期、标题、目的地、profile_id 或 request_id 猜测合并；不批量修改旧快照或删除旧数据。

## 3. 后继请求命令（不调用模型）

`POST /api/v1/plans/{plan_id}/successor-requests`，CAMPER + 本人方案 + CSRF：

```json
{
  "command_key": "UUID，16–128 字符",
  "expected_series_revision": 0,
  "expected_current_version_id": "version-id 或 null",
  "expected_version_revision": 0,
  "expected_active_run_id": "run-id",
  "expected_run_revision": 4
}
```

- series revision 0 只用于尚未关联的历史来源；版本不存在时两个版本字段均 null。
- 事务校验来源归属、未删除、是系列当前方案；run 必须已结束，版本/run/系列 revision 必须精确一致。
- 由服务端复制来源已确认的 raw_text 和 requirements，新请求仍为 DRAFT，不接收客户端伪造 owner、系列或旧确认上下文。
- 首次需要时登记系列首方案，但**不移动当前方案指针**。同一来源可有多个预览草稿，只有一个能以相同系列 revision 启动。
- 回执、请求和关联同事务写入；相同 key/相同输入回读同一 request_id，不同输入为 IDEMPOTENCY_CONFLICT。
- 回执重试先检查所有权和删除访问边界。来源或回执目标已删除时不从回执重新暴露内容，也不创建替代请求。
- 返回现有请求读取内容，并增加只读 `trip_series_id`、`predecessor_plan_id`、`series_revision`、`source_profile_revision`、`source_profile_snapshot`、`source_requirements`。精确 source_context 保持服务端内部绑定，不把内部完整运行配置放进公开响应。
- 独立出行仍走 POST /requests，没有 source 参数，明确标为“新建独立出行”。不得在普通请求 API 上接受任意系列 ID。

## 4. 预览、确认与启动

继续使用 `/requests/{id}/interpret`、`/confirm`、`/plan`，不另造第二套确认协议。

预览增加／明确：`profile_revision`、`profile_snapshot`、来源 `profile_snapshot` 和分区差异。
差异是客户端展示事实，不是正式评估、风险结论或授权依据。删除／新增装备直接展示旧/新列表，不按自定义名称推断行身份。

确认：沿用现有 expected_revision + command_key + acknowledged。在事务内再次核对当前个人资料 revision、数据和演示上下文。
资料变更为 VERSION_CONFLICT：使勾选失效，要求显式重新载入差异；不能自动采用最新值并继续规划。
已成功确认后的资料变化不修改该确认上下文；未知确认回执的重试沿用原 key，服务端优先回读原回执。

对后继请求，confirm 和 plan 还需核对来源仍为系列当前方案、未删除、精确版本/run 未变化。
plan 的既有命令回执、scope、run、系列新方案成员和 current_plan_id 更新必须在同一事务提交，并递增系列 revision。
并发独立 command 只允许一个后继成为当前，另一操作返回 STALE_CONTEXT；同 key 丢回执后仍返回同一 plan/run。
dispatch 仅对返回的持久化 run 工作，失败仍可读取和恢复；恢复不复查最新 profiles 作为运行输入。
来源仍有活动运行时不能启动后继；后继已启动后，来源不能再 REVISE/REASSESS/retry/finalise/submit review 改变当前任务资格。
读取和历史回放仍允许。新运行失败或无匹配不自动退回旧方案，不把旧最终当作新运行结果。

所有系列写入口使用 BEGIN IMMEDIATE，并在**同一事务**中复核当前指针；不能只依赖前端传值或查询后的异步检查。

## 5. 系列读取与列表

新增 `GET /api/v1/trip-series` 和 `GET /api/v1/trip-series/{trip_series_id}`，只返回本人未删除系列。
列表每系列一项，历史孤立方案作为单独项，使用明确判别字段区分，不推测关联。

```json
{
  "trip_series_id": "series-id",
  "revision": 2,
  "current_plan": {"plan_id": "new-plan", "active_run_id": "new-run"},
  "latest_run": {"plan_id": "new-plan", "run_id": "new-run", "status": "RUNNING"},
  "history": [{"plan_id": "old-plan", "predecessor_plan_id": null}],
  "last_final": {"plan_id": "old-plan", "final_id": "old-final", "run_id": "old-run", "is_current": false}
}
```

示例只列身份字段，不是完整 response schema。当前完整方案继续通过既有按角色投影读取。
history 和 last_final 的 SQL 必须过滤 plans.deleted_at，系列删除也必须使子入口不可读。
跨方案最终入口始终 `/plans/{last_final.plan_id}/finals/{last_final.final_id}`。
问题列表、当前卡片和正式资格必须指向同一个当前 run/version 的两份评估；旧最终只作为单独链接。
`display_status` 继续仅作展示，不参与上述当前关系、审批、运行路由或最终化守卫。

## 6. 删除语义（需要 A/B 明确确认）

- 删除历史方案：原 DELETE /plans/{id}，逻辑删除该方案；不改当前指针，不暴露该方案的运行、最终、回执或诊断。
- 删除当前方案：拒绝尚有活动 run 的删除；逻辑删除当前，current_plan_id 清空，系列 revision 增加，系列成为只读历史集合。不自动提升任何旧方案，不恢复旧待办。
- 删除整次出行：新增 `POST /trip-series/{id}/delete`，提交 command_key + expected_series_revision。若任意成员有活动 run 则拒绝；否则同事务逻辑删除系列和全部成员，写幂等回执。原有不可变审计内部保留。
- 所有旧读取／写入入口都检查系列删除和成员删除，不只从列表隐藏。已删除来源不能再被后继创建复活。
- 删除回执重试可返回无内容的同一成功结果，但不得返回已删除历史内容。

## 7. 风险审批与修正／协助分离

新政策身份建议 `current-evidence-risk-review-1`，不是 display_status，也不是系列永久审核锁。

- 待审批：系列当前、完整评估、运行结束、有真正人工判断触发，且除风险审核外没有待用户补充、修订、硬性 blocker 或必要证据缺项。
- 缺项／修订／证据缺失：进入当前方案修正事项；如需 Founder 查看另设只读协助列表，不能借协助列表 APPROVE。
- 审核命令继续绑定 VersionContext、run、两份 assessment IDs、version/run revision；增加服务端系列当前检查（不由前端隐藏旧任务）。
- 旧审核记录原样保存；后继再次触发风险审批时重新审批。不触发且正式评估通过时按正常用户确认最终保存，标明旧任务被新检查取代。
- 系列指针更新时事务化记录替代；旧页面晚到审核和旧回执不得授权新结果。独立新建请求也必须重新执行同一套正式规则和审批政策。
- 继续保留所有必要证据／装备／费用／道路的 eligibility 守卫，不允许 APPROVE 清除 blocker。
- 不加“送审后必须人工结案”的永久锁；若 A 的产品政策要求该锁，先说明差异再另行确认。

## 8. 装备政策审计（不重写算法）

已存在能力：

- 帐篷以 item_key=tent 聚合确认数量 × 每顶 capacity_persons 得到 person_space；车辆以确认数量 × 每辆座位数计算运力。
- 同类规则取最大需求并合并 essential/mandatory/source，不按 label 推断类别或容量。
- `_available` 保留未知／未确认／单位错误；已知确认容量已经满足需求时，不完整的额外行不会凭空产生额外容量或抹除已知容量。
- GearItem.essential、severity_if_missing、allowed_methods、DEFER_OPTIONAL 已支持可选项不采购；缺口仍保留，不代表免费库存。
- 饮用水、急救包等是否必需及其触发、数量沿封存规则执行，没有通用忽略按钮。
- LogisticsToolset.result 保留原规则的装备事实、mandatory_blockers 和 clarifications；模型建议不能把未落实安排变成 PASSED。
- 个人资料仍可保存未知数量、容量和未核实状态；最终要求在正式评估／eligibility 层检查，不上移为资料必填。

真正缺少的不是第二套容量算法：系列采用资料的绑定、当前审批任务转换，以及如未来要求“实际共用安排”时所需的结构化新事实政策。
第一阶段不增加共用豁免、不改封存规则或旧数据；需要新增政策必须单独定义版本、适用数据版本和回归样例。

## 9. 模型输出语言：已撤回本轮改动

按用户后续要求，不再增加“模型必须输出中文”的指令。规划与物流 Prompt 及组件版本恢复为本轮改动前的基线；页面既有中文展示保持不变。
不翻译或改写历史记录、不改旧哈希、不修改安全文本协议，不新增模型调用，不增加 token/超时/重试。
每日建议等有界 schema 是下一次独立提案，不能混进本轮接口冻结。

## 10. 阶段与验收矩阵

1. **接口阶段**：用户已授权迁移 11；本文和严格 HTTP input models 作为本地接口契约，待 A 联合复核。
2. **系列阶段**：后继命令、持久化／current CAS、幂等回执、系列读取和跨方案最终引用；旧孤立数据不聚合。
3. **资料阶段**：预览 revision／差异、失效勾选、显式采用、接线后继接口；普通保存／刷新／取消不 dispatch。
4. **审核阶段**：当前风险审核队列、修正／协助分离、旧审批与待办替代、所有写入口系列守卫。
5. **政策回归**：混合容量、自定义名、单位、未知值、optional/essential；不改封存数据。
6. **语言改动撤回**：保留原规划／物流 Prompt 和身份，历史内容原样读取，不新增中文输出要求。
7. **最终组合验证**：最终代码上从头运行后端全量、前端全量、导出 schema、类型和构建。首次全量与局部复测不能相加算通过。

必须新增用例：两个 command 竞争后继、同 key 丢回执、预览取消、profile revision 竞争、跨 owner／已删除来源、独立出行不合并；当前/历史/整次删除；旧最终所属 plan_id；新旧审核转换和晚到审批；原快照字节/哈希不变；恢复复用旧输入和已保存步骤。
权限检查直接读原始 HTTP JSON，不用内部审计辅助；方案／run／request／final 普通读无 trace/token/config，Founder 诊断维持现有授权。

## 交接请求

本轮已实现并使用用户批准的迁移 11。请 A 合并前核对编号不冲突，重点复核 current 删除不回退／系列只读历史语义、当前版本风险政策而非永久审核锁，以及 endpoint/字段/事务边界。
独立的“保留原行程但采用新个人资料只重评”未实现，现有 REASSESS 仍使用原确认资料；丰富每日建议 schema 也未实现。两者都需后续独立冻结，不得借本轮宣称已支持。
最终测试结果和实际未完成范围见 workflow_consistency_handoff.md，不以本接口文件替代验收报告。

后续统一更新入口、读取字段与关联费用投影见 [连续更新交接](trip_update_flow_handoff.md)；不新增迁移编号，不改变当前方案切换时机或冻结安全协议。
