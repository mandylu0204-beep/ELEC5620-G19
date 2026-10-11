# CampMate v2 数据字典

本包是结构化演示数据及验收 fixture，保留 CSV/JSON 格式。所有字段都以演示数据为准，不能用于真实出行。
原包保留不变；本包使用 v2 来源标识及 revision_date，不静默重命名旧字段。

## 缺失与导入规则

- 必有键与必有业务值分别判断。请求可含 null 以测试澄清流程；必有 ID、元数据与有效业务主键不可空。
- null = 未提供/未知数值或日期；[] = 明确无条目；CSV 空引用 = 不适用。不得统一替换为 unknown、0、[]。
- source_date=unknown 仅保留于原始安全证据来源；不能用它计算新鲜度。observed_at/有效期另外提供。
- CSV 布尔严格接受 true/false，使用 bool('false') 会产生错误；数字明确转 int/float，JSON 表达式明确解析。
- 字段表覆盖所有顶层字段。schemas/*.json 提供实际文件的完整嵌套结构与类型。它们校验 fixture 结构，不代替应用的业务校验或运行结果 schema。
- 运行时只使用 runtime_requests.json / runtime_safety_evidence.json 或 scripts/runtime_inputs.py 的 allowlist。tests/ 下全部为 harness/预期，不能批量塞进 Agent 提示词。

## 独立枚举

| 概念 | 值 | 用途 |
| --- | --- | --- |
| Request status | SUBMITTED, NEEDS_CLARIFICATION, AWAITING_CONFIRMATION, CONFIRMED, REJECTED | 缺信息和等待用户确认是不同状态 |
| PlanVersion status | DRAFT, EVALUATING, NEEDS_REVISION, AWAITING_REVIEW, READY_TO_FINALIZE, FINALIZED, REJECTED, BLOCKED | READY_TO_FINALIZE 需全部守卫成立 |
| Assessment outcome | PASSED, REVIEW, REVISION, BLOCKED | 对某版本的一项评估结果，与版本状态分开 |
| Risk severity | LOW, MEDIUM, HIGH, CRITICAL | Agent 输出；不属于安全输入 |
| Confidence | LOW, MEDIUM, HIGH | Agent 输出；不属于安全输入 |
| HumanReview decision | APPROVE, REJECT, REQUEST_REVISION | 版本 ID、身份、理由必须保留 |
| Evidence data_status | AVAILABLE, MISSING, STALE, CONFLICTING | AVAILABLE 仍需有效期及覆盖范围成立 |
| Road status | OPEN, RESTRICTED, CLOSED, UNKNOWN | 道路状态与 evidence data_status 分开 |
| Test mode | COMPONENT, INTEGRATION | 明确测试上下文的作用范围 |
| Test execution | NOT_RUN | 本次没有应用运行结果 |

NOT_FINALIZED、NO_MATCH、RECOMMENDED、VERSION_CREATED、REVISION_REQUIRED 等仅为测试断言/兼容文字，不能作为同一数据库 status 枚举。
expected_*/missing_fields/invalid_fields/severity/confidence 全部放在 tests/synthetic_oracles.json，或测试 CSV 的 expected_* 列。

## data/synthetic_profiles.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| profile_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| camper_name | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| group_size | integer | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| experience_level | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| has_children | boolean | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| available_equipment | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| transport_type | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| accessibility_requirements | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| notes | string | 必有键 | 非空来源/演示用途/限制说明。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| revision_date | string | 必有键 | 2026-10-09，修订日期。 |
| owner_user_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| children_count | integer | 必有键 | 非负整数；profile-d 的 1 来自 v1 notes，新增候选值需用户确认。 |
| vehicle_count | null / integer | 必有键 | 非负整数或 null；CAR 不等于已知车辆数。 |
| adult_count | integer | 必有键 | group_size - children_count。 |
| normalized_equipment | array | 必有键 | item_key、quantity、unit、capacity_persons、confirmed、original_text、provenance。未知数量/容量为 null。 |
| normalization_notes | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |

