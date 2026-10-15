# A26：按行程匹配资料的组合审查与页面验收

日期：2026-10-15。当前本地分支：`feature/a26-trip-integration`。

后续更新：新 2.1 的真实校园模型与浏览器验收已完成，见 [真实验收记录](a26_trip_live_acceptance.md)。下文保留第一轮离线集成时的结果和当时尚未验收的状态。

发布前全量 CI 补充：`2b1907e` 的首次远端运行 [38717291984](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38717291984) 为 908 passed、3 failed。三个失败都指出新增只读 `trip_evidence_coverage` 在 HTTP 中默认为 null，而基础 `PlanQueries.detail` 缺少该键，导致最终保存/部分进度重启回读的完整响应比较不一致。已在基础查询补齐默认 null；保持 HTTP 查询按已登记快照丰富当前投影，历史读取不计算新资料，不改数据库表、持久化快照或最终保存守卫。现有三项回读断言保留，不通过删字段、放宽比较或跳过测试消除失败；最终发布状态以修正提交对应的 CI 为准。

## 结论和版本

已将 B 的 `feature/trip-evidence-selection`（`5ed6e4404d54a29a44a6eb666d874c4a5c38159d`）与 A26 检查反馈（`9302642`）组合，合并提交 `fe89d4d`。B 分支同时包含物流修复 `2d8f2cf` 和验收材料 `a603a94`。本轮离线审查及规则模式浏览器验收未发现阻断问题。

本轮没有调用校园模型，没有推送集成分支或合入 main。新 2.1 数据下的真实校园模型联合验收仍待执行。B 已提供的物流真实验收材料属于先前版本的证据，不能替代本轮新数据验收；原上游失败的根因仍不能据此认定已被证明。

个人配置、私有密钥和既有用户数据库未修改。Canvas 完整部署和提交包验证遵照用户安排，留到系统完成后执行，本轮没有生成 ZIP。

## 已复核的 B 实现

- 2.1 是独立封存数据包；旧 2.0 包保留，无清库、表迁移或共享 schema 变更。
- 按确认需求、实际营地和检查日期查询资料。修订换营地后不需要更换启动场景；装备与安全使用同组选取结果和摘要。
- 区分没有资料、日期不覆盖、尚未发布、过期、来源冲突和明确关闭。道路关闭不能通过人工批准或资料覆盖完整而解除。
- 登记资料索引及选择策略身份，旧运行恢复不能混用新快照，保存产物不通过重新调用模型补造审计记录。

## 本轮 A 接入

新增已授权的只读 `trip_evidence_coverage` 页面投影，使用本次运行登记的同一快照和 B 选择器，返回具体资料缺口以及经查询验证的替代营地或日期。历史运行不使用当前资料补写，来源变化时关闭当前投影并提示重新检查。

安全页说明哪类资料不能支持此次行程，可展开已发布资料日期；有合适选项时显示最多三个营地、最多三个同晚数日期。建议检查资料覆盖、营地硬条件及基础营地费用，排除已知关闭，不代表完整费用、装备与安全已通过。选项不会写入需求或改变最终保存资格；用户进入调整页面后仍看到原需求，必须自行修改并重新确认。

自由输入保持开放，没有指定场景/日期白名单或日期输入 min/max 限制。仅缺天气资料时，不再错误地要求用户修正自己的装备资料。最终保存页面也不再引用已隐藏的检查进度区域。

## 实际执行的验证

| 验证 | 结果 |
| --- | --- |
| B 选择器、HTTP、A26 检查反馈、模型客户端及物流组合回归 | 148 passed |
| 新增投影、检查反馈、修订/重评回归 | 24 passed |
| 新包静态验证及天气查询 | 24 passed；600 次两晚行程天气查询 |
| 数据生成器 `--check` | 封存内容确定性匹配，未重写数据 |
| schema 检查 | 通过 |
| 前端 TypeScript 与构建 | 通过 |
| 浏览器真实 HTTP、SQLite、规则流程 | 通过，见下文 |

两组 pytest 有重复用例，不能相加为独立测试总数；本轮没有重新执行 B 报告的全量 900 项。JUnit 原始文件保存在忽略目录 `var/a26-trip-combined.xml` 和 `var/a26-coverage-ui.xml`，汇总另见 `evidence/a26-trip-integration-check.json`。

浏览器使用独立 SQLite 与进程级配置，检查时钟 2026-11-05、数据 2.1、规则执行，不依赖个人环境文件：

1. 正常方案 2026-11-06～11-08，先选 Wattle Rest；修改为更低费用后实际切换 Moonlit Field，第二版四类安全资料仍自动适用。
2. 保留第二版行程重评，显示本轮完成且结果相同，随后成功最终保存；保存快照仍显示第二版原行程。
3. 同一服务中另一方案 2026-11-20～11-22，天气预报尚未发布。页面如实提示并提供已查询的 11-10～11-12、11-09～11-11、11-08～11-10 可选日期，未错误放行。
4. 从资料提示进入调整需求页，仍保留原 11-20 日期、两晚及 AUD 320 预算；没有自动替换、确认或保存。日期输入无 min/max，浏览器无页面错误。
5. 独立数据库最终有 4 次运行、3 个行程版本、8 个评估及 1 份最终保存记录。测试服务已退出。

自动化另外覆盖：跨资料末端日期缺口、真正缺失天气时的其他营地建议、来源身份变化后禁用投影、历史记录不被补写、用户隔离、GET 不产生业务写入，以及资料完整但道路关闭仍禁止最终保存。

## 资料覆盖的实际边界

包内两个覆盖时段不等于任意检查日期都能取得时段内全部未来预报。天气资料还受发布时间、检查时钟、新鲜度和单份预报最长七天限制。长行程不能把多份不同时段的预报拼成一份完整安全证明；等待资料发布也不保证任意长行程最终具备完整覆盖。页面保留草稿与调整入口，不能据数据包总日期范围承诺全部日期均可通过。

## 复现命令

在仓库根目录使用已准备的虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_trip_evidence_selection.py backend/tests/test_trip_evidence_http.py backend/tests/test_check_feedback.py backend/tests/test_campus_model_client.py backend/tests/test_llm_logistics_agent.py -q -o addopts=''
.\.venv\Scripts\python.exe -m pytest backend/tests/test_trip_coverage_projection.py backend/tests/test_check_feedback.py backend/tests/test_plan_changes.py -q -o addopts=''
.\.venv\Scripts\python.exe scripts/validate_trip_dataset.py
.\.venv\Scripts\python.exe scripts/build_trip_dataset.py --check
```

schema 检查在 backend 目录执行 `..\.venv\Scripts\python.exe -m app.export_contracts --check`；前端在 frontend 目录执行 `npm.cmd run build`。以上命令均不调用真实校园模型。

截图：`evidence/a26-trip-campsite-coverage.png`、`evidence/a26-trip-final.png`、`evidence/a26-trip-coverage-options.png`。
