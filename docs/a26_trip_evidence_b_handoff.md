# A26：按行程自动选择资料与独立2.1数据版本（B交接）

2026-10-15，Australia/Sydney。分支 `feature/trip-evidence-selection`，从 `a603a94` 建立，已包含 A25 `fa33ac4`、物流修复 `2d8f2cf` 和已有验收材料。提交与远端状态以Git记录为准；本轮未合并PR #5，未调用校园模型，也未改个人环境或既有用户数据库。

## 1. 修复范围及版本决定

A26所述主要是资料选择和数据覆盖问题，不是SQLite表损坏。本轮不增加迁移、不改表、不清库、不更改共享DTO/schema 1.0或正式保存签名。

原包 `data/synthetic_demo_v2/` 2.0.0保持封存。新包为 **`data/synthetic_demo_v2_1/` 2.1.0**，保留契约已经允许的v2来源族和原始来源创建日期2026-10-07，发布修订日期为2026-10-15；资料的发布时间、观测日期和适用范围单独记录，不能将来源创建日期当成天气新鲜度。

不采用v3来源名是因为共享Provenance目前只有v1/v2两个literal；无需为此次独立数据发布扩大共享schema。Adapter明确支持2.0.0及2.1.0，不接受任意未知后续版本；2.0.0仍沿用历史显式场景路径，不改变旧演示或历史验证器。

## 2. 选择器返回结构（E-01/E-02）

内部类型/实现位于 `backend/app/agents/rules/trip_evidence.py`，不属于共享DTO或模型trace。

```python
selection = workflow_configuration.resolve_trip_evidence(
    confirmed_requirements, actual_campsite_ids, demo_context,
)
# 底层同签名：dataset.trip_evidence_selector.resolve_trip_evidence(...)
```

返回 `TripEvidenceSelection`：

| 字段 | 实际类型/语义 |
| --- | --- |
| selected_case_ids | list[str]；真正采用的来源记录ID，稳定排序 |
| scenario_context | 原ScenarioContext；查询范围、实际营地及逐条Evidence/SourceRef |
| weather_facts_by_campsite | dict[str, WeatherFacts]；temperature_min_c/max_c、forecast_rain_mm、wind_kph，Decimal或None；JSON为十进制字符串或null |
| coverage_issues | list[CoverageIssue]；区分资料质量问题，不把明确CLOSED说成缺资料 |
| selection_digest | SHA256；策略、登记索引摘要、完整查询、选择结果的规范化摘要，不包含自身 |

`CoverageIssue`字段：`campsite_id`、`kind`、`code`、`requested_range`、`available_ranges`、`uncovered_ranges`、`reason`。范围对象均为`{start, end}`（包含两端日期）。kind为WEATHER/FIRE/ROAD/RESTRICTION，code为MISSING/OUTSIDE_VALIDITY/NOT_YET_OBSERVED/STALE/CONFLICTING/ROAD_STATE_UNKNOWN。

`available_ranges`仅列已发布/观测、未过龄的已知来源区间；不代表最终出行获批。没有单条完整覆盖但若干部分区间并集无缺口时，仍报告OUTSIDE_VALIDITY、说明首版不拼接，`uncovered_ranges`可以为空；不能把这个限制谎称为物理日期缺口。

A可从当前run的已登记binding、保存确认需求和实际版本查询上述对象，再按A-owned GET扩展投影覆盖信息。不要将这些新字段塞进严格模型trace或允许前端传入内部场景ID。

## 3. 策略与日期语义（E-03）

