# CampMate v2 静态验证报告

验证日期：2026-10-11。共 68 项检查，68 项通过，0 项失败。

业务数据：10 个营地、30 条装备规则、16 条费用参考、5 个资料、13 个请求、12 个安全场景。
测试规格：58 条，每条都有独立 fixture、身份、动作与预期，全部为 NOT_RUN。

## 验证范围

本次执行 JSON/CSV 解析、唯一性、类型转换、来源标记、FR 追踪、身份/营地/日期语义、fixture 对象与版本引用、场景有效期、输入隔离以及示例装备/费用公式计算。
成功 fixture 的典型费用为 AUD 261；这是输入与预期的算术复核，不是 Agent 运行结果。
request-08 在 demo-lake-meadow 的两晚营地费为 AUD 110，已超过 AUD 50 预算。

## 尚未验证

没有运行 React/FastAPI、三个业务 Agent、数据库、身份认证或完整应用测试。
审批、阻止最终化、事务回滚、重试、资料 snapshot、适配器替换及干净环境启动目前均为待执行验收规格。
test-17、test-19、test-21 仍是组件级规格，不等同于完整低成本重规划、缺失证据或封路行程集成演示；应用接线后仍需补齐这些场景的端到端步骤。
FR 编号与正式 Stage 1 语义已对齐；这不等于需求实现已覆盖或通过。
A/B 仍需采用 docs/integration_contract.md 中的 v2 接口及路由约定。

## 检查结果

| 静态检查 | 结果 |
| --- | --- |
| Unique/nonempty campsite_id | PASS |
| Unique/nonempty gear_rule_id | PASS |
| Unique/nonempty cost_id | PASS |
| Unique/nonempty profile_id | PASS |
| Unique/nonempty request_id | PASS |
| Unique/nonempty safety_case_id | PASS |
| Unique/nonempty test_id | PASS |
| Unique/nonempty fixture_id | PASS |
| Synthetic provenance on every data/test/oracle record | PASS |
| Fixed manifest clock | PASS |
| Manifest counts match files | PASS |
| Cost ranges ordered | PASS |
| CSV false values converted to false | PASS |
| Profile child/adult counts reconcile | PASS |
| Unknown tent capacity/torch count preserved | PASS |
| Unconfirmed candidates do not imply confirmed equipment | PASS |
| Request ownership and snapshots | PASS |
| No business request starts confirmed | PASS |
| Two nights derive three days | PASS |
| All canonical durations/end dates reconcile | PASS |
| request-03 missing date AND duration | PASS |
| Missing budget differs from invalid budget | PASS |
| Business records contain no oracle labels | PASS |
| Runtime inputs contain no oracle labels | PASS |
| Runtime files match allowlist adapters | PASS |
| Oracle/candidate contamination cannot change Agent inputs | PASS |
| Original 30 tests semantically remapped to Stage 1 | PASS |
| FR-01 to FR-10 specification traceability | PASS |
| All acceptance specifications explicitly NOT_RUN | PASS |
| Every test has fixture and oracle | PASS |
| All nonempty cross-file IDs resolve | PASS |
| Test user/campsite/trip scope consistency | PASS |
| Plan versions, links, actors, actions and isolated fixtures | PASS |
| Observations do not come from future fixture clocks | PASS |
| Known mismatched safety references removed | PASS |
| Impossible constraints and reversed dates are explicit | PASS |
| Impossible accessible/walk-in/no-fire filter yields no record | PASS |
| Oracle policy prevents unsafe automatic eligibility | PASS |
| Fixable blocker and escalation modeled independently | PASS |
| Approval blocker case isolates FINALISATION_BLOCKED cause and owner actor | PASS |
| Missing safety evidence case isolates FINALISATION_BLOCKED cause | PASS |
| Target conditions have paired resolving controls | PASS |
| High heat escalates for human review | PASS |
| Stale evidence has computable expiry | PASS |
| Missing evidence is null, not fabricated weather | PASS |
| Context copies retain source and dates | PASS |
| Executable gear rules evaluate without missing inputs | PASS |
| Gear overlap does not double-count tents/bags | PASS |
| Self-catered fire-ban requires stove and pot | PASS |
| Ready-to-eat mode does not require stove or pot | PASS |
| Potable-site water uses 3 days | PASS |
| No-water site includes emergency day | PASS |
| Missing expression input never becomes numeric zero | PASS |
| Success fixture arithmetic independently reconciles | PASS |
| Food alternatives not double-charged | PASS |
| Half-cent money rounds per line using HALF_UP | PASS |
| Water cost uses equivalent person-days, not litres | PASS |
| Missing distance/vehicle gives incomplete estimate | PASS |
| test-17 campsite subtotal already exceeds budget | PASS |
| Success fixture uses one fixed clock and orders confirmation/all checks/save/read | PASS |
| Actual success fixture supplies satisfy every triggered rule | PASS |
| Actual fixture-derived total matches isolated oracle | PASS |
| Success request starts unconfirmed with explicit priced inputs | PASS |
| Fixtures use defined PlanVersion status enum | PASS |
| Safety oracle enums are distinct and controlled | PASS |
| Evidence status and source date formats | PASS |
| JSON record schemas validate complete files | PASS |
| Release manifest checksums | PASS |

完整机器可读结果见 tests/static_validation_results.json。
