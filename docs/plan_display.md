# A-06 规划进度与已保存产物展示

本文保留 A-06 阶段记录；后续 A-07 已接入审核与方案审核记录展示，当前状态见 [人工审核](founder_review.md) 与 [实施状态](implementation_status.md)。

日期：2026-10-10，Australia/Sydney。A 侧读取接口与页面已实现；B 的实际规划工作流及四个业务场景仍待联调。

## 页面与读取接口

`/plans` 展示当前 Camper 的真实方案列表，空数据库仍显示为空。`/plans/{plan_id}` 展示当前运行，查询参数 `run_id` 可选择该方案内的历史运行。详情包括推荐/排除理由、日程、装备数量与容量、交通可行性、费用、预算差额、安全风险与来源，以及保存时的需求/Profile 快照。

| HTTP（均在 /api/v1 下） | 返回范围 |
| --- | --- |
| GET /plans | 自己的方案索引，增加目的地、运行模式、阶段、运行/版本状态和版本号 |
| GET /plans/{plan_id}?run_id=可选值 | 一次 SQLite 读取事务中的运行、事件、推荐、版本、该 run/version 的评估与路由 |
| GET /runs/{run_id} | 同一详情响应，先按当前用户查找归属 |
| GET /plans/{plan_id}/versions | 已有的版本内容读取接口，保持原行为 |

所有接口要求 Camper 会话；Founder 无此访问权限，其他 Camper 的资源与不存在资源统一为 404。响应不暴露 scope/write_keys、owner_id 或会话字段。HTTP 保持 no-store。

## 进度与状态

活动运行处于 PENDING/RUNNING 时，详情及列表每 2.5 秒读取数据库。终结状态、历史运行或读取故障停止自动轮询；故障提示包含 HTTP trace_id，允许手动重新读取。轮询故障时保留最近成功读取的数据。刷新页面重新从持久化记录恢复，不依赖前端内存或模拟计时。

阶段依据已保存产物与 run_events，不显示虚构百分比。重新评估复用原版本内容，页面标明“复用已保存”，本次评估尚未保存时不展示上一次评估。历史路由取旧 run 的保存结果，不把当前可变版本状态套到旧运行；历史页不返回或展示当前 eligibility，确认请求链接也对应所选 run 的需求快照。

SUCCEEDED 表示该流程结束，与评估 PASSED、版本路由及 FINALISED 分开显示。BLOCKED、REVISION_REQUIRED、ESCALATED 有各自的原因和建议；技术故障展示 error code 与运行编号，已经保存的产物仍可查看。

NO_MATCH 为独立业务结果：显示排除理由，不生成假行程。持久化端口现在允许已保存 NO_MATCH 且没有版本的运行以 COMPLETED/SUCCEEDED 结束，不要求无意义的版本路由；其他运行仍须保存路由才能成功结束。这不赋予 eligibility 或最终化能力。

## 金额、数量与证据

金额按保存的整数 cents 格式化成 AUD，前端不重新计算费用；每行 ROUND_HALF_UP 由共享 DTO 校验。未知总费用、行金额和预算差额显示“未知”，真实零金额显示 AUD 0.00。已知部分小计与最终总额分开；正预算差额标为超出预算，负差额显示预算剩余。Decimal 数量保持字符串。

来源只显示文件/记录 ID、synthetic provenance、来源日期与适用区间，不把外部字符串变为可执行 HTML 或任意 URL。安全证据的 AVAILABLE/MISSING/STALE/CONFLICTING、道路状态、风险、置信度、行动建议、假设与不确定性均按实际保存字段展示。没有来源时明确提示，不能因其他评估通过而认定安全。行程与事件时间按 Australia/Sydney 显示；纯日期不转换。

## B 接入与本轮边界

共同 Agent DTO 与 schema 未改变。B 通过受限 PersistencePort 保存产物并 report_stage 后，页面即可读取；read model 实现在 backend/app/storage/plan_queries.py。RunResult 返回值本身不作为展示产物，数据库保存成功才显示。

当前没有实际 B 工厂、工作流启动/调度、执行重试、修订/审核提交或最终化服务。meta 的 plan_reading=true，planning/human_review/finalisation=false。请求确认后“开始规划”保持禁用，最终化按钮也禁用。A-06 的 B 集成与全组 Done 尚未完成。

## 实际验证

本机累计 68 项后端测试、共享 schema 对照、TypeScript/Vite 构建（46 模块）。新增 14 项读取检查覆盖部分进度、重启回读、未知费用与零金额、道路阻止、超预算修订、高风险审核、缺失/过期/冲突证据、NO_MATCH、技术故障、历史重新评估与用户隔离。

浏览器使用独立的 `var/e2e-a06-display-v2-20261010.sqlite3`、8001/5174 端口。夹具在 backend/tests/plan_fixtures.py，显式标注“独立展示测试；不是 B Agent 输出”。这不是原包修订，也不是正式业务场景。默认数据库和原 synthetic 数据未改。

已验证：登录读取列表；未知费用与零分别显示；刷新回读；无需手动刷新，读取到测试端口保存的安全阶段故障；新 run 不展示旧评估，历史 run 保留旧结果且没有当前放行提示。

证据：[列表](evidence/a06-plan-list.png)、[未知费用](evidence/a06-unknown-costs.png)、[保存的阶段变化](evidence/a06-saved-progress.png)、[无匹配](evidence/a06-no-match.png)、[历史运行](evidence/a06-historical-run.png)。本轮本地分支为 feature/a06-plan-display；未推送或合并到 GitHub main，本轮远端 CI 未运行。
