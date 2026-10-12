# B-02：确定性业务规则与待补输入

## 完成范围

本次在 B-01 Adapter 上实现五项纯业务能力，使用 Git 中未改动的 v1。没有调用外部 API、LLM 或爬虫，也没有更改共享契约 1.0、A 的数据库/权限/HTTP/前端、应用注册或默认配置。

入口：`backend/app/agents/rule_agent.py` 的 `RuleAgent(dataset)`。实现拆在 `agents/rules/`，当前 v1 规则标识为 `b02-v1-rules-2`。只接受 `deterministic_demo`，拒绝伪装成 stub 或真实 LLM agent。输入输出直接使用共同 DTO，不另建数据库或业务 ID。

2026-10-12 修订：无台阶硬约束采用 True/False/None 三态判断，False 不得被旧设施文本覆盖。本文后续 B-02 缺口/协商表是原阶段记录；当前 A12/A13 接线、v2 规则身份与 R-01/R-02 验证结论见 [v2 runtime integration](v2_runtime_integration.md)。

2026-10-11 更新：`orchestrate()` 已由 B-03 实现 checkpoint 编排，见 [编排与恢复交接](developer_b_orchestration.md)。RuleAgent 尚未加入 A 的 AGENT_FACTORIES，所以页面仍不声称可以执行真实规划；下文 B-02 的验证数字保留该阶段记录。

## 独立调用示例

从 `backend/` 的 Python 环境运行：

```python
import asyncio

from app.adapters import SyntheticDatasetAdapter
from app.agents.rule_agent import RuleAgent
from app.config import Settings
from app.contracts.dto import DemoContext

settings = Settings(_env_file=None)
dataset = SyntheticDatasetAdapter(settings.dataset_path).load()
agent = RuleAgent(dataset)
demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-08')
result = asyncio.run(agent.interpret_request(dataset.request_input('request-01', demo)))
print(result.model_dump_json(indent=2))
```

该调用仅返回解析与澄清结果，不确认请求、不创建运行或方案。真正的确认、用户身份和运行作用域仍由 A 提供。

## 规则行为

### 请求解析

限定为当前英文 demo 语句与明确结构化输入，不声称支持通用自然语言或中文解析：

- 识别已登记地区、ISO 日期、明确晚数/天数、AUD/美元符号金额和少量偏好。时长和人数先解析完整数字 token；负数和小数不会从 token 后缀误读成正整数，而是返回 INVALID 并要求澄清。
- 两晚推导三天及结束日期；只给天数不会自动换算晚数；原 v1 的 duration_days 元数据不参与解析。
- 显式字段优先；无效预算、非正人数、日期冲突、不同人数/交通方式、缺失字段或不支持地区返回 field_errors/clarifications。
- 原文 zero campers 不被 Profile 人数覆盖；request-03 没有时长仍需澄清。
- 识别有限的硬约束语句，如 must have toilets；未知或复合 must/require 语句要求明确结构化约束，不静默当作软偏好。
- 解析没有 CONFIRMED 状态输出；还须由 Camper 确认当前摘要。

### 营地推荐

完整扫描当前十个营地。地区、人数容量、整段行程的南半球季节、交通方式、已表达无障碍需求和明确硬约束不满足/未知时排除。已知营地费本身超过预算也排除，但候选的完整费用仍需物流阶段计算。

支持的硬约束名称：toilets、potable_water、showers、fire_allowed/campfire、pets_allowed、wheelchair_accessible、vehicle_access、public_transport_access、no_fires、walk_in_only。未知约束返回 INPUT_INVALID，不能伪装成已支持。

无障碍只支持有明确来源映射的 wheelchair-accessible toilet、step-free path、wheelchair access；其他需求不能用一个 wheelchair_accessible 标志替代。映射仅用于合成 demo，不是设施现场验证。

软偏好匹配数量降序，然后按已知夜费、营地 ID 稳定排序。quiet-hours 只能是偏好信号，不保证安静。MATCHES 不是订位或安全放行，NO_MATCH 也不能替代 ADAPTER_FAILURE。

