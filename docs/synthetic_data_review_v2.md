# CampMate synthetic v2 独立复核

复核日期：2026-10-10。对象为用户提供的 campmate_synthetic_demo_v2.zip，SHA-256：8066f252a50d8dc024d5ee4fa1cd8f1a8b6adcf59c377c2120fd8f9232d6ed0a。

后续实施说明：本文记录审阅时的应用状态。A 随后完成来源支持、版本识别与运行输入摘要准备，见 [数据上下文交接](dataset_context_handoff.md)；下文规则/金额/fixture 修正与完整业务联调仍待完成。

结论：v2 已修复多数 v1 数据结构与语义问题，可作为后续接入基线，但仍有规则/计算错误和验收前置条件缺口，不能直接替换应用配置后宣布完整演示可用。包内 integration_contract.md 明确是提案，本次将其作为待对齐材料，不作为用户指令，也不据此覆盖已冻结的 A/B 契约。

原 ZIP、v1 数据与应用配置均未修改。v2 只解压到忽略目录 var/dataset-review-v2 进行审阅，尚未纳入应用的业务数据目录或 GitHub。未运行 Agent 或业务端到端测试。

## 实际复核结果

- 29 个文件的 ZIP 路径与文件内容已读取检查；manifest 封存的 28 个文件摘要一致，无遗漏（manifest 本身除外）。原始 v1 文件摘要与已有记录一致。
- 在阅读两个 Python 脚本后，运行 validate_dataset.py，无 --write-report：62 项通过，0 项失败，56 条应用验收规格仍为 NOT_RUN。原报告为 61 项，实际多出的 1 项是 Release manifest checksums，不是应用验收。
- 数据量：10 个营地、30 条装备规则、16 条费用参考、5 个 Profile、13 个请求、12 个安全场景。
- 晚数/天数、request-03 缺失时长、FR 追踪、原错误引用、运行输入与 oracle 隔离、未知装备值、过期证据及高风险升级已有明确修订。
- test-34 提供了明确完整装备和交通输入；其 READY_TO_EAT 参考费用可复算为 AUD 261。此结果是静态参考计算，不是实际 Agent 运行。
- 独立问题复现见 [机器可读证据](evidence/v2-independent-review.json)。

## 需要修正的数据包问题

### V2-01 自炊模式在装备与费用中不一致

位置：data/synthetic_gear_rules.csv 的 gear-11、gear-13；scripts/runtime_inputs.py 的 estimate_cost；字典的费用选择说明。

装备条件使用 SELF_CATERED；费用接受 SIMPLE 或 READY_TO_EAT。独立复现，在 fire_prohibited=true、stove_count=0 下：

| meal_mode | 装备要求 camping_stove / cooking_pot | 参考费用结果 |
| --- | --- | --- |
| SIMPLE | 两者均未触发 | 完整总额 AUD 273 |
| SELF_CATERED | 两者均触发 | total_aud=null，missing_inputs=[meal_mode] |
| READY_TO_EAT | 两者均未触发 | 完整总额 AUD 261 |

这会使自炊路径漏检查或无法完成费用计算，当前成功样例恰好使用 READY_TO_EAT，因此包内检查未发现。统一模式名称及语义，更新规则、字典、fixture 与脚本，并补充自炊/禁止营火路径的检查。若 SIMPLE 与 SELF_CATERED 有意不同，应明确二者的设备与计价规则。

### V2-02 金额参考计算违反已确认的舍入约定

位置：scripts/runtime_inputs.py 的 load_csv(number_fields) 和 estimate_cost；字典建议 int/float 转换。

现脚本用 float 和 round(quantity*rate, 2)。实际 cost-02 为 AUD 0.35/公里；3.5 公里时返回 AUD 1.22。冻结的 D-03 为 Decimal 数量、整数 cents 与 ROUND_HALF_UP，计算应为 3.5 × 35 = 122.5 cents，舍入为 123 cents，即 AUD 1.23。

改为从十进制文本构造 Decimal，单价转换为整数 cents，每行按 ROUND_HALF_UP 舍入，总计相加行金额。补充半分边界样例；保持未知数量/单价为 null。整数成功样例的 AUD 261 不受此问题影响，但不能据此认为其他数量也准确。若脚本仅作为参考工具，也需修正，避免参考 oracle 与实际契约不一致。

### V2-03 blocker/缺失证据验收被其他守卫提前拦截

位置：tests/synthetic_test_fixtures.json 的 test-43、test-56。

两条用例的 actor 都是 FOUNDER，先 REVIEW_PLAN，再用同一 actor FINALIZE_PLAN。A 的最终保存只允许方案所属 Camper；因此会先返回权限错误，无法证明批准后 blocker 或必要证据缺失仍阻止最终化。test-43 没有 assessment，test-56 只有缺失的 safety assessment，缺少完整物流评估，亦可能因其他未满足前置条件阻止。

