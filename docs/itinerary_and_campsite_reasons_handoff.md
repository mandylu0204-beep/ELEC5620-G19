# 行程安排与营地选择依据：实施契约与交接

基线：feature/itinerary-and-campsite-reasons，f176489。只使用离线模型替身；不修改封存包、个人配置或原用户数据库。

**当前活动扩充以文末 `camp-activities-2` 为准；以下保留第一版设计及验证记录。**

## 第一版接口与阶段

1. 新运行登记 b_planning_details=camp-activities-1，扩展资料 planning/camp_activities_v1.json 的字节摘要纳入 DatasetContext。无标记旧运行不升级。恢复校验保存摘要，包括缓存命中。
2. 现有 Candidate.reasons 保存按确认资料计算的具体匹配依据。受控工具额外提供容量、交通、设施、逐项匹配事实及明确的活动目录。不改变筛选资格及排序政策。
3. 新模型内部协议在原 proposal 上增加 daily_plan:[{date,activity_id}]，有目录时每天最多一项、每个住宿日一项；离开日由宿主给出收拾准备。无目录选址明确返回空列表。旧协议保持原 schema/Prompt/工具身份。
4. 活动仅限低复杂度营地内准备／休息，无新增收费、专用装备、预约、游泳、明火或越野路线。共享 DTO、审计 envelope 与保存接口仍为 1.0。具体安排用已有 ItineraryEntry 和 SourceRef 保存，时间为建议时间，不能表示已核实入住或交通时刻。
5. 宿主验证活动 ID、营地、适用日期、日期覆盖、重复、日程重叠和目录范围。安全规则只识别同一绑定目录产生且带来源的精确描述；未知活动仍走既有人工判断，不扩成任意活动白名单。
6. 所有匹配文字、行程、来源随原版本保存；HTTP/历史/最终快照只显示已保存内容，不读取当前目录补写历史。不新增模型调用或 trace 表；规划 Prompt/schema/校验/工具的新身份随运行固定。REVISE 使用新协议，REASSESS 不重跑规划。

## 交付边界

第一版先覆盖 Lane Cove、Bonnie Vale、Bents Basin 的模拟营地内活动。其他营地保留住宿/休息草稿并明确活动资料不足。不提供实时路线、班次、精确旅行时间、订票或复杂户外活动；不宣称此候选接口已获 A 独立复核。

A 需重点复核 runtime 新政策分流、共享条目保存与 audit/recovery 组合；无需数据库迁移。验证结果完成后补充。


## 实际实现与读取展示

- `planning_reference.py` 严格校验版本、来源族、唯一 ID、适用期、零额外收费、无专用装备、无需预约的边界。目录共 9 条：每个营地两项营地内安排及一项离营整理。具体内容包括饮水整理、设施核对、营位休闲、观察记录、离营垃圾与装备清点。没有游泳、明火、未登记路线或实际班次。
- `created_on=2026-10-29` 是本次扩展创建日期；SourceRef 的 `source_date=2026-10-07` 沿用冻结 DTO 的来源族字段，不冒称新活动已由旧日期来源核实。所有新活动明确为模拟建议，独立文件摘要才是该次输入的精确身份。
- 新协议是 `planning-coordinator-daily-1 / campsite-tool-daily-1 / planning-validation-daily-1`；原协议的 Prompt/schema/工具版本继续保留。共享 ItineraryResult、SourceRef、ModelPlanningTrace 和 append_model_plan 签名不变；版本和 trace 仍走原事务。
- 模型只选择日期和目录 ID，不能返回活动费用、具体时间或已预订状态。宿主安排下午建议时段、夜间住宿及离营准备，验证整段日期与非重叠关系。未取得合法新协议结果会失败关闭，不自动补选或降为规则成功。
- 新增匹配事实使用已确认的人数、交通、必须条件、设施和整数分营地费用。费用文字用 Decimal 格式化；筛选资格和原排序不变，完整露营费用仍由物流计算。工具只发送一次候选来源，不重复展开每条事实来源，未增加模型轮数、token 上限、超时或重试。
- 页面按悉尼日期显示“第几天”，使用保存的具体条目。当前／历史／最终快照／审核共用组件，不查当前目录补写旧行程。模型自由说明仍标为未经核实的意见，宿主事实与备选营地的具体差异分别显示。
- 活动的确定性安全识别要求精确目录描述、对应营地、有效日期、建议时段和保存来源均匹配；未知、被篡改、缺来源的条目仍触发现有活动人工判断。正式天气、道路、用火、装备、费用、审核和保存守卫保持。

## 修改文件