## data/synthetic_requests.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| request_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| profile_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| natural_language_request | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| destination | string / null | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| start_date | string / null | 必有键 | ISO 日期或 null；未来日期用 fixture 的 demo_clock 校验。 |
| duration_days | integer / null | 必有键 | duration_nights + 1；缺少晚数时为 null。不是住宿收费基数。 |
| budget_aud | integer / null | 必有键 | AUD 数值或 null。null 表示未提供；负值刻意保留为拒绝测试输入。 |
| preferences | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| notes | string | 必有键 | 非空来源/演示用途/限制说明。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| revision_date | string | 必有键 | 2026-10-09，修订日期。 |
| legacy_duration_days | integer | 必有键 | 原 v1 值，仅供迁移追踪，不进入 Agent 输入。 |
| duration_nights | integer / null | 必有键 | 正整数或 null。来自自然语言中的晚数；request-03 未说明时长，必须澄清。 |
| end_date | string / null | 必有键 | start_date + duration_nights；缺少任何输入时为 null。倒置日期通过测试动作注入。 |
| user_supplements | object | 必有键 | 额外演示用户输入，来源在 supplement_provenance。不是解析预期。 |
| supplement_provenance | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| profile_snapshot | object | 必有键 | 请求时点的资料深拷贝；后续 profile 修改不得改变历史 snapshot。 |
| confirmed | boolean | 必有键 | 业务源请求必须为 false。只有独立 fixture 的显式 CONFIRM 动作/历史确认事件可改变。 |
| transport_parameters | object | 必有键 | vehicle_count 与 estimated_total_vehicle_km；总车公里包含去返程及所有车辆，避免再次乘车辆数。 |

## data/synthetic_safety_scenarios.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| safety_case_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| title | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| campsite_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| scenario_date | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| weather | object | 必有键 | 嵌套证据对象：summary、source_date、status、data_status、observed_at、valid_from、valid_until、temporal_provenance。 |
| fire | object | 必有键 | 嵌套证据对象；data_status 与实体火禁事实分开。 |
| road_access | object | 必有键 | 嵌套证据对象；status=OPEN/RESTRICTED/CLOSED/UNKNOWN，data_status=AVAILABLE/MISSING/STALE/CONFLICTING。 |
| campsite_restrictions | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| risk_tags | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| mandatory_blockers | array | 必有键 | 已知未满足的强制约束输入；不等于 outcome 必须为 BLOCKED。不能被人工批准抹去。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| notes | string | 必有键 | 非空来源/演示用途/限制说明。 |
| revision_date | string | 必有键 | 2026-10-09，修订日期。 |
| template_source_id | null / string | 必有键 | 原安全模板 ID，原模板为 null。复制场景必须使用新 ID 并记录来源。 |
| context_request_id | null / string | 必有键 | 复制安全上下文关联的 Request ID；独立模板为 null。 |
| valid_from | string | 必有键 | ISO 日期；覆盖范围两端均包含，集成场景必须覆盖 start_date 到 end_date。 |
| valid_until | string | 必有键 | ISO 日期；不是 source_date。缺失证据对象内可为 null，STALE 证据必须有早于 scenario_date 的失效日。 |
| evidence_facts | object | 必有键 | 模拟观测输入，不含 severity/confidence/outcome。缺失、过期、冲突天气的数值为 null。 |
| evidence_facts_provenance | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |

## data/runtime_requests.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| request_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| profile_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| natural_language_request | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| user_supplements | object | 必有键 | 额外演示用户输入，来源在 supplement_provenance。不是解析预期。 |
| supplement_provenance | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| profile_snapshot | object | 必有键 | 请求时点的资料深拷贝；后续 profile 修改不得改变历史 snapshot。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |

## data/runtime_safety_evidence.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| safety_case_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| campsite_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| scenario_date | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| weather | object | 必有键 | 嵌套证据对象：summary、source_date、status、data_status、observed_at、valid_from、valid_until、temporal_provenance。 |
| fire | object | 必有键 | 嵌套证据对象；data_status 与实体火禁事实分开。 |
| road_access | object | 必有键 | 嵌套证据对象；status=OPEN/RESTRICTED/CLOSED/UNKNOWN，data_status=AVAILABLE/MISSING/STALE/CONFLICTING。 |
| campsite_restrictions | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| risk_tags | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| mandatory_blockers | array | 必有键 | 已知未满足的强制约束输入；不等于 outcome 必须为 BLOCKED。不能被人工批准抹去。 |
| evidence_facts | object | 必有键 | 模拟观测输入，不含 severity/confidence/outcome。缺失、过期、冲突天气的数值为 null。 |
| evidence_facts_provenance | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| valid_from | string | 必有键 | ISO 日期；覆盖范围两端均包含，集成场景必须覆盖 start_date 到 end_date。 |
| valid_until | string | 必有键 | ISO 日期；不是 source_date。缺失证据对象内可为 null，STALE 证据必须有早于 scenario_date 的失效日。 |
| template_source_id | null / string | 必有键 | 原安全模板 ID，原模板为 null。复制场景必须使用新 ID 并记录来源。 |
| context_request_id | null / string | 必有键 | 复制安全上下文关联的 Request ID；独立模板为 null。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |

