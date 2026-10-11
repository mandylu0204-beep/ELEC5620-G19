# v2 修改说明

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

新增业务记录：request-13 完整成功输入；safety-11 为 safety-01 的 Nov 6–8 新上下文；safety-12 为 safety-05 的 Nov 4–6 新上下文。
新增明确演示假设：安静与无台阶属性、装备阈值、场景数值证据及有效期、成功路径的用品与总车公里。原有未知 family tent 容量与 torch 数量没有猜填。
默认费用仍是原 v1 典型参考值，全部为 SYNTHETIC。示例成本不代表真实价格。

## 集成仍需执行的工作

接口与状态约定已具体化，A/B 仍需将其接入实际应用、真实权限与数据库事务，再执行全部 56 条规格。
适配器替换/干净启动测试列出了可执行动作协议；实际启动命令和端点由应用仓库提供，本数据包没有构建 React/FastAPI/SQLite。
不把参考报告或评分文件中的后续编码建议扩大成当前用户要求。

## 对照材料

- synthetic_data_review.md，2026-10-08，原检查意见。
- 5620_stage1_report(2).pdf，第 5–7 页 FR/NFR，第 24 页 Agent/应用写入职责，第 49 页验收计划。
- ELEC5620 Project Stage 2 Marking Criteria.pdf，评分标准仅作为背景，不构成本次额外开发任务。
- docs/original_validation_report_v1.md 是原报告归档，不是 v2 当前结论。