- 资料与 Adapter：`data/planning/camp_activities_v1.json`、`backend/app/adapters/planning_reference.py`。
- 规则与身份：`agents/rules/planning.py`、`agents/rules/safety.py`、`application/agent_runtime.py`、`workflow/configuration.py`。
- 真实规划组件：`llm/tools.py`、`llm/planning_schema.py`、`llm/coordinator.py`。
- 页面：`frontend/src/daily_itinerary.tsx`、`plans.tsx`、`styles.css`。
- 测试：`test_planning_details.py`、两个现有 MockTransport responder 的协议适配、`display_presentation.test.mjs`。

## 人工验收与尚未覆盖范围

后续由用户明确启动/重启后端加载新代码，再刷新前端。先选 Lane Cove、Bonnie Vale 或 Bents Basin 验证具体行程；演示模式按目录轮换，agent 模式由真实模型选择目录 ID，两者身份不混用。新模型输出未经过真实校园服务验收，本次只做 MockTransport；不宣称现场开放、订票、入住时间或建议活动已安全放行。

其他七个营地仍有具体筛选依据，但暂无目录内活动，保留原住宿/休息草稿并显示数据限制。暂未实现跨营地、多段交通、徒步路线、额外收费活动及全天逐小时安排；要增加这些范围，应另补费用/装备/安全政策，而不是只添自由文本。

没有数据库迁移；没有改个人环境文件、密钥、原用户数据库、封存包；没有重启现有服务，也没有自动 commit/push。


## A 复核建议

1. 复核 `AgentRuntime.resolve/for_scope` 的 planning_policy：Sydney 2.2 托管新运行启用，旧 scope 缺标记时保持缺标记；旧模型 Prompt/schema/tool identity 不重标。恢复先检查已存摘要，暖缓存也不得替换资料。
2. 复核模型版本+trace+回执仍走 `append_model_plan` 原事务，新增条目全部进入保存的 content/source_refs。重评只产生新评估，原模型 trace 和行程不复制、不重生成。
3. 复核安全白名单范围：只有低复杂度营地内目录条目，必须精确描述/来源/日期/时段匹配；任何实际路线、越野、水域、收费、特殊装备活动都不在本轮支持范围。
4. 复核 Camper 原始 HTTP 无 trace/token/配置指纹，Founder 原权限不扩大；最终快照读取与历史页面没有从当前数据“补写”旧理由或安排。
5. 真实校园模型联合验收尚未执行。若安排验收，只需先做一个有目录营地的短途 PLAN、一次换营地 REVISE 和一次 REASSESS，检查模型日程字段和回读，不默认重复多轮付费测试。


## 离线复核命令

新内部协议静态文件：`docs/contracts/planning_daily_v1.schema.json`，只供本轮内部规划角色复核，不替换共享 1.0 schema。

```sh
# 仓库根目录；只用隔离测试数据库与 MockTransport
PYTHONPATH=scripts .venv/bin/python -m pytest -p v22_offline_transport_guard backend/tests/test_planning_details.py backend/tests/test_sydney_model_safety.py backend/tests/test_sydney_safety_snapshot_guards.py backend/tests/test_display_projection.py --basetemp=var/pytest-planning-details-review -q
# 全量（使用新的临时目录）
PYTHONPATH=scripts .venv/bin/python -m pytest -p v22_offline_transport_guard backend/tests --basetemp=var/pytest-planning-details-review-full -q
cd frontend
node --experimental-strip-types --test tests/*.test.mjs
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build
```

界面复核重点：在行程页看具体人数、配套及营地费理由；展开备选营地比较同一类事实；有目录营地应按日期显示具体安排和离营准备，所有时段均为建议。查看历史和最终记录不能发起新模型调用，未知天气、道路关闭和实际装备缺口仍按原流程处理。


## 第一版验证（2026-10-29；不代表下方扩充后的最终结果）

- 最终后端全量：**1937 passed，0 failed / error / skipped**。四组独立目录为 485 / 484 / 484 / 484 项，已核对收集清单一致、无重复遗漏，源码在全量前后不变；不是旧全量与局部复测相加。用时 316.9 秒。
- 完整证明：`var/itinerary-final-full-confirmed/verified-summary.json`；后端源码/测试/新增活动资料 SHA256：`d967ec66de2230fa7f68bcefbf86573ea111a97848b42accec957e4d06c606db`。真实 HTTP 尝试 **0**。
- 首次全量 1937 项有 1 项失败：旧测试将交通政策错误限定为完整 rules_version 的最后一段。修正为精确政策段只出现一次后，执行上述新的完整全量。首轮证据保留在 `var/itinerary-final-full`，不称首轮全过。
- 前端最终：**182 passed，0 failed / skipped**；TypeScript、Vite 生产构建和 Git 空白检查通过。
- 共享契约、Safety v3、compact Safety schema 检查通过；新内部规划 schema 与实际生成结构逐项相等。
- 原封存包校验：2.0 的 31 项、2.1 的 11 项、Sydney 2.2 的 11 项文件摘要全部未改变。
- 原有 Starlette TestClient 弃用提示和 Vite 大 chunk 提示仍在，不影响本轮通过。没有真实校园模型或交互式浏览器验收。


