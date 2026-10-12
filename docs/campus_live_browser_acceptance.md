# A-16：真实校园模型正常场景验收

日期：2026-10-13（Australia/Sydney）。测试源提交 `3b7abf248ed2fb522a0dbe5eac005346d18d8cf8`，分支 `feature/a16-campus-wiring`。本次实际执行，使用用户已连接的 USYD VPN、本机 `.env.llm.local` 和真实校园代理；没有模拟模型 transport，也没有预存成功结果。此前离线证据仍独立保留。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| 流程 | 浏览器登录Camper A → 显式保存Profile → 保存草稿 → 解释/明确确认 → HTTP调度 → 模型行程 → 规则评估 → 最终保存 |
| 输入 | 两人，2026-11-06至11-08，两晚/三天，预算AUD320，quiet / ready-to-eat meals；时钟2026-11-05，safety-15 |
| 请求模型 / 服务返回身份 | campus-qwen / Qwen/Qwen3.8-27B-FP8 |
| 调用 | 两轮、两次HTTP尝试；search_campsites；耗时9625ms |
| 成功响应usage | 输入3825、生成681、合计4506；不是完整计费报告 |
| 模型选择 | demo-wattle-rest；未强制选择或改写模型结果 |
| 物流和安全 | 两份规则评估均PASSED；费用AUD251，预算剩余AUD69；满足最终化eligibility |
| 最终化 | 用户显式勾选后保存FINALISED，快照保留原trace |
| 重启回读 | 停止并重启实际前后端，同数据库/会话读取原最终快照，模型身份与trace保留 |
| 用户隔离 | Camper B打开Camper A最终URL得到NOT_FOUND，不显示模型或方案内容 |
| 正常页面/重启控制台 | error为空；隔离检查的404是预期拒绝 |
| 清理 | 本次服务与标签已关闭，8640/5240端口已释放 |

独立数据库 `var/campus-live/normal.sqlite3` 只读检查：1请求、1plan、1run、1版本、1推荐、1trace、2评估、1最终记录。run为SUCCEEDED/COMPLETED，版本FINALISED。审计再次通过实际模型审计校验，最终快照的trace、版本身份和行程内容与持久化记录一致；SQLite integrity_check为ok、foreign_key_check无错误。重启没有新增run/version/trace。

关联编号：plan `fe646141ba41476e9ae14712ab3803cc`，run `9f588a471c824b299e67302fb3e26adc`，最终记录 `19b4396ad5424ec7b9ee8a76a32c3a0c`。完整受控trace和校验摘要见 [JSON证据](evidence/a16-live-campus-check.json)。截图：[最终保存](evidence/a16-live-campus-final.png)、[真实模型trace](evidence/a16-live-campus-trace.png)、[用户隔离](evidence/a16-live-campus-owner-isolation.png)。

本轮无业务代码修改，无新的全量回归。源提交3b7abf2的 [GitHub CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38322930027)已通过；原A16本机638 passed/44权限跳过和schema/前端构建证据见 [离线检查](evidence/a16-campus-wiring-check.json)。本轮只增加验收记录与更新状态文档。

## 完成边界

这次证明正常场景真实模型HTTP与浏览器应用闭环，包括两份评估、最终化、重启回读和用户隔离。仍只有行程角色使用模型，其余阶段为规则；服务返回身份不等于独立验证模型权重。

没有重跑其他真实校园错误/风险场景，也未在真实校园调用中注入失败来验收恢复。保存回滚、回执丢失/重启恢复、非法trace等仍以独立离线HTTP集成测试为证据。模型修订/重评、另外两个模型角色、最新版本干净安装、Canvas下载和另一电脑验收仍待完成。

个人应用 `.env`、默认数据库与封存数据未改。密钥只由客户端用于校园代理认证，没有打印或保存到证据，`.env.llm.local`仍被Git忽略。本轮报告先保存在本地分支，尚未推送新报告或合入main，也未生成最终ZIP。

可转发给B：

> A-16在已连接校园VPN的本机完成正常场景真实HTTP/浏览器验收，服务返回Qwen/Qwen3.8-27B-FP8，两轮/两次调用，9625ms。模型选择Wattle Rest，规则评估费用AUD251、物流/安全均通过，最终快照保存并经服务重启回读，trace一致，用户隔离通过。请保留PLAN-only边界；模型修订/重评和另外两个模型角色仍待后续实现。
