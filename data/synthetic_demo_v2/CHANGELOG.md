# v2 修改说明

## 2026-10-11 发布封存修复（A）

- 使用明确的发布文件清单生成 manifest，排除未交付的 pycache/.pyc 及本地运行产物。
- 发布文件使用 UTF-8/LF；CSV 生成器显式写 LF，与 Git 导出字节一致。
- 数据包自带 LF 属性，Windows core.autocrlf=true 下单独 Git 导出数据子目录仍保持封存字节。
- 校验包含完整发布文件清单和真实字节摘要；生成报告后同步封存报告，避免报告更新使 manifest 失效。失败检查不会自动重签输入。
- 业务输入、费用规则、fixture 语义及应用 NOT_RUN 状态保持原修订版内容；此项仅修正可重复发布，不代表应用端到端验收完成。

## 2026-10-11 审查修订

- 统一自炊模式为 `SELF_CATERED`；该模式在禁火时触发炉具与锅具要求，并仅选择 cost-04；`READY_TO_EAT` 不触发炉具/锅具且只选择 cost-14。
- 费用 Adapter 改为 Decimal 解析、逐项 `ROUND_HALF_UP` 转整数分后求和；新增 3.5 km × AUD 0.35/km = AUD 1.23 的半分边界校验。
- test-34 自启动起固定 demo clock 为 2026-11-06 08:00，不再在同一流程推进时钟。
- test-43/test-56 改为完整 gear/logistics/safety 前置状态，以 Founder 审核、Camper 所有者最终化，断言具体 `FINALISATION_BLOCKED` 原因；新增 test-57/test-58 条件解除后的配对控制。
- fixture actions 支持显式 actor override，以准确表示不同身份先后操作。
- 执行 `python3 scripts/repair_review_findings.py` 可重建修订 fixture 和 manifest 校验和；执行 `python3 scripts/validate_dataset.py` 可运行静态校验。

修订日期：2026-10-09。原始 Downloads/campmate_synthetic_demo 保持不变，原始 10 个文件的 SHA-256 存于 manifest.json。

| 检查意见 | 已完成的数据修订 |
| --- | --- |
| 2.1 FR 错位 | 原 30 条按正式 FR 重映射；新增 Profile 正常操作、全流程与权限/版本/恢复等规格，共 56 条 |
| 2.2 晚数/天数 | 新增 duration_nights/end_date，duration_days 为晚数+1，保留 legacy_duration_days；request-03 同时缺日期和晚数 |
| 2.3 语义引用 | 去除 test-09/10/12 等无关安全引用；安全组件去除无关 Request；test-30 使用 profile-a 的组件上下文与 cloud-gully；test-23 复制为 safety-12，覆盖 Nov 4–6 |
| 2.4 字典与状态 | weather/fire/road_access 改为 object；完整字段表和嵌套 schema；五类状态/断言分别定义 |
| 2.5 oracle 隔离 | 预期标签移入 tests/synthetic_oracles.json；提供 allowlist 运行时输入；合法初始请求仍未确认 |
| 2.6 计算参数 | 增加归一化装备、人数、车辆/公里字段及 JSON 规则；未知值为 null；新增完整供应与费用的成功 fixture |
| 2.7 路由与守卫 | REVISION 可有 blocker；高风险必须升级；safety-09 改 REVIEW；人工批准不能绕过 blocker/缺失证据 |
| 2.8 时间与前置条件 | 固定/可注入 demo_clock，模拟观测/有效期，STALE 明确过期日；倒置日期、复杂筛选、旧审批、失败注入皆有结构化动作 |
| 3 缺失场景 | 两 Camper 越权读写、Founder 决策/理由、blocker 守卫、新版重评、snapshot、幂等/迟到结果、保存回滚/恢复、适配器/干净环境规格 |
| 4 报告范围 | 报告仅声明静态数据检查；所有应用规格 NOT_RUN；测试记录补来源元数据 |

## 2026-10-12 数据与验证更新

- Added safety-13/safety-14, synthetic coverage for Pine Camp and River Flat during the two-night budget-revision demo (2026-10-27–29).
- Shifted safety-06 and its matching component fixture to 2027-04-10–13, within Cloud Gully's synthetic autumn availability; the road remains CLOSED.
- Kept safety-02 weather evidence MISSING intentionally. Its fire and road evidence already cover the River Flat test trip.
- Added independent test-only expected outcomes for safety-13/safety-14; they are not Agent evidence inputs.
- Re-sealed all 31 registered release files. Static package validation: 68 passed, 0 failed; the generated report and manifest checksums are current.
- Full backend suite: 485 passed, 0 failed; shared JSON Schema check passed. The suite reports one Starlette deprecation warning for the test-client `httpx` dependency.
- These results do not claim browser acceptance or the complete authenticated HTTP retry/reassessment flow; those remain outstanding integration acceptance work.

新增业务记录：request-13 完整成功输入；safety-11 为 safety-01 的 Nov 6–8 新上下文；safety-12 为 safety-05 的 Nov 4–6 新上下文。
新增明确演示假设：安静与无台阶属性、装备阈值、场景数值证据及有效期、成功路径的用品与总车公里。原有未知 family tent 容量与 torch 数量没有猜填。
默认费用仍是原 v1 典型参考值，全部为 SYNTHETIC。示例成本不代表真实价格。

## 2026-10-12 HTTP 演示输入对齐

- 新增 safety-15（Wattle Rest 正常）、safety-16（Wattle Rest 超预算）、safety-17（Moonlit Field 低价修订）与 safety-18（Moonlit Field 封路）。均为明确标注的合成事实，不修改营地排名或现有业务记录。
- runtime_safety_evidence 由相同业务记录的 allowlist 映射同步生成；独立期望仅保存在 synthetic_oracles。safety-16 的安全评估通过不代表整份方案可最终化（费用超预算）。
- 四套真实 HTTP 输入位于应用仓库 docs/demo/v2_inputs.json；不用手工筛选或指定候选营地。预算为 AUD 245，自动推荐的 AUD 251 方案可修订至 AUD 231。
- 数据包静态验证不执行应用测试；应用端验证结果与范围见仓库 docs/v2_runtime_integration.md。上节 485 项结果是此前组件测试阶段的记录，不是本轮锁定环境的验证结论。

## 集成仍需执行的工作

接口与状态约定已具体化，A/B 仍需将其接入实际应用、真实权限与数据库事务，再执行全部 56 条规格。
适配器替换/干净启动测试列出了可执行动作协议；实际启动命令和端点由应用仓库提供，本数据包没有构建 React/FastAPI/SQLite。
不把参考报告或评分文件中的后续编码建议扩大成当前用户要求。

## 对照材料

- synthetic_data_review.md，2026-10-08，原检查意见。
- 5620_stage1_report(2).pdf，第 5–7 页 FR/NFR，第 24 页 Agent/应用写入职责，第 49 页验收计划。
- ELEC5620 Project Stage 2 Marking Criteria.pdf，评分标准仅作为背景，不构成本次额外开发任务。
- docs/original_validation_report_v1.md 是原报告归档，不是 v2 当前结论。