## tests/synthetic_test_fixtures.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| fixture_id | string | 必有键 | 对应 tests/synthetic_test_fixtures.json 的独立 setup/actor/actions/clock。 |
| test_id | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| test_mode | string | 必有键 | COMPONENT 或 INTEGRATION；组件不借无关 Request 宣称完整行程通过。 |
| demo_clock | string | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| actor | object | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| setup | object | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| actions | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| source_type | string | 必有键 | 固定 SYNTHETIC。 |
| source_name | string | 必有键 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 必有键 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 必有键 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| revision_date | string | 必有键 | 2026-10-09，修订日期。 |
| notes | string | 必有键 | 非空来源/演示用途/限制说明。 |

## tests/synthetic_oracles.json

| 字段 | 实际类型 | 存在要求 | 含义及缺失处理 |
| --- | --- | --- | --- |
| request_oracles | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| safety_oracles | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| test_oracles | array | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |
| metadata | object | 必有键 | 按同名字段保存；null、空数组与空串各保留原义，详细嵌套结构见 schemas。 |

## data/synthetic_campsites.csv

| 字段 | CSV 导入后类型 | 必填/可空 | 含义及缺失处理 |
| --- | --- | --- | --- |
| campsite_id | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| name | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| region | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| subregion | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| latitude | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| longitude | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| nightly_fee_aud | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| fee_unit | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| booking_required | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| vehicle_access | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| public_transport_access | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| max_group_size | integer | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| toilets | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| potable_water | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| showers | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| fire_allowed | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| pets_allowed | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| wheelchair_accessible | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| supported_seasons | array<string> | 空串代表无条目 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| facilities | array<string> | 空串代表无条目 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| mandatory_restrictions | array<string> | 空串代表无条目 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| risk_tags | array<string> | 空串代表无条目 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| source_type | string | 非空 | 固定 SYNTHETIC。 |
| source_name | string | 非空 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 非空 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 非空 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| notes | string | 非空 | 非空来源/演示用途/限制说明。 |
| revision_date | string | 非空 | 2026-10-09，修订日期。 |
| walk_in_only | boolean | 非空 | 由 vehicle_access=false 归一化；并非任意营地允许步行就为 true。 |
| quiet_environment | boolean | 非空 | 新增演示属性，明确标注 V2_DEMO_ASSUMPTION。 |
| step_free_path | boolean | 非空 | 新增演示属性，仅对 v1 可达性营地作演示假设。 |
| demo_attribute_provenance | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |

## data/synthetic_gear_rules.csv

| 字段 | CSV 导入后类型 | 必填/可空 | 含义及缺失处理 |
| --- | --- | --- | --- |
| gear_rule_id | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| category | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| item_name | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| trigger_conditions | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| quantity_rule | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| essential | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| severity_if_missing | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| substitute_allowed | boolean | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| substitute_example | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| reason | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| source_type | string | 非空 | 固定 SYNTHETIC。 |
| source_name | string | 非空 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 非空 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 非空 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| notes | string | 非空 | 非空来源/演示用途/限制说明。 |
| revision_date | string | 非空 | 2026-10-09，修订日期。 |
| item_key | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| trigger_json | JSON expression | 非空 | CSV 中 JSON 字符串，导入为声明式条件对象；禁止执行英文条件或 eval。 |
| quantity_json | JSON expression | 非空 | CSV 中 JSON 字符串，导入为声明式数量表达式；未知变量返回具体 missing_inputs。 |
| quantity_unit | string | 非空 | item/person_capacity/litre/meal_portion/snack_portion。跨单位禁止直接相乘。 |
| overlap_group | string | 可空：不适用 | tent_capacity、sleeping_bag、drinking_water 或空串；同组取 MAX，避免把基础及补缺规则相加。 |
| aggregation | string | 非空 | MAX_WITHIN_OVERLAP_GROUP；按 item_key + quantity_unit 合并总需求，补缺量再减已确认库存。 |
| policy_source | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |

## data/synthetic_cost_reference.csv

