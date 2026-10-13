# A 对 B 模型修订与同版本重评的审查回复

日期：2026-10-13（Australia/Sydney）。审查 PR [#4](https://github.com/LyraWangDev/ELEC5620-G19/pull/4)，提交 `22f0681c31519666f140148d2e1c60800eaec4d6`，共同基线 main `9996e74`。本报告只确认所列代码审查与离线验证，不代表真实校园调用、浏览器闭环或 Canvas 部署验收已经完成。

后续状态：A19 已解决 R-01、完整整合 A18，完成真实校园修订、同版本重评、浏览器及受控保存恢复验收，见 [A19 实测](model_revision_reassessment_live_acceptance.md)。下文保留 PR 初次审查时的结果与边界；最终 Canvas 部署仍未验收。

## 结论

A 接受 `origin-version-v1` 的设计与现有实现方向。没有发现本轮变更放宽跨用户权限、最终化 blocker 或版本与 trace 的原子保存要求。合并前需要修正下面的页面提示，并完成真实校园修订、重评及浏览器验收。

PR #4 已在远端创建，当前 OPEN，尚未合并；所审查提交的 push / pull_request CI 均为 SUCCESS。附件末尾“未 commit/push”为过时描述，远端现状以该提交和 PR 为准。

## R-01：页面顶部与实际能力冲突（P2）

`frontend/src/App.tsx:56` 在 `features.model_planning` 为真时仍显示“首版不支持修订或重新评估”。本分支已返回 PLAN、REVISE、REASSESS 三种能力，并启用方案页的修订和重评按钮，因此每个模型页面会同时出现相互矛盾的信息。

建议按 `/api/v1/meta` 的 `supported_operations` 显示实际能力。新分支应明确说明：初次规划和修订调用校园规划模型；同版本重评复用行程，装备、费用与安全仍由规则计算。旧 PLAN-only 模式仍可显示其原有能力限制。此项属于 A 前端接线，可由 A 在联合集成时处理。

## 已确认的接口与守卫

- 工厂完整透传登记的 `a_revision_feedback`；A 审计升级至 `a-model-audit-v2`，并登记 `a_model_trace_binding=origin-version-v1`。共享 schema 1.0、保存接口签名和数据库结构未改变。
- PLAN / REVISE 的新版本与新 trace 仍通过同一 `append_model_plan` 事务保存。首次修订的原版本必须等于 A checkpoint 的完整对象；已提交产物的恢复走 checkpoint，不重复生成。
- REASSESS 的新 run / input fingerprint 属于本次评估；原 trace 按原生成 run 的配置、推荐、确认快照与内容校验。返回的是原 id、run_id、fingerprint、attempt_id 与时间，不伪造本次模型调用，也不复制 trace。
- 原生成来源必须为 PLAN / REVISE；唯一 trace、owner、内容、hash、原 fingerprint 和本次 fingerprint 的校验均继续执行。重评链始终回到原生成记录。
- HTTP owner、CSRF、当前 run / version 修订号、lease / heartbeat 与最终化的当前输入校验仍保留。重评产生新评估，不沿用旧审核，历史最终快照保持原内容。
- 模型提出确认需求变化时，返回 REQUEST_NOT_CONFIRMED 和 EDIT_INPUT，不修改确认需求、不保存新版本。目前页面只提示重新确认，未展示具体提案字段；这是明确的功能边界。

## A 在 Windows 上的独立验证

在 `var/b-revision-review/source` 从所审查提交导出独立源码，使用现有锁定 Python 环境与离线 MockTransport。未读取或修改个人 `.env` / API key，未修改封存数据，未调用校园 API，未覆盖当前本地 A18 分支或用户演示数据库。

- B 新增修订 / 重评测试：23 passed，1 条既有 Starlette 弃用警告。
- 共享 JSON schema 检查：通过，仍为 1.0。
- 前端：独立副本中锁定依赖离线安装完成，TypeScript 与 Vite 构建通过，53 个模块。
- `git diff --check`：通过。
- 完整 Windows 后端回归：659 passed、45 skipped、0 failed，525.36 秒，1 条既有 Starlette 弃用警告。44 项因本机缺少文件 symlink 创建特权而跳过；另 1 项检查 Git ignore 策略，只在 Git 仓库中运行，本次导出源码无 `.git`，因此跳过。跳过项不计为通过。

额外进行了跨实际代码版本的离线升级测试：先用 main `9996e74` 生成 A16 方案及最终快照，再用 PR `22f0681` 打开同一独立 SQLite 数据库。验证旧身份不能直接再次最终化；新身份重评成功并可再次最终化；原行程、trace 与旧最终快照保持相同；跨用户读取被拒绝。

升级验证结束后的数据库为：2 runs、1 version、1 model trace、4 assessments、2 final records。新代码阶段规划模型调用数为 0。两次最终化使用不同 command_key，原幂等冲突守卫未修改。

本轮机器可复查的原始证据位于 `var/b-revision-review/source/var/targeted-unsandboxed.xml`、`var/b-revision-review/source/var/full-review.xml` 和 `var/b-revision-review/upgrade-result.json`。这些是本地审查临时记录，不作为真实校园调用或正式提交包证据。

沙箱下 Windows 真实路径读取和 Vite realpath 曾被拒绝；解除该工具环境限制后复测通过。沙箱失败不计入产品缺陷或通过数量。

## 与 A18 集成的注意事项

本地 `feature/a18-near-matches` 已有“无完全匹配时展示最相近三个营地及具体缺口”功能，提交 `17805be`，尚未上传。B 当前基于远端 main 开发，不包含这项功能，不能以 B 的文件覆盖本地新功能。

已用 `git merge-tree` 做只读合并预检查：README.md、docs/campus_model_wiring.md、frontend/src/plans.tsx 存在内容冲突。正式集成应同时保留 A18 的 NearMatches 和 B 的 `ModelTracePanel currentRunId` 关联提示；保留本地无匹配指引与 B 的重新确认提示。不应只摘取能力开关或删除审计检查。

## 联合验收建议

1. 修正顶部能力提示，并整合 A18；在完整集成源码上重新跑相关检查。
2. 独立数据库、显式校园模式下执行真实模型修订。优先验证“寻找费用更低的营地”；记录真实模型选择与规则费用，不能强制首轮选择某个营地来凑超预算结果。
3. 修订版本最终保存后，执行同版本重评。核对没有新的规划模型调用、没有新版本或 trace、有新的两份评估，页面和最终快照明确标注原生成记录。
4. 验证已提交回执丢失后的恢复、服务重启、历史最终快照回读和缺失安全证据的放行阻止；标明故障注入与真实网络故障的区别。
5. 联合验收通过后再合 main。真实调用结果、浏览器证据和 Canvas 下载源码的现场部署演练需分别记录。

本报告未发送给 B，未发布 PR 评论，未合并 PR，也未创建正式提交 ZIP。