### 行程与有限修订

从调用方给出的合法候选选一个营地，生成明确晚数的 CAMP 及中间休息时段。时间使用 Australia/Sydney，12:00/17:00/08:00/10:00 是已注明的草稿占位，不宣称是真实入住、活动可用性或交通耗时。保存前后的时间区间必须有序、不重叠、覆盖每一晚并引用已选营地。

支持反馈：cheaper campsite、lower campsite fee、change campsite、remove campfire、no campfire。更便宜必须有来源价格支持，不保证完整总费用已满足预算。没有有效替代时返回错误，不能造低价。

remove campfire 返回 requested_requirement_changes，移除营火偏好/硬要求并提出 no_fires；不修改原确认需求。未知反馈、预算/日期/地区的自然语言变更留待结构化补充和重新确认。B-02 的修订限定同一确认日期范围，完整修订闭环待 B-05/A 对接。

### 装备、交通和费用

- 显式解释当前 30 条 Gear Rule 的触发与数量文本，不执行 eval。遇到新/未知规则、物品或计费语义返回 ADAPTER_FAILURE，不能悄悄换算。
- 帐篷以人位容量检查；帐篷/额外容量、睡袋/额外睡袋按同一 item_key 合并，缺口取最大要求，不能重复租赁计费。
- 只有数量、单位、容量均明确且 confirmed=true 的库存才可满足要求。缺失库存是未解决缺口；存在未知/未确认条目时不能直接按 0 计算。租赁估价不等于 CONFIRMED_RENTAL。
- LogisticsInput 没有天气事实，先纳入天气装备的保守全集并记录假设，而不是猜某条件不触发。可选装备只列建议、不自动计入必须采购支出；未知必需装备费率为 null。
- 餐饮方式通过现有、已确认的 preferences 表达：ready-to-eat meals/READY_TO_EAT 或 self-catered meals/SELF_CATERED。两者同时出现或缺失需澄清；不引入未持久化的私有 meal_mode 值。
- 无饮水供应时增加一天应急水；升数装备需求与人天价格分别计算，不能直接乘错单位。食物/水费用是明确注明的 synthetic provision-value allowance，不把已有物资默认当作免费，也不声明发生采购。
- CAR 需要车辆数、全部车辆合计公里数及确认的车载人数容量；里程是合计值，不再乘车辆数。容量用 vehicle EquipmentItem 的 quantity/capacity_persons，单位 vehicle，不猜车座数。
- PUBLIC_TRANSPORT 需营地可达以及 confirmed transport_itinerary，单位 plan；仅有可达标志不证明有可用接驳。
- 每行 Decimal × cents 按 ROUND_HALF_UP；五类费用均覆盖。任一金额未知，总价和预算差额为 null，已知小计独立报告。已知小计已超预算也明确要求修订。
- 只有必需装备落实、交通可行、费用完整且未超预算、无 blocker/clarification 才返回物流 PASSED。这里不表示安全通过或允许最终保存。

### 安全与路由建议

安全只使用实际 ScenarioContext/Evidence、行程、已保存物流评估及营地限制，不读取原 severity/confidence/expected_* 标签，不编造温度、风速或风险概率。

四类证据 WEATHER/FIRE/ROAD/RESTRICTION 必须分别适用于每个已选营地，来源日期不能晚于固定 demo_today，场景和证据的有效期必须覆盖整个行程。SourceRef 明确声明更窄范围时也不能忽略。缺失/过期/冲突、未知或 unverified 内容保持不能通过；AVAILABLE 标签不能掩盖事实缺口。

限定的定性天气政策：明确 mild/dry synthetic conditions 为低；cold/rain/wind 为中；extreme heat/cold、strong wind、heavy rain、flood 为高。无法识别的天气/火情事实需补证据，不从标签推算数值。它们仅是版本化 synthetic demo 规则，不是校准的真实安全标准。

