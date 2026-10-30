# 人工审核闭环与 Stage 1 对齐

初始开发基线 main ffc28dc。用户确认本轮占用数据库迁移 14；不得复用 13。开发验证阶段未重启服务、未迁移原用户数据库、未调用真实模型。后续用户授权的部署与提交前组合验证见文末。

## 精确接口与阶段

1. 复用 `POST /plans/{plan_id}/revision-proposals`（以及原 revise）增加可选 `source_review_id`。服务端通过本人当前方案、run、版本、原评估集合读取不可变的 REQUEST_REVISION/REJECT 记录，以版本化 CampMate review-linked revision v1 信封固定保存来源审核 ID、被审版本 ID、原理由及用户确认的修改指令，沿用运行 scope 的 revision_feedback 恢复。模型只接收正文，不接收内部审核／版本 ID；完全相同的采用意见不重复发送。既有 change/cheaper campsite 严格目标检查仍生效，正文合计超 4000 字符在派发前拒绝，不截断原意见。新反馈协议将 coordinator_version / validation_version 附加 -review-feedback-1，旧运行身份保持不变。界面“采用审核意见”仅准备输入，用户明确提交才启动原模型修订和待选方案比较；不自动修改预算、库存或确认需求，不继承旧批准。
2. `POST /review/{plan_id}/assistance`：Founder 专用，绑定 version_context、两份 assessment_ids、expected_version_revision、expected_run_revision 和 command_key。decision 为 WAITING_EVIDENCE / NEEDS_CAMPER_INPUT / UNSUPPORTED，必须有 problem、reason、next_action，可选 recheck_on。只追加意见，不更新原评估、路由、资格、审批或最终记录。待选修订未决定、历史／已删除／被取代结果拒绝写入。与 APPROVE/REJECT/REQUEST_REVISION 严格分开。
3. 需求协助 decision 增加 UNSUPPORTED；仍保存为原 RETURNED 任务状态，通过 response.decision 区分，避免复用数据库约束或引入虚假的批准。新界面发送 feedback_version=structured-help-feedback-1；退回与暂不支持必须填写具体问题、理由及用户下一步。旧请求格式与已保存短理由保持可读。未知要求不能因人工处理而视为满足。
4. `GET /plans/{plan_id}/finals/{final_id}/pdf`：复用原最终读取的本人／删除／完整性校验，只导出已保存 FINALISED 快照。使用明确业务字段，不导出 trace、usage、配置、指纹；不读取当前资料补写旧快照，不发模型请求，不改变保存内容或哈希。历史最终可导出但明确标注，不授权新结果。失败可重试，最终记录保持不变。
5. `GET /review-history?decision=&offset=0&limit=30`：Founder 专用分页，按原 plan/run/version 返回已处理决定；旧记录通过 `/review/{plan_id}?run_id=...` 只读。原队列筛选及服务端守卫保留。`GET /requirement-help?history=true` 补充已处理／失效协助记录，隐藏已删除来源，旧建议不能回写当前要求。

## 数据与依赖

迁移 14 仅新增 review_assistance_notes 与 review_assistance_commands；追加记录、事务回执不可更新／删除。不改迁移 1–13，不修改既有审批表或最终记录。PDF 使用固定 ReportLab 4.4.9；运行依赖与 lock 同步。测试依赖增加 pypdf 6.10.0。项目随包分发约 10.6 MB 的开源中文字体（SIL OFL 1.1，已改名 CampMate Sans SC），PDF 嵌入实际使用字形子集；无需阅读器语言包或运行时下载。来源、固定上游提交与 SHA-256 见 backend/app/assets/fonts/README.md 和 OFL.txt。字体未覆盖字符以 Unicode 编号显示，原文仍保留于网页保存记录。

## 验证与边界

验证应覆盖：审核意见真实来源与跨用户／旧版本拒绝，重复提交和丢回执，等待资料不改变资格，暂不支持不能采用／批准，新旧反馈兼容，历史权限及删除边界，PDF 仅本人已保存最终、失败不损坏保存、无诊断泄漏、中文与长文字分页、恢复不重复模型执行。最终全量单独记录，不能累加旧全量与局部复测。

不做多级审批、自动邮件／出发提醒、直接更改评估或解除硬性限制。没有新增未知需求验证能力；报告中“保持升级等待信息”通过独立人工处理记录表达，不把原 BLOCKED 业务状态强制改为可审批。