| 字段 | CSV 导入后类型 | 必填/可空 | 含义及缺失处理 |
| --- | --- | --- | --- |
| cost_id | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| category | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| item_name | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| unit | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| low_aud | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| typical_aud | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| high_aud | number | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| calculation_rule | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| source_type | string | 非空 | 固定 SYNTHETIC。 |
| source_name | string | 非空 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 非空 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 非空 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| assumption | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| notes | string | 非空 | 非空来源/演示用途/限制说明。 |
| revision_date | string | 非空 | 2026-10-09，修订日期。 |
| quantity_json | JSON expression | 非空 | CSV 中 JSON 字符串，导入为声明式数量表达式；未知变量返回具体 missing_inputs。 |
| rate_source | string | 非空 | 营地用所选营地的 nightly_fee_aud；其余用典型参考价 typical_aud。 |
| selection_group | string | 可空：不适用 | FOOD_CHOICE 或 TRANSPORT_CHOICE：每组按 meal_mode / transport_type 选适用项，避免重复费用。 |

## tests/synthetic_agent_test_cases.csv

| 字段 | CSV 导入后类型 | 必填/可空 | 含义及缺失处理 |
| --- | --- | --- | --- |
| test_id | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| requirement_id | string | 非空 | 正式 Stage 1 FR/NFR 编号，多值以分号分隔；出现编号不等于验收通过。 |
| module | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| title | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| priority | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| preconditions | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| profile_id | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| request_id | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| campsite_id | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| safety_case_id | string | 可空：不适用 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| plan_version_id | string | 可空：不适用 | 可空；非空必须由 fixture 预置或由显式 GENERATE/REVISE 动作创建。 |
| execution_steps | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| expected_extracted_values | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| expected_outcome | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| expected_required_content | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| expected_state_change | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| forbidden_behaviour | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| test_type | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| pass_criteria | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| source_type | string | 非空 | 固定 SYNTHETIC。 |
| source_name | string | 非空 | CampMate Synthetic Demo Dataset v2。 |
| source_date | string | 非空 | 2026-10-07，原包来源日期；不是观测时间或覆盖期限。 |
| demo_only | boolean | 非空 | JSON 中 true；CSV 为文本 true，导入必须严格转换。 |
| revision_date | string | 非空 | 2026-10-09，修订日期。 |
| fixture_id | string | 非空 | 对应 tests/synthetic_test_fixtures.json 的独立 setup/actor/actions/clock。 |
| test_mode | string | 非空 | COMPONENT 或 INTEGRATION；组件不借无关 Request 宣称完整行程通过。 |
| execution_status | string | 非空 | NOT_RUN。实际运行由应用团队另行记录，不从预期改成 PASS。 |
| notes | string | 非空 | 非空来源/演示用途/限制说明。 |
| actor_user_id | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |
| actor_role | string | 非空 | 保留原始业务含义；类型按本列严格导入。空值不自动变成 0 或 unknown。 |

## 装备与费用的结构化规则

DSL 仅支持 var、mul、add、sub、eq、lt、lte、gt、gte、and、or。变量不存在或为 null 时返回具体缺失字段；不执行任意代码。
触发阈值为明确的演示假设：寒冷 ≤10°C、低温 ≤5°C、高温 ≥35°C、大雨 ≥30mm、强风 ≥40km/h。
同 item_key + quantity_unit 的规则取最大总需求；帐篷按总人数容量比较，租两人帐篷数量为 ceil(max(0,人数-已确认容量)/2)。
儿童零食必须使用 children_count，手机数量使用 adult_count。未知容量、torch 数量及车辆数必须澄清，不能视为零。

费用选择：CAR 使用 cost-02 与 cost-15；PUBLIC_TRANSPORT 使用 cost-03。SELF_CATERED 使用 cost-04；READY_TO_EAT 使用 cost-14。其他装备只对明确缺口计费。金额先按每行计算并使用 Decimal 与 ROUND_HALF_UP 转为整数分，再累加整数分；禁止用 binary float 或 Python round() 计算货币。
cost-01 使用实际选中营地费 × duration_nights，不能再加一笔通用营地参考费。
饮水需求为 litres；cost-05 计费为等价人天（两升/人天）：water_equivalent_person_days = packaged_water_litres / 2。
普通三天两人例子为 12L → 6 等价人天 → AUD 36；无水营地加应急一天为 16L → 8 等价人天 → AUD 48。
水源采集的现场水不计入包装水采购费用。示例成功路径刻意购买全部 12L 包装水，避免隐含水费假设。
汽车公里数为所有车的总公里，停车按 vehicle_count 计一次；租赁价格假设为整个演示行程一次费用。
缺路程、车辆数或装备采购数量时，只给已知分项/具体 missing_inputs，完整 total_aud=null，不给伪精确价格。