道路关闭、营地关闭、计划/请求营火违反禁令产生 mandatory blocker；缺失其他证据不会抹掉已知禁止条件。检测营火不限于 ACTIVITY，CAMP 描述也检查。B-02 仅识别自身的过夜/休息模板；任意其他活动或旅行描述进入未知风险人工审核，不宣称全部活动已经评估。已保存物流中的强制装备 blocker 也保留。

`agents.rules.safety.propose_route(saved_logistics, safety_result)` 校验同 run/version/context、模式及实际依赖 assessment_id，建议顺序为：强制阻断→必要审核→普通修订→满足最终化前置条件。函数不保存 route、更不写 FINALISED；实际 route 与 eligibility 仍由 A 守卫决定。

## 缺什么，以及是否阻塞当前工作

不缺开始 B-02 单元开发的条件，不需要 API Key。Git v1 能支撑规则实现和异常路径，但不能自动形成完整成功演示：

| 缺口 | 需要谁补/确认 | 当前处理 |
| --- | --- | --- |
| 已确认装备数量、容量、单位、饮水与食物安排 | Camper/数据与测试负责人 | null、缺口及澄清，不从 notes 补值 |
| 儿童数、车辆数、座位容量、合计公里数/公共交通计划 | Camper/测试负责人 | 未知交通不标可行 |
| 单一餐饮方式和复杂强制约束 | Camper，必要时 A/B 对齐输入 UI | 使用现有确认 preferences/mandatory_constraints，不私下追加字段 |
| 每个营地的整段行程证据有效期及完整事实 | A/B 与数据负责人 | 原 v1 日期不足，不能 PASSED；新事实须登记为独立输入 |
| 部分必需装备的费率，如 warm layers/groundsheet/fuel | 数据负责人，或 Camper 确认实际库存 | 未知价为 null，不造价 |
| 实际规则版本登记与全部场景文件摘要 | A/B | b02-v1-rules-1 尚未进入 A 的运行上下文，注册/启动前必须对齐 |
| 启动、调度、续期、checkpoint、重试接线 | B-03 与 A | B-02 不注册工作流能力 |

本次测试使用明确标记的独立 Profile/交通/证据 DTO 输入；这些补充没有写回 Git 数据，也没有纳入应用默认数据上下文。完整输入单元通过不等于从空库/UI 运行的四场景通过。B-03 必须将所有实际运行输入的 bytes/digest、选择配置及规则版本纳入确认/run，不能把 tests/rule_fixtures.py 或测试预期当作生产输入。

### 与 A 的已知路由差异

冻结交接要求高风险不能跳过升级。B 的建议在无强制 blocker 时让 REVIEW 优先于 REVISION；当前 A `storage/port.py` 仍让 REVISION_REQUIRED 优先于 ESCALATED。高风险且超预算的 B 测试会建议 ESCALATED，不能据此声称 A 最终也返回该状态。

A/B 需对齐持久化/审核队列顺序。B-03 要消费 A 实际返回的 RouteResult，不自行改数据库、覆盖实际状态或把建议当作最终化许可。本次没有修改 A 的路由。

## 验证与后续

从 backend/ 使用已安装仓库锁定依赖的 Python：

```bash
python -m pytest tests/test_rule_planning.py tests/test_rule_logistics.py tests/test_rule_safety.py --basetemp ../var/pytest-b02-rules
python -m pytest --basetemp ../var/pytest-b02-regression
python -m app.export_contracts --check
```

2026-10-11 实际验证（B-02 原阶段）：新增 120 项规则测试通过；当时后端回归 354 项通过。后续审查修复及当前回归结果见 PR 审查修复记录。没有运行 LLM 或真实 UI 四场景验收。

后续更新：B-03 已完成后端编排，当前工作区可一并提交 B-01～B-03。接下来与 A 接线规则版本、工厂、场景登记、HTTP/页面启动重试与风险路由，再共同准备四个用户端可运行场景。