## 界面使用与人工验收步骤

1. **原审核要求修订／拒绝**：Founder 在原风险审批保存理由；Camper 打开当前方案，点击“按审核意见准备修改”或调整区的“采用这条审核意见”。核对文本后点击“生成待选方案”，才执行正式修订。原方案仍保留，用户比较后选择是否采用；新结果不继承旧批准。准备、刷新和查看历史不会调用模型。
2. **需要资料／用户补充／暂不支持**：Founder 进入“修正／协助（不可审批）”，填写具体问题、原因和下一步，可选等待资料的重查日期；保存仅增加处理记录。Camper 在对应方案看见意见，等待资料后明确重查，或核对修改需求。新评估不携带旧协助作为新结论；此前 run 的意见可只读回看，即使同一版本后来重评通过。
3. **规划前的其他要求**：需求协助可选择“退回补充”或“暂不支持”。新表单必须给出具体问题、理由、用户下一步；不能用模糊“不同意”直接放行，也不能将无法核实的要求映射成已满足。旧短反馈保留原样读取；映射仍须 Camper 明确采用并重新生成摘要。
4. **已处理记录**：Founder 审核列表选择“已处理／历史”，可按批准／拒绝／要求修订筛选、分页并打开精确历史 run。需求协助另有“已处理”和“历史／失效”分类。已删除的方案、请求或系列不能借历史入口重新读取。
5. **导出 PDF**：Camper 打开本人已保存的最终记录，点击“下载已保存方案 PDF”。不能导出草稿／待审作为最终方案；历史最终标注历史，仅包含当时保存的业务内容、来源日期及审核理由，不带模型诊断。Founder 不新增跨用户最终记录导出权限。

## 文件索引

- 持久化与读取：storage/database.py、review_assistance.py、review_followup.py、review_history.py、reviews.py、requirement_help.py、plan_queries.py。
- HTTP：http_plans.py、http_reviews.py、http_requirement_help.py。
- 修订边界：contracts/revision_feedback.py、llm/coordinator.py、llm/planning_schema.py、agents/rules/planning.py。未改装备／安全政策、正式输出 schema、token 上限或重试配置。
- PDF：application/final_pdf.py、assets/fonts/、backend/pyproject.toml、requirements.lock。
- 前端：review_revision.ts、review_assistance.tsx、final_pdf.tsx，以及 planning / plans / next_steps / reviews / requirement_help / finals 和局部 styles。
- 回归：test_human_review_completion.py、原迁移版本相关测试、display_presentation.test.mjs、structured_requirements.test.mjs。

## 部署与 A 交接

- 本轮迁移 14 已由用户分配；与 A 合入前确认没有其他迁移重号。没有改动迁移 1–13、既有最终快照、审计或封存资料。
- 初始开发验收时服务仍运行旧进程，未对 var/sydney/campmate.sqlite3 运行 initialize。应用新代码前须先备份实际数据库、安装依赖并确认 schema 14；本机后续授权重启已完成，见文末。
- 迁移 14 是只增表／触发器；回退旧代码会因 schema 就绪校验拒绝该数据库。不要删表降级已写入的人工作业记录；需要回退时使用升级前的备份并协调部署。
- 不新增 A-owned AgentPort/RecoveryPort 方法；复用既有命令回执、运行固定 scope、checkpoint、heartbeat、原审计保存和恢复。审核来源反馈的重放仍由原 workflow 完整命令哈希验证，不通过文本授予权限。
- 后续真实联合验收须由用户明确启动；离线回归和组件渲染不等于校园模型／浏览器联合验收。
- 未实现多级审批、自动消息／提醒、外部证据采集、任意新需求验证或公共通用豁免。独立协助意见保存在对应 run，不进入最终快照充当批准。


## 最终组合验证（2026-10-30）

