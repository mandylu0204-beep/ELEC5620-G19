# B-01：Git v1 合成数据 Adapter

## 范围与状态

本次仅使用 Git 中的 `data/synthetic_demo`，不改动原始数据、共享契约 1.0、数据库、HTTP、前端或 Agent 注册。Adapter 是独立的只读业务输入边界，不表示规划、风险评估或端到端演示已经完成。

新增模块在 `backend/app/adapters/`。`models.py` 是 Adapter 内部的来源记录类型，不是第二套 AgentPort/PersistencePort 契约；输出的 ProfileSnapshot、Evidence、ScenarioContext 等仍直接使用共同 DTO。

## 使用方式

在 `backend/` 的 Python 环境中：

```python
from app.adapters import SyntheticDatasetAdapter
from app.config import Settings

settings = Settings(_env_file=None)
dataset = SyntheticDatasetAdapter(settings.dataset_path).load()

campsite = dataset.get_campsite('demo-pine-camp')
profile = dataset.get_profile('profile-a')
car_rate = dataset.get_cost_reference('cost-02')
safety = dataset.get_safety('safety-01', campsite_id='demo-pine-camp')
```

可枚举 `campsites`、`gear_rules`、`cost_references`、`profiles`、`requests`、`safety_cases`，或按来源 ID 精确查找。查找失败返回 `ContractFailure`，错误码为 `ADAPTER_FAILURE`，不伪装为空搜索结果。`regions` 为排序后的地区列表。

来源 ID 只标识演示数据，不是账号、授权身份、确认事件或 A 生成的业务 ID。不要直接将这些 Profile 当作已认证用户资料导入数据库。

## 加载与输入身份

只读取以下六份注册来源文件，每个文件一次读取，摘要和解析使用同一份字节快照：

```text
synthetic_campsites.csv
synthetic_gear_rules.csv
synthetic_cost_reference.csv
synthetic_profiles.json
synthetic_requests.json
synthetic_safety_scenarios.json
```

支持 UTF-8 BOM、严格 CSV 行列与 JSON 数组校验，检查所有来源记录的 v1 Provenance、重复 ID、请求→Profile 和安全场景→营地引用。拒绝越出 data 业务目录的文件 symlink，包括指向同一包内 tests/docs 的链接。文件缺失、结构或字段非法时返回 `ADAPTER_FAILURE`；不会执行包内脚本或读取 `tests/`、`docs/`。

`dataset.context` 与当前 A-09 的 `application.request_rules.data_context` 一致：版本 v1、六份原始文件 SHA-256、空 fixture/selection、`a-request-normalization-v1`。后续运行可以：

```python
dataset = SyntheticDatasetAdapter(settings.dataset_path).load(
    expected_context=confirmed_context.dataset_context,
)
```

输入身份与预期上下文不一致时返回 `STALE_CONTEXT`，不能复用旧 run。B-01 不支持未登记的场景 fixture 或选择配置，也不监控文件变化。每次 `load()` 重新读取；已有 snapshot 保持原内容，公开 DTO 返回深拷贝，调用方修改列表/字典不会污染内部快照。

`ADAPTER_VERSION=b01-v1-adapter-1` 用于实现版本说明，不代表当前 A 的 fingerprint 已额外包含该标识。B-02 上线前需与 A 共同登记实际 Adapter/业务规则版本，之后不能在旧 run 中替换映射或规则。当前模块不会自行构造确认、run、版本 fingerprint 或 write key。

## 字段转换

| 来源 | Adapter 输出与处理 |
| --- | --- |
| CSV true/false | 显式转换为布尔值；缺失/unknown 保持未知；不是 `bool('false')` |
| CSV 分号列表 | 转为字符串列表，保留顺序 |
| 经纬度、价格 | 从十进制文本读取，拒绝 float、bool、非有限数和非法范围 |
| nightly_fee_aud、low/typical/high_aud | 整数 cents；转换按 ROUND_HALF_UP；真实零保留为 0，未知保留为 null |
| Additional Equipment | 转为共同费用类别 ADDITIONAL_GEAR；其余四类同样明确映射 |
| 装备原文 | 保留 label；只提取明确数字短语；不使用 Profile notes 补数量、儿童数或容量 |
| two-person tent | quantity=1、capacity_persons=2；仍 confirmed=false |
| two/three sleeping bags | 数量为明确的 2/3；仍 confirmed=false |
| family tent、torch、first aid kit 等无明确数量输入 | 数量未知；family tent 容量未知 |
| car | vehicle 装备标识及 CAR 交通类型；车辆数、公里数未知 |
| 不能识别的装备标签 | 保留原标签，用 unmapped_ 前缀，不能假装满足已知规则 |
| Gear Rule 的触发与数量说明 | 保留规则原文，不执行 eval、不声称已完成规则引擎 |

