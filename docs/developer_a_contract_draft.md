# CampMate AI 开发 A 数据库与接口草案

> 本文为 1.0 接口冻结时的设计记录；其中实施状态描述保留当时语境。当前代码和验证进度见 [实施状态](implementation_status.md)。

日期：2026-10-08。设计版本：1.0。状态：D-01 至 D-06 与风险路由已按用户转交的 B 反馈确认，尚未实施。React、FastAPI、SQLite 来自五人分工；表结构和公开 HTTP API 是 A 的实施设计，尚无运行服务。具体交接字段与调用边界见 [开发 B 接口交接](developer_b_handoff.md)，新增端口签名见 [共享契约实施说明](shared_contracts_spec.md)。保留当前文件名，便于已有链接继续使用。

目标是将现有 synthetic 数据用于用户界面、应用服务、版本记录、权限和最终交付，同时保留 B 的 Agent 和业务工作流职责。数据问题详见 [数据检查](synthetic_data_review.md)。

## 1 责任和调用边界

采用一个 FastAPI 应用作为前端入口。A 管理 HTTP 路由、认证授权、数据校验、持久化和最终化守卫。B 提供可由应用服务调用的 Agent 与 Orchestrator 模块，以及替换数据源的 Adapter。

| 事项 | A | B |
| --- | --- | --- |
| Request | 输入、澄清与确认界面，结构校验，snapshot 保存 | 原文提取、缺失识别、问题生成 |
| Recommendation / Itinerary | 查询及展示，保存推荐和新版本 | 过滤、排序、解释、行程生成 |
| Assessment | 校验返回结构、关联版本、保存并展示 | 装备、交通、费用及安全评估 |
| Revision | 原子保存新版本与 current 指针 | 根据当前反馈生成修改内容，重新评估 |
| Human Review | Founder 权限、审核界面、决定及理由保存 | 根据有效决定执行工作流 |
| Finalisation | 当前版本与所需证据守卫，事务保存，展示 | 提供业务判断及当前版本结果 |

B 通过 A 提供的 repository/application-service 接口保存业务产物。公开写接口不能允许浏览器伪造 PASSED、审批人、owner、当前版本或 Finalised 状态。A 生成身份与记录标识，并验证 B 返回结果对应本次运行的版本与上下文。

若 B 已有独立服务，可以将内部调用适配为服务 API，但应继续使用同一份契约和同一个持久化责任边界。

## 2 数据导入和归一化

保留原始包，导入时建立映射，不修改原文件。

| 原始字段或内容 | 拟议运行时处理 |
| --- | --- |
| snake_case 字段 | API、B 模块和数据库统一使用 snake_case |
| CSV true / false | 严格转换为 boolean，不以非空字符串表示真假 |
| 分号列表 | 对具体字段转数组，例如 facilities、risk_tags、restrictions |
| unknown / 空值 | 缺失的可选日期和数值用 null，保留对应字段错误和原始值 |
| budget_aud=0 的“未提供预算” fixture | 根据输入含义保留缺失情况，不将用户显式输入 0 当作合法预算 |
| 负预算、无效日期 | 输出校验错误，不能保存为已确认请求 |
| 两晚及 duration_days=2 歧义 | 从明确原文和用户确认得到 duration_nights，再派生天数及结束日期 |
| equipment 自然语言 | 原文与标准化条目并存，数量和容量不明确则需要澄清 |
| expected_*、测试标注 | 隔离为测试 oracle，不用于决定实际状态或直接输出结果 |
| source_date | 保留来源日期，与证据有效期和 demo clock 分开 |

装备标准化条目建议包含 `item_key`、`label`、`quantity`、`unit`、`capacity_persons`、`confirmed`。family tent 不自动赋予容量；has_children 不自动换算成儿童人数。预算按整个小组的 AUD 总额确认。

金额持久化使用整数分，API 的计算字段使用对应的 `*_cents`，来源中的 AUD 数值由边界适配器转换；UI 显示 AUD。quantity 用 Decimal，JSON 为十进制字符串；费用行 ROUND_HALF_UP 到整数分，total_cents 为行 subtotal_cents 之和；未知金额为 null 并附缺失说明。B 返回每条费用的 quantity、unit、unit_price_cents、subtotal_cents、source_ref 和 assumption，后端核对合计。

synthetic 标签固定为原包规定的四个值；衍生结果引用这些来源，同时另存生成时间。所有主要页面、Assessment 和 Final Plan 显示原 UI-01 英文声明。

