# CampMate AI 开发 B 接口交接

> 本文为 1.0 接口冻结时的设计记录；其中实施状态描述保留当时语境。当前代码和验证进度见 [实施状态](implementation_status.md)。

日期：2026-10-08。契约版本：1.0。用户已转交 B 的审阅反馈，D-01 至 D-06 与风险路由按反馈冻结为实现基线。B 当前没有 Agent、Adapter 或 workflow 代码，六个入口是计划接口，尚无运行样例或联调结果。本助手没有向成员发送消息。

本交接针对 Stage 2 的 React、FastAPI、SQLite 原型。业务来源仅使用当前 synthetic 数据包。详细背景见 [数据库与接口设计](developer_a_contract_draft.md)，已有数据问题见 [数据检查报告](synthetic_data_review.md)。A 提供的共同 contracts 位置、端口签名和异常格式见 [共享契约实施说明](shared_contracts_spec.md)；实施任务见 [开发 A 任务清单](developer_a_backlog.md)。新增签名是 A 本轮提供的设计，尚无代码，未声称 B 已逐项复核这些新增细节。

## 1 已确认的六项约定

| 编号 | 冻结约定 | 对 B 的影响 | 当前状态 |
| --- | --- | --- | --- |
| D-01 | 前端只调用一个 FastAPI；A 负责权限、数据库、事务及最终化；B 通过持久化端口保存产物 | 不另建用户、方案或审核数据库，不从 Agent 直接更新 FINALISED | B 已接受 |
| D-02 | 两晚为 duration_nights=2、duration_days=3，end_date=start_date+2；只给天数或日期冲突先澄清 | 营地按晚、食物和水按约定天数计算 | B 已接受 |
| D-03 | 金额为整数 cents，币种 AUD；数量用 Decimal；费用行 ROUND_HALF_UP 到分，总计为行金额之和；未知金额为 null | 原 CSV 的 AUD 在 Adapter 边界转换，不用 0 掩盖未知金额 | B 已接受 |
| D-04 | 版本状态、评估 outcome、审核决定分开；HUMAN_APPROVED 只作审核事件，不作版本状态 | APPROVE 保存后由 A 重算 eligibility | B 已接受 |
| D-05 | A 登记 run_id 和 input_fingerprint，B 原样返回；证据变化开启新 run | Fingerprint 包含版本内容、确认需求、Profile 快照和本次数据上下文；旧审核不自动沿用 | B 已接受 |
| D-06 | 固定 demo clock=2026-10-08，通过配置传入；来源日期、场景有效期及行程覆盖范围分别检查 | 必要证据缺失、过期或冲突不能 PASSED | B 已接受 |

D-06 的固定时钟已确认，用它检查演示请求日期。安全数据有效性仍须看明确的适用营地、覆盖日期及 AVAILABLE / MISSING / STALE / CONFLICTING 状态，不能只靠固定时钟通过检查。

用户输入明确的两天不能直接当作两晚。本文的晚数规则适用于过夜露营；如果用户只给天数，先澄清，再展示明确的开始日期、结束日期、天数和晚数供确认。

## 2 共享数据类型

字段名称统一 snake_case。必填表示调用方必须提供该字段；可为空不等于可以缺少字段。列表无元素时为 []，未知日期或数值为 null。输入中保留 invalid_fields，不能将无效数据修饰成合法数值。

| 类型 | 主要字段 | 规则 |
| --- | --- | --- |
| Provenance | source_type、source_name、source_date、demo_only | 固定为 SYNTHETIC、CampMate Synthetic Demo Dataset v1、2026-10-07、true |
| DemoContext | schema_version、mode、demo_today、dataset_version | schema_version=1.0、dataset_version=v1；运行模式为 stub / deterministic_demo / agent，stub 是 A 开发支架 |
| ProfileSnapshot | profile_id、group_size、experience_level、equipment、transport、accessibility_requirements | 确认请求时保存快照，之后修改 Profile 不影响历史 |
| EquipmentItem | item_key、label、quantity、unit、capacity_persons、confirmed | unknown 数量或容量为 null；B 不从 family tent 猜容量 |
| Transport | transport_type、vehicle_count、estimated_km、assumptions | 数量与路程未明确时澄清，或显示来源明确的演示假设 |
| TripRequirements | destination、start_date、duration_nights、end_date、duration_days、budget_cents、currency、preferences、mandatory_constraints | 确认前允许必要字段为 null；确认后必须通过校验 |
| Clarification | field、question、reason | 只针对输入缺失、歧义或冲突；补充后重新解析和校验 |
| FieldError | field、code、message | 区分 MISSING、INVALID、AMBIGUOUS、CONFLICTING、UNSUPPORTED |
| VersionContext | plan_id、plan_version_id、run_id、input_fingerprint | A 生成或登记，B 在版本产物中原样返回 |
| SourceRef | dataset_file、record_id、provenance、valid_from、valid_to | 适用日期可为空；必要有效期未知时报告不确定性 |