`dataset_mapping.aud_to_cents()` 可用于明确 AUD 输入的边界转换。后续费用行直接遵循共同 `CostLine`：`3.5` 公里 × `35` cents = `123` cents；总价计算不属于 B-01。合法 JSON 小数按 Decimal 读取，不能先经 float 损失精度。

### 请求：只构造解析输入，不提前确认

`dataset.request_input(request_id, demo_context)` 返回 `InterpretRequestInput`，包含原始请求文字、关联 ProfileSnapshot 和指定的 DemoContext；dataset_version 必须匹配 v1。

不消费 `expected_request_status`、`missing_fields`、notes 等测试标签，也不将结构化 destination/start_date/duration_days/budget/preferences 摘要伪装为用户明确补充。v1 的两晚/两天冲突因此不会在 Adapter 中被静默修正；request-03 的原文没有时长，也不会自动得到两晚。

请求解析、澄清、明确补充和摘要确认属于后续 Agent/A 应用流程。零预算、负预算等无效用户文字仍送交解析，不使用默认值覆盖，不因业务输入待澄清而拒绝整个数据包。

### 安全：只转换事实，不复制风险答案

安全输出保留 weather/fire/road 的原始说明、数据状态、来源日期、限制和 risk_tags。排除 title、severity、confidence、expected_outcome、expected_actions、预计算 mandatory_blockers 和 notes；实际风险/阻断须由 B-02 根据事实与规则生成。

每个场景有四类共同 Evidence。SourceRef 的文件是安全来源文件，Evidence 的 record_id 是该营地 ID，以满足 A 的证据关系守卫；外层 SafetyRecord.source_ref 保留独立 safety_case_id。

- scenario_date 单独保留，**不当作证据有效期**。所有 v1 Evidence/ScenarioContext 的 valid_from/valid_to 保持 null；来源日期不能证明覆盖整个行程。
- MISSING、STALE、CONFLICTING 状态保留。AVAILABLE 但来源日期未知时降为 MISSING，并保留说明。
- OPEN/CLOSED 转为对应 RoadState；UNKNOWN 转为 UNKNOWN/MISSING。
- RESTRICTED 不在共同枚举中，保留 raw_road_status，同时保守转换为 UNKNOWN/MISSING 并记录原因，绝不能转换成 OPEN。
- 要求 get_safety(..., campsite_id=...) 时检查营地关系，不自动复制模板或更改场景日期。

因此，即使原数据的 safety-01 标注 PASSED，B-01 也不会产生安全通过结果。完整成功场景仍需独立、明确且纳入上下文的行程覆盖证据和已确认装备/交通输入。

## 验证方式与下一步

从 `backend/` 使用项目依赖环境运行：

```bash
python -m pytest tests/test_synthetic_dataset.py --basetemp ../var/pytest-b01
python -m pytest --basetemp ../var/pytest-b01-regression
python -m app.export_contracts --check
```

测试只修改 var 下的隔离来源副本，并检查 Git 原数据与 A 的 manifest 摘要一致。覆盖转换、未知值、半分舍入、来源身份、oracle 隔离、缺失文件、重复 ID、非法类型/日期、引用、上下文变化、读取范围和快照隔离。

本次实际验证使用临时隔离的 Python 3.12.14 环境及仓库 `backend/requirements.lock`：新增 Adapter 测试 105 项，全部后端回归 234 项均通过，共同 schema 检查通过。回归有一条依赖自带的 Starlette/httpx 弃用警告。未执行前端构建或 Agent 端到端演示；前端和应用注册未修改。

后续进度：B-02 已新增五项确定性业务能力，范围和待补输入见 [B-02 规则交接](developer_b_rules.md)。下一步 B-03 才消费 A 的 checkpoint、持久化端口和恢复租约；目前没有注册 deterministic_demo 或 agent 能力，stub 行为保持不变。
