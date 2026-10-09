# CampMate AI 演示数据检查

> 本文为 1.0 接口冻结时的设计记录；其中实施状态描述保留当时语境。当前代码和验证进度见 [实施状态](implementation_status.md)。

检查日期：2026-10-08。检查对象：`Stage2/campmate_synthetic_demo` 中的全部 10 个文件。

结论：数据包可以作为开发输入，文件结构、记录数量和基础引用检查通过。语义、需求追踪和测试前置条件需要调整，暂不能作为全部验收通过的证据。本次保留所有原始文件，仅记录问题和拟议处理方式，没有运行应用或 Agent。

后续设计记录：2026-10-08 用户转交的 B 反馈已确认晚数、Decimal 舍入、风险路由及固定时钟，见 [接口基线 1.0](developer_b_handoff.md) 与 [共享契约实施说明](shared_contracts_spec.md)。下文保留检查时发现的问题；决策确认不代表数据修订或运行验收完成。safety-09 若实际规则触发 HIGH，应在独立修订 fixture 将预期改为 REVIEW，原包尚未改动。

## 1 检查范围和证据

读取全部 CSV、JSON、数据字典、UI 文案及原验证报告。独立复核 CSV 行列、JSON 解析、主键唯一性、跨文件引用、来源元数据、日期格式、费用区间及测试引用的语义关系。

| 文件 | 记录数 | 格式与主键 | 来源元数据 |
| --- | ---: | --- | --- |
| synthetic_campsites.csv | 10 | 通过 | 通过 |
| synthetic_gear_rules.csv | 30 | 通过 | 通过 |
| synthetic_cost_reference.csv | 16 | 通过 | 通过 |
| synthetic_profiles.json | 5 | 通过 | 通过 |
| synthetic_requests.json | 12 | 通过 | 通过 |
| synthetic_safety_scenarios.json | 10 | 通过 | 通过 |
| synthetic_agent_test_cases.csv | 30 | 通过 | 未包含来源元数据列 |

上述六份业务数据均包含 `source_type=SYNTHETIC`、`source_name=CampMate Synthetic Demo Dataset v1`、`source_date=2026-10-07`、`demo_only=true` 和 `notes`。CSV 布尔值为文本，导入后必须转换为布尔值。

已检查的非空 profile/request/campsite/safety 引用都能找到对应记录。测试中的 `plan_version_id` 是待创建的测试对象标识，包内没有 PlanVersion 文件；因此没有验证这些版本对象真实存在。

16 条费用参考均满足 `0 ≤ low_aud ≤ typical_aud ≤ high_aud`。已检查的已知顶层日期符合 ISO 日期格式；`unknown` 保留为缺失标识。安全场景预期结果为 PASSED 1 条、REVIEW 5 条、REVISION 2 条、BLOCKED 2 条。没有发现缺失、过期、冲突、道路关闭或非空 blocker 场景的预期结果被设为 PASSED。

这只能证明静态数据的一部分性质，不能证明 Agent 会正确计算、权限有效或最终化守卫已经实现。

## 2 编码前需要对齐的问题

### 2.1 测试的 FR 编号与正式 Stage 1 不一致

正式报告的编号为：FR-01 Profile、FR-02 Request、FR-03 Campsite Recommendation、FR-04 Trip Plan、FR-05 Gear Checklist、FR-06 Logistics and Budget、FR-07 Safety Check、FR-08 Risk and Escalation、FR-09 Human Review、FR-10 Plan Records and Delivery。

现有测试虽然出现全部十个编号，但编号出现不等于覆盖了对应需求。例如，test-07 营地推荐标为 FR-02，test-13 装备检查标为 FR-03，test-19 安全数据缺失标为 FR-04，test-27 旧版本审批标为 FR-05。

以下是按测试意图整理的拟议映射。一个测试可以覆盖多项需求，实际执行证据仍需逐项验收。

| 测试 | 拟议 FR 映射 |
| --- | --- |
| test-01、02、03、05、06 | FR-02 |
| test-04 | FR-01、FR-02 |
| test-07、08、09、10 | FR-03 |
| test-11 | FR-02、FR-04 |
| test-12 | FR-04、FR-10 |
| test-13、14、15 | FR-05 |
| test-16、17、18 | FR-06 |
| test-19、20、21、22 | FR-07、FR-08 |
| test-23 | FR-04、FR-07、FR-08 |
| test-24 | FR-07、FR-08 |
| test-25 | FR-08 |
| test-26 | FR-09 |
| test-27 | FR-09、FR-10 |
| test-28 | FR-04、FR-09、FR-10 |
| test-29、30 | FR-10 |