input_fingerprint 标识不可变的版本内容、确认需求、资料快照以及本次数据上下文。它不等于 UI 的 expected_revision。UI 的 revision 随受控状态或记录更新变化；不能因为物流结果保存使 UI revision 增加，就把同一合法 run 的后续安全结果误判为陈旧。

数量允许小数，例如公里数，用 Decimal 计算，不能强制变成整数。quantity 的 JSON 形式为十进制字符串。subtotal_cents = quantity × unit_price_cents，按 ROUND_HALF_UP 舍入为整数分；total_cents 为已舍入行金额之和。assumptions 中记录估算，未知数量或金额返回 null 和缺失说明。

## 3 B 提供的六项能力

函数名是建议的集成入口，本文没有创建函数或实现代码。B 可在内部继续拆分三个 Agent。

### 3.1 interpret_request

输入：raw_text、profile_snapshot、explicit_fields、demo_context。

输出：extracted_requirements、clarifications、field_errors、assumptions、source_refs。required 字段缺失时保持 null 并提出问题。输入完整时由 A 展示摘要，仍等待 Camper 确认。

expected_request_status、expected_* 和原测试 missing_fields 不传给实际解析器。request-06 原文“Zero campers”不能被 profile-a 的两人默认值覆盖，必须暴露无效输入或冲突。request-03 原文没有时长，不能从测试标注自动获得两晚。

### 3.2 recommend_campsites

输入：confirmed_requirements、profile_snapshot、demo_context。

输出：search_outcome（MATCHES / NO_MATCH）、candidates、excluded_candidates、assumptions、source_refs。每个候选含 campsite_id、rank、reasons 和 material_uncertainties。

硬约束不满足时排除；软偏好参与排序。NO_MATCH 是完整检索没有匹配项，数据加载失败是技术错误，两者分别返回。推荐不是订位或安全放行。

### 3.3 generate_or_revise_itinerary

输入：confirmed_requirements、profile_snapshot、recommendations、previous_version（首次为 null）、feedback、demo_context。

输出：itinerary_entries、selected_campsite_ids、revision_reason、assumptions、source_refs。每个行程条目含 entry_kind、start_at、end_at、campsite_id（旅行或活动条目可空）和 description。

A 校验时间顺序、晚数及已确认硬约束。内容有效时通过持久化端口创建版本并获得 VersionContext，再开始评估。生成调用开始时尚无已保存版本，不能强制此阶段带新 plan_version_id。

如果 B 建议改变预算、日期、地区或强制偏好，返回 requested_requirement_changes，A 展示并让用户重新确认；B 不直接改变已确认需求。

### 3.4 assess_gear_and_logistics

输入：version_context、saved_itinerary、confirmed_requirements、profile_snapshot、demo_context。

输出：version_context、gear_checklist、transport_feasible（未知为 null）、cost_breakdown、total_cents（无法支持时为 null）、budget_difference_cents（total-budget，正数为超预算）、outcome、mandatory_blockers、clarifications、assumptions、uncertainties、source_refs。

清单条目含 item_key、required_quantity、available_quantity、missing_quantity、unit、capacity_requirement、arrangement_status 和 essential。未确认的租借安排不能直接算作已经拥有的装备。

费用条目含 category、item_key、quantity、unit、unit_price_cents、subtotal_cents、source_ref、assumption。提供数据支撑的五类费用：营地、交通、食物、饮水、新增装备。缺失费率或数量时返回具体缺失内容，不使用 0 掩盖未知费用。

缺失关键装备可要求 Revision，但当前版本的 blocker 要保留。帐篷、睡袋等重复规则应按同一 item_key 合并缺口，不重复租赁计费。合计不一致由 A 拒绝接收成功结果。

### 3.5 assess_safety

输入：version_context、saved_itinerary、confirmed_requirements、saved_logistics_assessment、scenario_context、demo_context。

scenario_context 含原场景证据及适用营地与日期。B 负责 Adapter 选择或装配场景；A 校验返回来源关系。模板重用必须明确记录 template_id 与新的演示适用范围，不能静默改动原始记录。

输出：version_context、risk_level、confidence、data_quality、hazards、mandatory_blockers、recommended_actions、outcome、requires_human_review、assumptions、uncertainties、source_refs。