- 先按实际营地、资料种类、行程日期筛选，再核对发布与观测时间；不按测试名称、预期结果或请求文字匹配。
- 检查时钟来自DemoContext.demo_today。按Australia/Sydney的日粒度比较带时区时间戳，不读主机当前时间；共享输入没有时分秒，本轮不声称提供小时级“检查时间”。
- 天气记录最长7天，观测最大年龄7天；本包其他资料最大年龄45天。阈值在登记的源记录中并纳入完整索引摘要。
- 未来观测/尚未发布的记录不被提前消费。有当前完整合法来源时，不让未来的额外预报破坏它；没有当前覆盖时明确报告NOT_YET_OBSERVED。
- 每营地、每种必要资料分别检查；非重叠日期不制造冲突，不再对整个资料库取全局日期交集。
- 同时适用且真实区间重叠的来源，摘要、道路状态或天气数值不一致时标CONFLICTING；不凭“更新”或更有利自动覆盖。只有事实已全部比对一致后，才按稳定来源ID去重等价完整记录，减少模型上下文重复。
- 首版不拼接部分预报，按单条完整覆盖判定。部分ROAD CLOSED/营地关闭等明确限制仍按重叠日期保留并阻断，不能因未覆盖全程而删除。
- 多营地暂不推断住宿日期，保守要求每个营地覆盖整个行程。天气装备用已知营地的保守极值；任何营地必需天气未知则相应事实仍None。
- ScenarioContext.valid_from/to是**本次查询范围**，不是把资料并集伪造为连续有效期；逐条Evidence/SourceRef保留原适用范围，部分覆盖明确MISSING并附结构化范围问题。

## 4. 数据覆盖与异常隔离（E-05）

用户确认正常覆盖两个时段：**2026-10-20～2026-11-30、2027-04-09～2027-04-30**，共64个日期、10个既有营地。

新包共有706条正常/明确限制来源记录：640条逐日发布、最多7天的天气预报，66条按明确有效区间组织的营火、道路和营地限制记录。天气不是无限有效；提前很久查询未来行程时尚未观测，范围外/跨界日期也会报告不足。

来源、费用、装备、设施对应的6个业务/运行文件与封存v2字节一致；正常安全索引与其业务镜像独立替换，不把旧缺失/过期/冲突世界追加到正常索引中。旧异常资料单独封存在 `tests/fixtures/legacy_runtime_safety_evidence.json`，生产Adapter不加载该目录，缺资料等异常另由明确的单元/HTTP测试世界或真实越界日期验证。

保留的日期限制及来源：Ridge Lookout禁火（safety-05、safety-12；静态营地永久禁火仍优先保持）、Cloud Gully道路关闭（safety-06）、Granite Ledge营地关闭（safety-07）、Moonlit Field道路关闭（safety-18）。完整日期、观测、来源继承见包内 `coverage.json`。不查询到资料时绝不默认OPEN。

因此原“missing_evidence / River Flat”在新正常包的覆盖日期可能获得完整天气，这不是取消安全守卫，而是该故意缺失的测试世界不再混入正常数据。要验证缺资料，使用例如2026-11-30～2026-12-02的跨界行程，或独立测试快照；不要要求普通用户改内部safety_case_id。

## 5. Hybrid、编排、身份与恢复（E-04）

- 同一选择器接入规则Agent、Hybrid规则物流、模型物流基线和正式保存事实重算。Orchestrator在实际行程保存后按确认日期/营地生成SafetyInput，不需要选中营地后才登记run。
- `WorkflowConfiguration.scenario_for()`只扩展B内部可选参数；旧v2调用保留。2.1必须提供确认需求和DemoContext，禁止缺少查询条件时猜日期。
- 装备与安全产物source_refs均保留选中记录的实际case ID、营地关联及源有效期。两份assumptions另记录同一个`Trip evidence selection digest`；安全入口拒绝替换为另一套ScenarioContext。
- 装备天气未知时使用`evidence.weather.*`覆盖提示，说明需要维护资料，不要求用户确认不存在的天气值。数量、金额、预算和供应确认守卫继续保留。
- PLAN、REVISE、REASSESS走相同策略；换营地后重查，新同版本重评产生新assessment，原行程和原生成trace不复制、不重跑。
- 全部运行资料索引已由现有A入口登记原文件字节摘要；新增选择配置为`b_evidence_policy`、`b_evidence_index_sha256`、`b_evidence_clock_policy`。policy也进入数据规则版本；检查日期仍在已保存DemoContext内。
- 选择器脱离源字典保存不可变资料内容。旧run不在恢复时切换新数据：索引、版本/manifest或策略变化后，旧scope拒绝重试；原配置保留时才能按原scope恢复。历史audit和最终快照用已存事实回读，不拿当前资料改写旧结果。
- 正式保存签名、同事务audit/回执、write_key、heartbeat及checkpoint流程未改。已提交物流丢回执恢复直接复用；缺失/损坏审计不提升为RETRY、不重跑模型补trace。