- **最终后端全量：1,988 项全部通过，0 失败／错误／跳过**。四个互斥分片各 497 项；验证收集清单一致、无遗漏无重复，检查期间源码指纹一致，真实 HTTP 尝试为 0。机器结果：var/human-review-final-full/verified-summary.json。
- 首次完整检查同样收集 1,988 项，仅有两处旧断言失败：迁移列表仍到 13，以及 main 已有 revision_proposal_id 轻量进度字段未被测试认可。适配测试后从头执行上述最终全量；没有将首次结果与局部复测相加。
- 新增审核闭环针对性测试 23 项通过，包含当前来源／历史／跨用户、同版本重评后旧协助可读、删除边界、命令并发与事务回滚、等待资料不能放行、暂不支持不能采用、历史分页、PDF 访问及无诊断投影。另通过直接 revise HTTP 丢回执验证：active_run 已改变后仍返回原运行，同 key 不同内容拒绝、不创建第三次运行。
- 全部前端测试 **208 项通过**，类型检查、生产构建、共享 schema --check、git diff --check、依赖一致性检查通过。
- v2 静态校验 **68 项通过**；v2.1 发布／导入／覆盖检查 **24 项通过**。三个数据包封存摘要分别 31／11／11 项一致，未改封存数据。
- PDF：标准两页逐页实际渲染核对，中文正常、装备标题随表格移到下一页、页脚正常；长文本、XML 特殊字符及字体未覆盖字符回退测试通过。离线 wheel 中字体摘要与源文件一致且包含 OFL 许可证；此 wheel 仅用于字体打包检查，不是发布包。
- 非阻塞既有提示：FastAPI TestClient 的 httpx 弃用提示；Vite 主包大于 500 kB。未为此升级框架或改动拆包。

最终后端源码／测试／字体／依赖指纹：`bfa158815963753f128eeb0d1c4fe3425d14fe8ff5121f773a7263c71c9d0198`。

可串行复现（无需四分片辅助文件）：

```sh
cd /Users/bibabu/_Code/github/ELEC5620-G19
PYTHONPATH=scripts .venv/bin/python -m pytest -p v22_offline_transport_guard backend/tests --basetemp=var/pytest-human-review-check --tb=short -q
cd backend
../.venv/bin/python -m app.export_contracts --check
cd ../frontend
node --experimental-strip-types --test tests/*.test.mjs
node node_modules/typescript/bin/tsc -b --pretty false
node node_modules/vite/bin/vite.js build
```

没有执行真实校园模型、实际浏览器联合验收或原用户数据库升级。没有自动 commit、push、合并或切换分支。


## 后续部署及提交前最终组合（2026-10-30）

- 当前功能分支 feature/human-review-completion 已包含 main 701700c，以及 767fc43 / b26fb59 的界面和测试夹具修复。原来的 1,988 / 208 是先前基线的结果，不作为本次组合结果。
- 用户授权单独重启后端，先通过 SQLite backup API 备份到 var/sydney/backups/campmate-pre-schema14-20261030-143007.sqlite3，确认完整性后加载迁移 14。健康检查 ready，新需求协助 history 参数、审核历史和 PDF 接口均已加载；原前端进程保留，agent / model / model / compact 和 4096 / low 配置保持。原业务表记录数量与备份一致；未发起模型调用。
- “测试审核”任务仍为 PENDING 且 current=true；此前误入历史分类是新前端连接旧后端导致列表缺 current 字段，并非原需求失效。重启后按新接口返回有效待处理任务。
- 本次提交前完整后端 **1,989 passed，0 failed / errors / skipped**，四组 498 / 497 / 497 / 497，收集清单无重复遗漏，源码在执行前后保持一致；真实 HTTP 尝试 0。机器记录：var/human-review-push-final-full/verified-summary.json。
- 当前全部前端 **232 passed，0 failed / skipped**，包含需求对照、完整确认清单、人工审核、统一检查状态和资料页底部添加装备入口；TypeScript、Vite 生产构建、共享 schema --check、Git 空白检查通过。Vite 保留原有大 chunk 提示。
- 手工测试的 9 套输入确认使用独立 var/manual-state-* 数据库及 rules-only 模式，启动器语法通过；手册／50 个接口清单属于验收计划，不冒称浏览器或真实校园模型验收完成。
- 数据库、备份、日志、个人环境与密钥不纳入提交；没有合并 main。首次验证与局部复测数量没有累加为本次全量。
- 最终组合源码摘要：`577ac8f7d57972c48a08a491f545fb2b6be24382c81c5d4407f1b27bd5e0bf9b`。

提交空白检查补充：仅移除字体 OFL 许可证原文的一处行尾空格，许可条款文字不变；此文本格式整理在全量检查后完成，不涉及运行代码。