weather、fire 是 Evidence 对象，含 summary、source_date、status、valid_from、valid_to。road_access 同时区分数据质量和通行状态；原数据 OPEN / CLOSED / UNKNOWN 是通行状态，不能与 AVAILABLE / MISSING 混用。

severity、confidence 和 expected_outcome 作为测试标注隔离；实际结果应按证据与明确规则产生，不直接复制预期。原场景只有文字证据，数值温度、风速等未提供，不得虚构成精确数值。

### 3.6 orchestrate

输入：command、run_id、confirmed_context、previous_version_context、persistence_port、demo_context。

推荐执行顺序：推荐、生成草稿、保存版本、装备及物流、保存评估、安全、保存评估、路由。修订创建新内容版本后重跑必要检查。

每个阶段通过 persistence_port 记录进度及产物。最终化由 A 的守卫和事务执行，B 只能请求重新计算 eligibility，不能直接将 status 写成 FINALISED。

## 4 A 向 B 提供的持久化端口

| 能力 | B 提供的数据 | A 保证 |
| --- | --- | --- |
| load_confirmed_context | request_id 或当前 run 标识 | 用户确认、快照及权限上下文真实有效 |
| save_recommendations | request_id、候选和来源 | 关联已确认请求，结果可追踪 |
| append_plan_version | plan_id、expected_current_version_id、new_content、request_id、reason、command_key | 版本与当前指针原子更新，旧内容保留 |
| save_assessment(LOGISTICS) | VersionContext、物流结果及其中的清单 | 同事务保存清单与评估，关联当前运行的已保存版本 |
| save_assessment(SAFETY) | VersionContext、结构化结果及依赖的物流 assessment ID | 不混合不同 run，保存来源和 blocker |
| report_stage | run_id、stage、状态和错误 | 持久化进度，不因技术错误产生假成功 |
| route_assessed_version | VersionContext、route、reason | 校验合法状态迁移，不允许陈旧结果推进当前版本 |
| load_review_result | plan_version_id、run_id | 只返回适用于当前证据的有效审核决定 |
| evaluate_eligibility | plan_version_id、run_id | 核对全部必要条件，返回 blockers 与允许动作 |

这些能力只有后端内部可调用。数据库事务不能跨越耗时的 Agent 推理；产物生成完成后短事务保存并重新检查上下文。相同 command_key 和内容的公开命令返回原结果；内部阶段写入用 A 登记的独立 write_key 去重。具体签名和事务边界以 [共享契约实施说明](shared_contracts_spec.md) 为准。

## 5 推荐状态映射

| 产物或事件 | PlanVersion 的处理 | 最终化 |
| --- | --- | --- |
| 两项必要评估通过且无需审核 | ELIGIBLE_FOR_FINALISATION | 守卫再检查后可保存 |
| 可修复问题 | REVISION_REQUIRED | 当前版本不可最终化，新版本重新评估 |
| 高风险、未解冲突、证据不足 | ESCALATED | 等待足够信息和必要审核 |
| 禁止条件或不可执行的当前计划 | BLOCKED，或返回 mandatory revision | blocker 未解决时不可最终化 |
| Founder APPROVE | 保存 decision=APPROVE 审核记录，由 A 重算 eligibility；不增加 HUMAN_APPROVED 版本状态 | 人工决定不能补齐缺失证据或绕过 blocker |
| Founder REQUEST_REVISION | REVISION_REQUIRED | 保存新版本再评估 |
| Founder REJECT | REJECTED | 不可最终化 |
| 最终保存成功 | FINALISED | 返回已保存最终方案 |
| 生成、交接或保存失败 | 保留最后有效业务状态，run 报告可恢复错误 | 不宣称成功 |

风险路由已确认：强制 blocker 阻止放行；高风险、低置信度或未解冲突进入审核；其余可修复问题返回修订。高风险版本可以同时提出修订建议，但不得跳过升级要求。outcome、版本路由与 finalisation blockers 分开表达；可修复 blocker 可以对应 REVISION，但当前版本始终不能最终化。

safety-05 的 campfire blocker 可通过新版本取消营火解决，当前版本仍阻止放行。safety-09 若按实际证据和规则确实触发 HIGH，expected_outcome 应由 REVISION 调整为 REVIEW，并提供修改建议。原始包尚未改动；变更应在独立修订 fixture 中记录，不能在实现中隐式例外。

## 6 联调场景与首轮范围

首轮先交付 I-01 正常流程、I-03 超预算、I-04 安全证据缺失、I-06 道路关闭；其他场景后续补齐。以下 fixture 尚待建立，联调均未执行。来源数据不足的字段需在独立 fixture 中明确补充并记录假设，不能直接把预期输出当成输入。