## 3 SQLite 数据模型建议

| 表 | 核心字段与约束 |
| --- | --- |
| users | id、username、password_hash、role、active；username 唯一；角色 CAMPER / FOUNDER |
| profiles | id、owner_user_id、source_profile_id、group_size、experience_level、equipment_json、transport_json、accessibility_json、revision、created_at、updated_at |
| requests | id、owner_user_id、source_request_id、raw_text、structured_json、profile_snapshot_json、status、revision、confirmed_at、predecessor_request_id |
| recommendations | id、request_id、candidates_json、reasons_json、source_refs_json、created_at |
| plans | id、owner_user_id、current_version_id、final_version_id、revision、created_at |
| plan_versions | id、plan_id、request_id、version_number、previous_version_id、revision_reason、content_json、active_run_id、status、revision、created_at、finalised_at |
| gear_checklists | id、plan_version_id、run_id、requirements_json、available_json、missing_json、assumptions_json、created_at |
| assessments | id、plan_version_id、run_id、input_fingerprint、kind、outcome、result_json、source_refs_json、data_quality_json、mandatory_blockers_json、depends_on_assessment_id、gear_checklist_id、created_at；kind 为 LOGISTICS / SAFETY |
| human_reviews | id、plan_version_id、run_id、input_fingerprint、reviewer_user_id、decision、reason、assessment_ids_json、created_at |
| workflow_runs | id、plan_id、plan_version_id、command_id、command_key、input_fingerprint、mode、stage、status、error_json、started_at、completed_at；首次生成内容前 plan_version_id 与 input_fingerprint 可空 |
| workflow_commands | id、actor_user_id、command_key、operation、payload_digest、result_refs_json、status、created_at；actor_user_id 与 command_key 联合唯一，同 key 不同操作或内容返回冲突 |

JSON 存放嵌套行程、清单与解释，主键、归属、状态和版本关联使用明确字段。运行时无需把 Gear Rule、Cost Reference 等所有源文件照搬成用户表；B Adapter 可以从受版本管理的只读数据包加载。

数据库关系要求：

- Profile、Request、Plan 的 owner 由认证上下文确定。
- 版本属于一个 plan；current_version_id 和 final_version_id 必须属于同一个 plan，由事务和关联约束共同校验。
- 同一 plan 的 version_number 唯一，previous_version_id 属于同一 plan。
- 确认后的请求正文和 profile snapshot 不被后续资料修改覆盖。改变已确认约束时生成重新确认的请求记录，再生成新 PlanVersion。
- 新版本的内容不可覆盖旧版本。状态可以按受控流程更新。
- 新评估追加记录；只选择 plan_versions.active_run_id 对应的结果，不混合不同 run 的物流和安全结果。安全结果记录它使用的已保存物流 assessment ID。旧结果留作历史。
- 证据变化或必要检查重跑时 A 创建新 run，登记新的 input_fingerprint，并原子切换 active_run_id。恢复同一输入的技术失败可以沿用未完成 run；已完成 run 不重新写入成功产物。
- HumanReview 记录 run、fingerprint 和实际审阅的 assessment IDs。证据改变或必要检查重跑后，旧批准不能自动应用到新结果。
- 最终化与 final_version_id 更新在同一事务中完成；失败全部回滚，保留原有效记录。

原始 profile-a 至 profile-e 是演示资料 ID，不是登录凭证。种子配置单独绑定认证用户。至少两个 Camper 加一个 Founder，密码只在开发配置中提供，数据库保存 hash。

## 4 状态和守卫建议

### Request

`DRAFT → ANALYSING → NEEDS_CLARIFICATION / UNSUPPORTED / AWAITING_CONFIRMATION → CONFIRMED`。

无效值返回具体字段错误并允许修改。客户端提交当前 request revision 才能确认；完成所有字段校验和支持地区校验后，记录明确的用户确认事件。

原数据的 REJECTED 可以作为无效 fixture 的预期分类，不强制将所有输入错误建成永久不可修改的请求状态。

### PlanVersion

`DRAFT → ASSESSING → REVISION_REQUIRED / ESCALATED / BLOCKED / ELIGIBLE_FOR_FINALISATION`。

人工批准保存 HumanReview 的 `decision=APPROVE`，可记录 `HUMAN_APPROVED` 审核事件，但它不是 PlanVersion 状态。A 再次核对必要检查和强制约束后才进入 `ELIGIBLE_FOR_FINALISATION`；否则维持相应待处理或阻止状态。拒绝进入 `REJECTED`。保存成功才进入 `FINALISED`，再提供应用内查看。统一使用 FINALISED，适配原包的 FINALIZED，不保留两个同义状态。

