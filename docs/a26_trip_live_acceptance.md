# A26：2.1 数据真实校园模型与浏览器验收

日期：2026-10-15，Australia/Sydney。代码基线 `0eec6aa`，本地分支 `feature/a26-trip-integration`，包含 B `5ed6e44`。本轮只执行验收、归档报告与截图，未修改业务代码，未推送或合入 main。

## 环境与调用边界

最初校园代理 TCP 超时；用户连接 VPN 后复测连通，再执行真实调用。使用独立 SQLite `var/a26-live/acceptance.sqlite3`、新包 `data/synthetic_demo_v2_1`、检查日期 2026-11-05、agent 模式和 model 物流。内部 safety_case_ids、场景文件和 selection 均为空，营地变化不依赖更换启动场景。

本机私有文件仍配置 2048 token。本轮只在独立验收进程显式使用 4096 与 `reasoning_effort=low`，沿用此前 B 已纳入身份登记的公开选项。个人 `.env`、`.env.llm.local`、已有用户数据库及封存数据未改，常规启动不会因本次验收自动切换数据或参数。

测试 transport 直接转发实际校园请求/响应，仅记录序号、HTTP 状态和耗时，不保存请求头、密钥或模型私有推理；设全轮最多 24 次请求，遇 HTTP/网络失败即停止后续调用。该熔断没有触发，没有替换成功响应，没有修改生产重试策略或登记身份。没有提交 RETRY，没有使用 MockTransport 或规则回退替代模型角色。

## 实际结果

| 操作 | 结果 | 新增模型 HTTP |
| --- | --- | --- |
| 正常 PLAN | 实际选择 Wattle Rest，2026-11-06～11-08，25100 cents。物流和安全通过，四类资料完整。 | 规划 2，物流 3 |
| REVISE：cheaper campsite | 实际改为 Moonlit Field，新版本 2，23100 cents。自动重新选择新营地资料，物流和安全通过。 | 规划 2，物流 3 |
| 同版本 REASSESS | 仍版本 2，行程内容与原规划 trace 精确保持，只产生本次物流/安全评估和独立物流 audit。 | 规划 0，物流 3 |
| 浏览器最终保存 | 勾选确认并点击保存，跳转不可变最终快照，显示 Moonlit Field、版本 2、AUD 231、评估通过。 | 0 |
| 未来日期 PLAN | 同一服务、相同资料与 Profile，仅将行程改为 11-20～11-22。实际选择 Wattle Rest，天气 NOT_YET_OBSERVED，安全 REVIEW，不能最终保存。 | 规划 2，物流 3 |
| 缺资料守卫 | Camper 最终保存 HTTP 409；Founder APPROVE HTTP 409 / INVALID_STATE，拒绝后审核详情未变化。 | 0 |
| 停止并重启后回读 | 当前方案、行程、评估、原规划 trace、物流 audit 和整份最终快照与重启前 HTTP 结果精确一致。Camper B 读方案及最终快照均 404。 | 0 |

浏览器登录、结果页面和最终保存均使用本机真实 HTTP；模型工作流由 HTTP 命令启动，浏览器核对当前保存状态，没有为了截图重复执行模型。浏览器控制台无 error。

重评页面实际显示“重新检查已完成”、完成时间，以及“装备与费用的结果或依据已有更新”。本轮模型物流建议确有变化，`check_feedback.comparison=CHANGED`、`changed_sections=[LOGISTICS]`；行程和总费用仍不变。不能把本轮描述为全部结果未变化，也不能把变化提示误解为重新生成了行程。

每次运行的装备、安全 assumptions 均包含同一个实际选择摘要，与该运行的 `trip_evidence_coverage.selection_digest` 相符。

## 资料不足时的用户体验

11-20～11-22 的天气资料在检查日 11-05 尚未发布，页面明确说明此原因；营火、道路、营地规定仍各自显示资料适用。页面提供经过选择器重新查询的同晚数日期：11-10～11-12、11-09～11-11、11-08～11-10。建议不代表完整方案已经通过，仍需用户调整并重新确认、评估。

实际点击该区域的“调整需求并重新确认”后，表单仍是原 11-20、两晚和 AUD 320，没有自动改为建议日期、保存或确认。开始日期输入没有 min/max 白名单。有限资料覆盖没有被转化为前端只能选择几个演示场景。

## 调用、存储与证据

累计 **18 次真实模型 HTTP 请求，全部 200，0 次 HTTP 重试**。实际返回模型为 `Qwen/Qwen3.8-27B-FP8`。3 份独立规划 trace、4 份独立物流 audit 均通过严格校验；重评引用原规划 trace，未复制或重新调用规划模型。

按 7 份独立 trace 去重，服务返回输入 79799、生成 9868、总计 89667 token。原规划 usage 没有重复算入重评。该用量是成功响应的 token 记录，不是货币账单；AUD 251/231 是合成行程费用估算。

独立数据库最终有 4 run、3 version、8 assessment、4 gear checklist、3 planning trace、4 logistics audit、1 final record，所有任务结束。测试后端、前端均已停止，仅保留本轮独立数据库及本地原始验收文件，不影响用户服务。

- [脱敏汇总](evidence/a26-live-campus-check.json)
- [正常规划](evidence/a26-live-normal.png)
- [换营地后的安全资料](evidence/a26-live-revised-coverage.png)
- [重评完成反馈](evidence/a26-live-reassessed.png)
- [浏览器最终保存](evidence/a26-live-final.png)
- [尚未发布的资料说明](evidence/a26-live-future-coverage.png)
- [经查询的调整建议](evidence/a26-live-future-options.png)

## 未扩大本轮结论

本轮未重新跑全量后端回归，因为未修改业务代码；此前组合的 148/24 项与静态、schema、构建结果见 [离线组合审查](a26_trip_integration_review.md)。没有把这些测试计为本轮新增真实调用。

新 2.1 的道路关闭已有离线覆盖，本轮未额外重复付费运行其真实模型场景；先前 2.0 的真实封路/重启/恢复证据独立保留，不冒充本轮新 2.1 验收。也没有据本次全 200 推断校园上游以前 502 的根因或保证未来不会失败。

Canvas 下载、干净安装、最终提交 ZIP 留到系统完成后按照用户安排验证，本轮不执行。