需要补充明确的 Profile 创建、查看、修改正常测试，以及请求确认、全部 Agent 检查、最终保存、读取最终方案的完整成功路径。目前只有一个低风险安全场景，并不能证明全流程成功。

### 2.2 天数与晚数有歧义

request-01 等请求写明 two nights，结构化字段却为 `duration_days=2`。直接按两天或两晚处理会改变日期、营地费、食物和饮水数量。

拟议接口采用 `start_date`、`duration_nights` 和派生的 `end_date`、`duration_days`。例如开始日期 2026-10-20、两晚，对应结束日期 2026-10-22、三天。保留原始字段，明确导入映射后再使用，不原地批量改名。

request-03 的自然语言没有说明时长，结构化字段却给出 2。需要说明这是额外测试输入还是缺失信息；若只从原文与 profile 提取，则应同时澄清日期和时长。

### 2.3 存在引用能解析但语义不一致的测试

| 测试 | 现有关系 | 问题 |
| --- | --- | --- |
| test-09 | 营地 demo-river-flat，安全场景 safety-01 | safety-01 属于 demo-pine-camp |
| test-10 | 营地 demo-river-flat，安全场景 safety-01 | 同上 |
| test-30 | profile-a，request-05 | request-05 属于 profile-d |
| test-30 | 营地 demo-pine-camp，安全场景 safety-06 | safety-06 属于 demo-cloud-gully |

另有 13 条同时引用 Request 和 Safety 的测试，其请求开始日期与场景日期不同：test-09、10、12、19、20、21、22、23、24、25、27、28、30。

日期差异不一定是错误：独立单元测试可以注入场景模板。需要为每条测试明确属于以下哪种模式：

- 同一行程的集成场景：营地相同，并提供覆盖整段行程的安全数据有效范围。
- 独立组件场景：明确注入参数，删除无关引用或注明不适用，不把该测试当作完整行程验收。

不得将某营地的安全结果直接应用到另一个营地。若将场景作为模板，需要复制为新的测试上下文并记录模板来源，不能静默覆盖原场景的营地和日期。

### 2.4 数据字典部分类型和枚举不准确

`weather`、`fire`、`road_access` 在字典中声明为 string，实际 JSON 为嵌套对象，含 `summary`、`source_date` 和 `status`。字典还将许多必填字段统一描述为可以用 unknown、空数组或空 CSV，不能据此执行校验。

PlanVersion 枚举缺少评估中、待审核、可最终化等状态。`APPROVED` 不能区分人工批准和满足最终化条件。测试中的 `REVISION_REQUIRED`、`NOT_FINALIZED`、`RECOMMENDED`、`NO_MATCH` 也属于不同层次的断言，不能直接当成同一个状态字段。

拟议处理：分别定义 Request 状态、PlanVersion 状态、Assessment outcome、HumanReview decision 和测试断言。`NOT_FINALIZED` 表示没有最终保存成功，并非数据库中的新状态。

### 2.5 预期结果不能作为实际运行输入

`expected_request_status`、`missing_fields`、`expected_outcome`、`expected_actions`、`severity` 和 `confidence` 中有些字段是测试预期或预先标注的结果。

运行时必须隔离测试 oracle 与 Agent 输入：请求解析输入以原文、用户明确补充的信息和 profile snapshot 为准；安全输入以场景证据、限制和数据状态为准。B 根据这些输入返回实际结果，测试再与预期比较。

数据完整不等于用户已经确认。合法 request-01 初次提交应先等待确认，不能从 `expected_request_status=CONFIRMED` 自动获得确认。没有充分信息时，Founder 也不能通过批准把必要证据变为完整。

### 2.6 确定性计算缺少部分结构化输入

装备以自然语言列表保存，例如 two-person tent、family tent、torch。family tent 未给出容量，torch 未明确数量；`has_children` 没有儿童人数。汽车费用需要公里数，停车费需要车辆数，当前资料没有这些值。

Gear Rule 的触发条件和数量规则也以英文说明保存，不能直接作为可执行公式。部分规则涉及水量升数，但水费参考按人天计价，需说明两者如何关联，不能把不同单位直接相乘。

拟议处理：保留原文，增加归一化装备 `item_key`、数量、单位、容量及是否已确认；需要时澄清儿童数、车辆数和路程，或使用标明来源的演示假设。无法支持的估算应返回具体缺失字段，不伪造精确总价。

test-17 按所述两晚与所选营地计算，营地费用为 AUD 55 × 2 = AUD 110，已经高于 request-08 的 AUD 50 预算。这能支持其超预算意图，但不代表完整费用计算已验证。