Assessment outcome 单独使用 `PASSED / REVISION / REVIEW / BLOCKED`，HumanReview decision 使用 `APPROVE / REJECT / REQUEST_REVISION`。推荐搜索使用候选列表和搜索 outcome，不占用 PlanVersion 的状态枚举。

UI 可以显示 pending、loading、recoverable error 等运行信息，但技术失败不等于业务拒绝，也不会绕过检查。

### 最终化条件

最终化服务在事务中重新读取并校验：

1. 操作者有权访问和推进该方案，目标版本仍为当前版本，预期 revision 没有变化。
2. 请求已确认，行程和必需产物存在，当前有效评估属于该版本及有效上下文。
3. 必要装备、物流和安全检查完整有效，没有未解决的强制 blocker 或修订要求。
4. 不需要人工审核，或当前版本及当前证据已有有效的授权批准。
5. 必要安全信息仍缺失、过期、冲突或不足时不能通过人工批准直接放行。
6. 当前状态满足最终化条件，成功保存最终记录后才改变状态和最终指针。

可修复 blocker 可以返回 REVISION，同时阻止当前版本最终化。已确认路由：强制 blocker 阻止放行；HIGH 风险、低置信度或未解冲突进入审核；其余可修复问题返回修订。缺失、过期或冲突的必要证据不能 PASSED。safety-09 若实际规则输出 HIGH，其预期需在独立修订 fixture 改为 REVIEW，并提供修改建议。

## 5 前端 HTTP API 草案

统一前缀 `/api/v1`。以下只是接口设计，没有创建可调用服务。

| 方法与路径 | 请求要点 | 返回要点 | 角色 |
| --- | --- | --- | --- |
| POST /auth/login | username、password | 会话及用户角色 | 未登录 |
| POST /auth/logout | 当前会话 | 注销结果 | 已登录 |
| GET /auth/me | 当前会话 | id、role | 已登录 |
| GET /profile | 无 owner 参数 | 当前用户资料 | Camper |
| PUT /profile | 资料及 expected_revision | 已保存资料及新 revision | Camper |
| POST /requests | raw_text | request_id、提取草稿、field_errors、澄清问题、status | Camper |
| PATCH /requests/{id} | 明确补充或修改的字段、expected_revision | 更新后的摘要和待确认状态 | 所有者 |
| POST /requests/{id}/confirm | expected_revision、command_key | 已确认请求、plan_id、run_id | 所有者 |
| GET /requests/{id} | 无 | 摘要、确认和处理状态 | 所有者 |
| GET /plans | 无 owner 参数 | 当前用户方案列表 | Camper |
| GET /plans/{id} | 无 | 当前版本、状态、可执行操作 | 所有者或 Founder |
| GET /plans/{id}/versions | 无 | 历史版本和关联产物摘要 | 所有者或 Founder |
| GET /plans/{id}/versions/{version_id} | 无 | 行程、清单、评估、审核和来源 | 所有者或 Founder |
| POST /plans/{id}/revisions | expected_version_id、expected_revision、feedback、command_key | 新 run；保存新版本后返回 version_id | 所有者或 Founder |
| GET /workflow-runs/{id} | 无 | stage、status、产物 ID、可恢复错误 | 所有者或 Founder |
| POST /workflow-runs/{id}/retry | command_key、expected_revision | 恢复同一输入的失败工作；证据变化需另开新 run，不重复保存内容版本 | 所有者或 Founder |
| GET /reviews/pending | 无 | 待审版本及风险摘要 | Founder |
| POST /plans/{id}/versions/{version_id}/reviews | decision、reason、run_id、assessment_ids、expected_revision、command_key | 服务端核对当前 run、证据及权限；已保存决定和后续状态 | Founder |
| POST /plans/{id}/versions/{version_id}/finalise | expected_revision、command_key | 成功保存的最终方案摘要 | 所有者或 Founder |
| GET /plans/{id}/final | 无 | 已保存最终方案及历史属性 | 所有者或 Founder |

确认接口原子保存确认记录并创建一次规划 command；调用 B 可以在事务提交后执行。执行时需要持久化阶段与结果，前端轮询 run，不长期占用页面等待。具体是否同步完成首版短任务可在骨架阶段决定。