| 场景 | 设置 | 检查结果 |
| --- | --- | --- |
| I-01 正常流程 | profile-a、request-01、demo-pine-camp、safety-01；补齐明确装备数量、行程覆盖日期和交通估算 | 确认前不规划；确认后完成物流和安全；最终保存后读取同一版本 |
| I-02 缺失信息 | request-02；用户补充 destination | 澄清后显示新摘要；确认当前摘要才开始规划 |
| I-03 超预算 | profile-b、request-08、demo-lake-meadow；明确两晚和费用单位，另提供可用于修订的低成本替代方案 | 营地费本身 AUD 110 超过 AUD 50；返回修订并阻止放行；替代方案仍需完整计算和复评 |
| I-04 缺失安全证据 | 独立场景 ID、demo-river-flat、有效范围和具体缺失项；记录 safety-02 模板来源 | 不自动 PASSED；Founder 不能在必要证据仍缺失时放行 |
| I-05 禁止营火 | request-12、demo-ridge-lookout；装配覆盖本次行程的 no-fire 场景 | 旧版 blocker 保留；取消营火需用户同意相关需求变化；新版本复评 |
| I-06 道路关闭 | 明确 demo-cloud-gully 与 safety-06 的适用日期和版本 | 人工批准和 finalise 均不能绕过关闭限制 |
| I-07 旧审批与陈旧任务 | V1 已产生评估；创建 V2，再提交 V1 审批及迟到评估 | 历史保留；当前指针和 V2 状态不被推进 |
| I-08 保存失败及重试 | 合法 eligibility，注入最终保存失败，恢复后重试同一命令 | 失败不产生 FINALISED；恢复后只保存一次 |
| I-09 数据隔离 | 两个 Camper 和一个 Founder | Camper 跨用户读取/写入失败；Founder 只能执行授权审核 |

正常 fixture 仍需核对各项 gear rule。profile-a 的“mostly complete gear”说明不等于所有装备已经满足，不能为了打通成功路径忽略睡垫、雨具或其他触发规则。

## 7 文件所有权与交付位置

应用目录定为 `Stage2/campmate_app`，共同契约位置为 `Stage2/campmate_app/backend/app/contracts`，与原始数据包分开；代码目录尚未创建。目录与文件职责详见 [共享契约实施说明](shared_contracts_spec.md)。

| 目录或文件 | 主负责人 |
| --- | --- |
| frontend、启动脚本、Compose、CI、安装运行 README | A |
| backend/app/api、auth、models、repositories、application | A |
| backend/app/agents、adapters、workflow | B |
| backend/app/contracts | A 提供端口、异常与应用侧 DTO；B 提供 Agent DTO/schema；A 负责统一合并与版本管理 |
| 认证、权限、数据库、审核与最终化测试 | A |
| Agent、Adapter、费用、风险与修订业务测试 | B |
| 端到端测试与演示 fixture | A/B 与测试负责人共同检查 |

数据来源路径通过配置传入 B Adapter。部署包包含原始数据和需要的独立修订 fixture；代码不依赖这台电脑的绝对路径。

## 8 B 确认记录及待交付项

确认来源：用户于 2026-10-08 在当前对话转交 B 审阅反馈。已确认 D-01 至 D-06、六个入口与风险路由。B 表示无现有实现，首版先交付 schema、Adapter 及四个场景的规则流程，随后接入 LLM 与完整修订流程。

B 的 deterministic_demo 将根据实际输入、数据和明确规则计算，expected_* 独立于 Agent 输入；未知数量、容量、路程或费用返回具体缺失信息，不擅自补值。实际调用入口、运行输入输出样例及联调结果在实现后提供。

A 本轮补交：共享 contracts 位置、持久化端口签名、异常格式、数据链接及任务验收清单。原始包见 [synthetic 数据入口](../data/synthetic_demo/FINAL_VALIDATION_REPORT.md)，具体文件清单见 [共享契约实施说明](shared_contracts_spec.md)。数据语义问题以 [独立检查报告](synthetic_data_review.md) 为准，不能仅凭原验证报告宣称联调通过。

A 以后可使用明确标注的 stub 推进前端与数据库；stub 不算 Agent 实现或 Agent 能力验收证据。当前未开始应用代码编写。

首次提交 DTO 与规则时，B 应检查本轮新增端口参数及异常结构是否足够；如需兼容性变更，先更新契约版本与变更记录再修改调用方，不能让字段定义在双方代码中分叉。
