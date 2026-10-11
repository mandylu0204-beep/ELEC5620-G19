# CampMate Synthetic Demo Dataset v2

根据 synthetic_data_review.md 修订的独立数据包。原始包未覆盖。

数据为 10 个营地、30 条装备规则、16 条费用参考、5 个资料、13 个请求、12 个安全场景；58 条验收规格均带独立 fixture，状态为 NOT_RUN。

## 使用

1. 先读 docs/integration_contract.md 与 docs/synthetic_data_dictionary.md。
2. Agent 请求输入使用 data/runtime_requests.json，安全证据使用 data/runtime_safety_evidence.json；也可调用 scripts/runtime_inputs.py 的 allowlist 函数。
3. 保留业务 CSV/JSON 原字段用于导入/候选摘要，依据字典严格转换布尔、Decimal 数值、数组和 JSON 表达式；货币以整数分计算。
4. 测试用 tests/synthetic_test_fixtures.json 的 setup/actor/actions/demo_clock，输出与独立 tests/synthetic_oracles.json 比较。
5. 阅读 FINAL_VALIDATION_REPORT.md 查看静态检查范围；应用验收需要实际执行。

运行无需第三方库的静态检查：

```bash
python3 scripts/validate_dataset.py
```

检查仅验证结构、引用、时间/状态预期及参考计算，不执行应用或 Agent。
每个场景启动前设置固定 demo_clock，运行中不得改变；不能根据运行电脑的今天改变演示输入。
新增假设明确标注，未知容量/数量/路程不猜填；不是实时营地、价格或安全数据。

修改逐项对照见 CHANGELOG.md。完整嵌套 fixture 类型见 schemas/。

## 当前边界

test-43/test-56 与 test-57/test-58 已覆盖审核/最终化守卫和条件解除控制；test-17、test-19、test-21 仍是组件级规格，不应当作完整预算修订或全流程安全集成演示。所有 58 条仍为 NOT_RUN，必须由接入后的真实应用执行并记录结果。