Founder 权限按审核职责授权查看方案和评估，不默认允许读取所有用户资料。GET final 可展示历史已保存最终版本，但如果存在新修订，明确标注其版本号及当前修订状态，不能将旧最终方案标成新版本的最终方案。

### 错误返回

错误结构为 error.code、error.message、error.field_errors、error.recoverable、error.allowed_actions、error.context，并附 trace_id。context 内提供适用且有权查看的 request_id、plan_version_id 或 run_id。具体错误码和例子见 [共享契约实施说明](shared_contracts_spec.md)。

HTTP 401 表示未认证，403 表示已认证但无操作权限，404 用于不存在或不应泄露的其他 Camper 资源，409 表示版本/状态冲突，422 表示输入或结构校验失败。依赖失败使用明确的 5xx 错误和恢复提示。前端不依赖英文文本判断错误种类。

重复同一 command_key 返回原命令结果；同 key 携带不同内容应返回冲突。重复最终保存不重复建立最终记录。expected_revision 与版本 ID 在事务中核对，避免点击期间出现新版本而批准旧版本。

## 6 B 模块需要提供的内部契约

| 能力 | 输入 | 输出 |
| --- | --- | --- |
| interpret_request | 原文、profile snapshot、用户明确补充字段、demo context | 提取字段、缺失/无效字段、澄清问题、解释 |
| recommend_campsites | 已确认需求、候选数据、硬约束和软偏好 | 候选 ID、排序理由、排除原因、来源 |
| generate_or_revise_itinerary | 已确认需求、候选、旧版本及反馈 | 行程条目、选择、变更说明、假设 |
| assess_gear_and_logistics | 已保存版本、资料快照、规则和费用来源 | 清单、缺失数量、运输可行性、费用明细、outcome、blockers |
| assess_safety | 当前版本、物流结果、适用营地和日期的证据 | risk、confidence、来源、数据质量、outcome、blockers、措施 |
| orchestrate | command/run 标识、当前上下文、持久化接口、执行模式 | 阶段进度、产物、路由和可恢复错误 |

已保存版本的评估、路由调用及结果必须带 `plan_version_id`、`run_id` 和 `input_fingerprint`。首次生成内容尚未有已保存版本，不强制此阶段提供新版本 ID。input_fingerprint 标识不可变内容和评估上下文，与 UI 使用的可变 expected_revision 分开。结果还包含 schema_version、source_refs、assumptions、uncertainties。A 验证关联与结构，再写入数据库；陈旧结果可以保留历史，但不能推进当前版本。

`deterministic_demo` 根据真实输入、固定数据、时钟和明确规则计算。`agent` 模式仍使用同一份 synthetic 业务来源和相同输出契约；实际模型调用方案由 B 负责确定。A 的 `stub` 仅用于界面和持久化开发，运行及产物均需明确标注，不作为 Agent 已实现的验收证据。不能把测试预期复制输出当作已展示真实推理能力的证据。

## 7 A 的开发顺序和验收

1. 按已确认的 1.0 基线建立共享契约；B 提供首版 DTO/schema，检查 A 本轮新增端口细节。
2. 建立前后端目录、启动脚本、健康检查与 CI 基础。
3. 建立表结构、迁移、seed 用户与资料，验证权限和数据隔离。
4. 实现 Profile、Request、澄清和确认界面，接入 B 的解析接口。
5. 实现工作流状态、方案产物与版本历史，联调正常路径。
6. 实现 Founder Dashboard、修订、阻止最终化与恢复操作。
7. 验证新版本复评、旧审批拒绝、事务失败、重复请求和跨用户访问。
8. 从提交包的干净目录重建数据库、启动服务并运行演示流程。

至少一名其他成员检查后，才能将对应 Jira 项目标记 Done。当前仅完成数据检查与接口文档，以上应用开发和验收均尚未执行。任务拆分和可观察验收条件见 [开发 A 任务清单](developer_a_backlog.md)。

## 8 对齐事项

- A/B：六项约定和路由已确认；待首版 DTO/schema、运行样例以及本轮新增端口细节检查。
- 数据负责人：正确嵌套字典、数量单位、场景有效期、正常流程输入、修正测试上下文。
- Agile 负责人：按正式 FR 编号更新追踪矩阵，保留审阅和决定记录。
- 测试负责人：将角色、输入 patch、版本与评估前置条件、故障注入写成可执行步骤。

已确认事项依据用户转交的 B 审阅反馈记录；本助手没有直接联系其他成员。数据修订、应用实现、测试及其他成员检查仍待完成。