## 活动扩充版 camp-activities-2（2026-10-29）

- 新运行默认使用 `b_planning_details=camp-activities-2`，独立文件 `data/planning/camp_activities_v2.json`，共 30 条，覆盖全部 10 个营地。每营地两项营位内轻量休闲选择及一项离营整理；增加色彩／光影观察、可选摄影、口头游戏和旅行故事等。可以独自参与，不强制携带拍摄设备或额外道具。
- The Basin 原先没有活动目录，因此截图仍为住宿／自由安排。扩充后，模型可选择该营地的“营位自然观察与趣味摄影”或“营位故事接龙与休闲”；每个住宿日仍一项建议活动，另有过夜条目与离营日整理。
- 仍使用已有 `daily_plan(date, activity_id)` 内部协议及建议时段（13:00–16:00、17:00 住宿、最后一天 10:00–11:00 整理）。未改模型 Prompt、输出 schema、token、超时或重试；不伪造全天逐小时安排、已开放活动、交通时间或预订。
- 全部新活动明确是模拟建议、营位内、低强度、不增加固定费用／装备／预约。没有把游泳、外出徒步、真实导览或收费项目加入识别范围。正式天气、道路、用火、装备及保存资格继续由现有检查决定；来源、描述、日期或时段不符仍不能作为目录内活动识别。
- `camp_activities_v1.json` 保持原字节，SHA256 为 `da0028a43cbb056e247a442a4bcf50b948f2517c41b935fdfbc4d5dfaca0a230`。旧策略 1 继续绑定文件 1，新策略 2 绑定文件 2，SourceRef 的文件身份相应区分。没有策略标记的旧运行继续旧协议；恢复不能自动换版，已保存的旧版本／最终记录不追加活动。
- 前端只从保存的活动描述提取标题，在卡片中展示活动名称、所属营地、模拟标记及建议时间，不查新目录填充旧行程。
- 没有数据库迁移或共享 DTO 变化，没有修改原用户数据库、个人环境、密钥或封存包，没有调用真实校园模型或重启服务。用户重启后端后，新建出行或经“修改需求与资料”确认创建后继方案，才会生成扩充后的新版本。旧运行恢复、同版本 REASSESS 继续固定的策略与保存行程；单纯刷新旧方案不补写活动。
- 本轮离线验证结果完成后记录于下方，不能把第一版全量与本轮局部测试相加作为最终全量结果。


### 活动扩充版最终验证

- 当前最终组合后端全量 **1950 passed，0 failed / error / skipped**；四组 488 / 488 / 487 / 487 项，完整收集清单一致且无重复遗漏，执行前后后端源码、测试和活动文件摘要一致。用时 472.3 秒，真实 HTTP 尝试 0。证明：`var/activities-expanded-full/verified-summary.json`，源码摘要 `5a6da810813aab7ef6bba40f7302d3226ca5c25edba2abd3157d874b1f6131ba`。
- 前置针对性 70 项、已有行程回归 14 项分别通过，但不计入上述全量总数。覆盖全部十个营地、The Basin 两轮 MockTransport 规划、真实 Agent 身份、未知活动拒绝、旧目录字节／来源身份、保存丢回执恢复、重评不重跑规划和最终快照回读。
- 最终前端 **197 passed，0 failed / skipped**；TypeScript、Vite 生产构建、Git 空白检查通过。使用保存的中文活动名作卡片标题；原有英语休息条目不会从当前目录自动增添模拟活动。
- 封存包 2.0 / 2.1 / Sydney 2.2 的 31 / 11 / 11 项摘要均未变化；旧活动文件 1 保持原摘要。没有真实校园请求、服务重启、原用户数据库迁移或 commit/push。
- 尚未进行真实校园模型／浏览器生成验收。未提供完整交通路线、徒步、水上、收费活动或全天逐小时计划；当前是一项下午建议活动、夜宿及离营整理，空余时间由用户安排，模型不能编造未入目录的项目。