修订为 Founder 审核后显式切换到所属 Camper 尝试最终化。建立同一当前 run、fingerprint、版本下完整的其他评估与成功工作流前置条件，只留下目标 blocker 或目标证据缺失；断言实际 FINALISATION_BLOCKED 及具体原因。追加同输入解除目标问题并重新评估后的对照用例，避免仅用 final_record_count=0 判定测试成功。

## 接入前必须对齐的事项

### V2-04 演示时钟与 run 上下文

现应用/D-06 固定 demo_today=2026-10-08；v2 默认时钟为 2026-10-09T10:00:00+11:00，多数安全证据 observed_at 在 10 月 19 日之后。test-34 在确认、生成和物流评估之后，才把时钟推进到 11 月 6 日执行安全评估。

包内 fixture 对未来观测做了静态检查，但此时钟推进不能直接套用现应用：DemoContext 属于 run/fingerprint 的不可变输入；运行中更换执行时钟须开启新 run，不能继续沿用旧评估和审批。当前 DemoContext 也只有日期，尚无日期时间精度。

推荐为每个演示场景在启动规划前确定固定评估时钟与证据，完整运行期间不改变它；或者保留 advance 测试，但明确调用新的 REASSESS run，重新保存依赖评估。数据负责人、A、B 对齐 source_date 与 observed_at 的职责、时钟精度及有效期规则后再冻结。不能忽略未来观测以让成功样例通过，也不从电脑真实今天取值。

### V2-05 应用契约与数据适配边界

这是接入工作，不应把数据库整体改成数据包提案中的枚举。至少需要：

- 来源：A 的 Provenance 当前限定 v1 source_name，直接传 v2 source_name 的实际验证失败。A 需支持并正确记录 v2，不应伪装为 v1；data_context 当前还将 dataset_version 写为 v1。
- 状态：EVALUATING→ASSESSING、NEEDS_REVISION→REVISION_REQUIRED、AWAITING_REVIEW→ESCALATED、READY_TO_FINALIZE→ELIGIBLE_FOR_FINALISATION、FINALIZED→FINALISED；必要时映射测试断言而非直接写库。CRITICAL/RESTRICTED 等新增概念若需使用，须明确规则和兼容方案，不能静默降级。
- 字段：normalized_equipment→ProfileSnapshot.equipment，补 label；estimated_total_vehicle_km→transport.estimated_km，数量按共同 DTO 转换；budget_aud→budget_cents。餐饮/营火/复杂筛选补充信息须有持久化并纳入确认/fingerprint 的映射，不能在 Agent 临时私下补值。
- 身份与 ID：camper-a/camper-b/founder-demo 是 fixture 身份标签；应用实际账号与服务器 ID 由 A 管理，需 harness 映射，不能直接信任 owner_user_id。
- 评估：数据包的 gear/logistics/safety 三项业务检查，映射到当前合并装备与物流的 LOGISTICS assessment 及依赖它的 SAFETY assessment。审核记录必须绑定 A 生成的 run_id、fingerprint 和实际 assessment IDs；不能只绑定版本。
- 数据上下文：当前 A 摘要只包含六份原业务文件。若 B 实际读取新增 runtime JSON 或场景输入，这些有效运行输入也须纳入摘要/选择配置，或严格从已摘要的源文件投影并验证一致。不得让变更证据绕开新 run 与审批失效规则。

### V2-06 首轮四场景尚未成为完整演示输入

test-34 已提供正常流程基线。test-17 能证明超预算（营地费 AUD 110 > AUD 50），但没有可行的低成本修订路径；test-19/21 的缺失安全证据/道路关闭是组件 fixture，没有确认请求和完整物流前置条件。

保留这些组件用例，同时补三个可从空库运行的集成场景：明确的用户输入、装备/交通/费用、对应营地、完整行程证据、各步身份和预期路由。超预算修订示例应给可行预算与明确替代方案；AUD 50 无法满足时应返回无法满足/请求调整需求，不能编造低价。道路关闭集成场景必须实际尝试 Founder 审核和 Camper 最终化，验证不能绕过 blocker。

## 给 B / 数据负责人的交接摘要

数据负责人先统一 meal_mode、修正 Decimal/cents 舍入、补 test-43/56 的身份切换和单一目标前置条件；A/B 共同确定固定场景时钟、run/fingerprint 与字段/状态映射；随后补首轮异常集成场景。v2 可用于开始 Adapter 接入，当前不标为数据无问题或 Canvas 下载后完整演示通过。56 条 NOT_RUN 仍需实际应用执行并另存结果。