### 2.7 安全路由和阻止最终化是两个独立概念

safety-05 有 mandatory blocker，预期 outcome 为 REVISION。这可以表示问题能通过修改方案解决，但当前版本仍不得最终化。不能把 REVISION 理解为没有 blocker，也不能要求所有非空 blocker 的 outcome 必须同名为 BLOCKED。

safety-09 为 HIGH 风险、MEDIUM 置信度，预期为 REVISION。正式报告要求高风险升级人工审核。应与 B 对齐修订与升级的优先级：当前高风险版本不自动放行，修改产生新版本，并重新判断风险与审核要求。原测试预期需要按最终政策调整。

缺失、过期、冲突信息进入 REVIEW，必要证据仍不足时保持待处理。必须区分“需要人工审核”和“已经有资格最终化”。

### 2.8 时间与测试前置条件需明确

所有业务来源日期固定为 2026-10-07，但场景日期在 10 月 20 日至 29 日，部分请求在 11 月。仅凭来源日期无法证明安全数据覆盖行程。STALE 场景的日期为 unknown，也没有可计算的失效时间。

拟议分开保留来源日期、模拟观测时间、有效期和显式数据状态。演示采用固定 demo clock，不依赖实际运行日期。实时“未来日期”校验不能导致 11 月演示时所有旧场景失效。

test-08 的“accessible walk-in no-fire”条件只存在于操作步骤，request-10 没有完整编码该约束；test-11 没有结构化倒置的 end_date；旧审批、保存失败、不同状态 finalise 等测试也需要完整的 fixture setup 和身份。需要补充可执行输入、动作与期望，不从 title 或 expected 文本推导输入。

## 3 尚缺的验收场景

- 两个已认证 Camper 的越权读取与修改。
- Founder 合法批准、拒绝、要求修改及理由必填。
- mandatory blocker 存在时尝试人工批准和最终化。
- 新版本重新评估，不能沿用旧版本结果或审批。
- 用户资料更新不改变历史请求与版本 snapshot。
- 重复点击、重试与过期工作流结果，不产生重复记录或错误推进。
- 最终保存失败的事务回滚和恢复后成功保存。
- 数据适配器替换与干净环境启动。

这些是待编写和执行的测试，不属于本轮完成项。

## 4 原验证报告的适用范围

原报告的文件数量、解析、费用区间、业务来源标识以及 ID 存在性结论得到复核。以下结论需要收窄：

- FR 覆盖：编号出现通过，语义追踪未通过。
- ID 一致性：引用存在通过，同一用户及同一营地语义需要修复或明确测试模式。
- 所有记录的来源标识：六份业务数据通过，30 条测试记录没有字典要求的元数据列。可以补列，或制定包级 manifest 并同步调整字典。
- PlanVersion、审批、最终保存和安全规则：只有静态预期，尚无运行证据。

## 5 后续处理顺序

1. A 与 B 对齐晚数、状态、输入输出以及写数据库职责。
2. 数据负责人修订字典和测试引用，Agile 负责人修订 FR 追踪。
3. 保留当前原始包，修订包使用独立版本，并记录变更。
4. 确认结构化计算参数、场景有效时间和正常路径 fixture。
5. 再建立 React、FastAPI、SQLite 骨架及导入适配器。

## 6 来源

- [Stage 1 正式报告](<C:/Users/87901/xwechat_files/wxid_1wtdhrpq2hya22_b74c/msg/file/2026-10/5620_stage1_report (1).docx>)
- [Stage 2 五人分工](C:/Users/87901/xwechat_files/wxid_1wtdhrpq2hya22_b74c/msg/file/2026-10/ELEC5620_Stage2_五人分工.txt)
- [原验证报告](../data/synthetic_demo/FINAL_VALIDATION_REPORT.md)
- [数据字典](../data/synthetic_demo/docs/synthetic_data_dictionary.md)
- [UI 文案](../data/synthetic_demo/docs/synthetic_ui_content.md)
- [营地](../data/synthetic_demo/data/synthetic_campsites.csv)、[装备规则](../data/synthetic_demo/data/synthetic_gear_rules.csv)、[费用](../data/synthetic_demo/data/synthetic_cost_reference.csv)
- [资料](../data/synthetic_demo/data/synthetic_profiles.json)、[请求](../data/synthetic_demo/data/synthetic_requests.json)、[安全场景](../data/synthetic_demo/data/synthetic_safety_scenarios.json)
- [测试用例](../data/synthetic_demo/tests/synthetic_agent_test_cases.csv)