## 6. A 接回及迁移步骤

现有A `inspect_dataset()`已经支持v2来源族的2.x版本，完整8文件及manifest摘要均被核验；现有v2规则/Hybrid工厂可加载本2.1包。本轮没有改A的数据库、HTTP投影、前端、工厂实现或默认设置。

显式启用新包时：

```text
CAMPMATE_DATASET_PATH=data/synthetic_demo_v2_1
CAMPMATE_WORKFLOW_SAFETY_CASE_IDS=[]
CAMPMATE_DATASET_SCENARIO_FILES=[]
CAMPMATE_DATASET_SELECTION={}
```

默认不自动切换用户现有数据根目录。旧已确认需求/FAILED任务不要换配置后强行重试；保留原包和数据库，使用新资料时重新确认需求或按A允许的规则登记新重评。换用户Profile仍需重新确认，不能重评时偷偷换Profile。

先做不消耗模型的本机检查（根目录、独立数据库；执行前停止自己之前的测试服务）：

```bash
export CAMPMATE_EXECUTION_MODE=deterministic_demo
export CAMPMATE_PLANNING_ENABLED=true
export CAMPMATE_LOGISTICS_EXECUTION=rules
export CAMPMATE_DATASET_PATH=data/synthetic_demo_v2_1
export CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='[]'
export CAMPMATE_DATASET_SCENARIO_FILES='[]'
export CAMPMATE_DATASET_SELECTION='{}'
export CAMPMATE_DEMO_TODAY=2026-11-05
export CAMPMATE_DATABASE_PATH=var/trip-evidence-manual-01.sqlite3
.venv/bin/python scripts/dev.py --backend-port 8001 --frontend-port 5174
```

如果这些端口已占用请选择其他端口，不要结束不认识的进程。在一个服务中用normal需求（11月6日、2晚、AUD320、quiet与ready-to-eat meals）规划，再选择“更换营地”，无需更改后台资料ID。A核对后再显式启用agent/model；本轮不追加真实付费验收。

A26自己的`check_feedback/current_inputs_state`及页面不在此分支，需A把其尚未发布的增量与本分支共同集成。B提供结构化结果供A接覆盖提示和真实可验证的替代选择；没有声称这些A-owned新页面已经完成。

## 7. 验证与明确未验收范围

- 新包静态封存/导入/有限覆盖检查：24 passed，600个范围内两晚天气查询；报告 `docs/evidence/trip-evidence-static-check.json`。这不是完整HTTP或模型验收。
- 原封存v2静态检查68 passed；未改写报告、未运行原包`--write-report`或重封存。
- schema 1.0检查、前端TypeScript/Vite构建、pip依赖一致性、确定性新包生成比较通过。使用根目录`.venv`的Python3.12.15/Pydantic2.13.5，不使用backend目录另一个旧环境。
- 新增选择器边界与HTTP业务/恢复测试29项，在最终全量回归中全部通过；全量 **900 passed、0 failed、0 skipped**（226.85秒）。唯一警告为既有Starlette TestClient/httpx弃用提示，依赖锁未改。完整摘要见 [a26-trip-evidence-check.json](evidence/a26-trip-evidence-check.json)；模型均为MockTransport，未读取/输出密钥或请求校园推理服务。
- 早一轮在并发负载下碰到旧5秒HTTP测试等待期限，当时业务已保存至ROUTING、没有业务错误。仅新测试模块使用20秒有界只读轮询，不增加RETRY或模型请求，不更改生产超时、heartbeat、重试策略；上述最终全量已通过。复跑命令：`cd backend && ../.venv/bin/python -m pytest tests -o addopts='' -q --basetemp=../var/pytest-evidence-final-all`。

尚未执行：新2.1配置的真实校园模型/浏览器联合验收、A26页面和覆盖提示合并后验证、Canvas下载全新目录启动或另一台电脑部署。A25已有物流修复/补测记录独立保留，不把新增选择器当作502服务端根因解决证明。

本提交供A复核后决定后续PR/集成；不包含向A自动发消息、创建PR或合并main的操作。
