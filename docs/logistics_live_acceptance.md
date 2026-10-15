# A25：真实校园双模型联合验收

日期：2026-10-15（Australia/Sydney）。集成 B `bc5c74f`、main `9b54143` 和 A24 存储能力；本轮输出额度修正为 `4c07ddf`。个人 `.env`、`.env.llm.local`、原用户数据库及封存数据未修改，应用物流默认仍为 rules。

所有模型请求使用实际校园代理与本地凭据，未模拟回复、指定预期模型选择或替换业务结果。模型返回身份为 `Qwen/Qwen3.8-27B-FP8`。正常、预算、缺资料和封路各自使用独立 SQLite 文件；启动验收进程显式配置 agent/v2、模型物流和 4096 token 上限。

## 本轮发现及修正

原本个人配置为 2048 token。首次正常运行成功保存行程，但物流第二轮被截断，流程以 CONTRACT_INVALID 停止，未保存物流/安全评估且不允许自动重试。保留该运行和截图，没有清库或伪造恢复成功。

独立真实诊断复现：服务返回 `finish_reason=length`、content=null，completion_tokens=reasoning_tokens=2048。提高隔离诊断上限至4096后，物流三轮通过严格业务校验；其中第二轮使用2509 completion tokens（含1748 reasoning tokens）。诊断不写业务评估，不计作完整应用验收。

公开 CampusModelSettings 默认值和 config/campus_llm.example 改为4096，保持原128～8192范围、显式用户配置优先级、重试/轮数/权限边界。已有个人文件若明确写2048，仍会覆盖新默认；正式启用模型物流前需自行更新该非密钥配置，或在启动进程临时设置：

```powershell
$env:ELEC5620_MAX_COMPLETION_TOKENS = '4096'
```

配置变动会改变登记身份，必须重新确认需求并开启新运行。本轮通过浏览器复制原需求、重新摘要及明确确认后开启新运行，没有强行继续旧身份。

## 验收进度

| 场景 | 实际结果 |
| --- | --- |
| 正常 PLAN | 浏览器登录、保存资料、草稿/摘要/确认/规划；实际选择 Wattle Rest，费用25100 cents，物流/安全通过，显式最终保存。两个模型记录分别保存。 |
| 低成本 REVISE | 原费用25100 cents、预算24500；实际修订为 Moonlit Field，新版本2、费用23100。物流收到临时502后，经浏览器恢复，仅补未完成物流，原版本/规划trace保持，无重复版本。 |
| 同版本 REASSESS | 浏览器发起；保留版本2与原行程、原规划trace，零新增规划调用；新增3次物流completion、独立评估/audit及输入fingerprint。保存第二份最终快照，原最终快照未改。 |
| 重启与用户隔离 | 正常和预算服务均实际停止/重启，详细记录与所有最终快照完全回读一致。Camper B通过HTTP及浏览器不能读取Camper A预算方案/快照。 |
| 道路关闭 | 实际选择Moonlit Field，安全BLOCKED；浏览器明确显示道路关闭，最终保存禁用；最终保存与人工批准HTTP请求均409。 |
| 安全资料缺失 | 已实际选择River Flat并保存原行程；物流连续502，经两次恢复仍未完成，未生成物流audit或安全评估，不计作安全缺资料闭环通过。 |
| 物流保存后丢回执 | 使用完整演示Profile、真实校园产物，正式物流保存提交后注入一次回执丢失；重启应用再恢复，新增模型调用为0，原audit/行程/规划trace保持。1run、1version、2assessment、1gear checklist、1planning trace、1logistics audit，具备最终保存资格。 |
| 未知帐篷数量变体 | 额外复制Profile，将帐篷quantity明确设为null；真实运行在物流阶段遇到502，尚未提交，不能计为未知费用/确认标记的真实验收通过。已有离线覆盖仍独立有效。 |

正常数据库保留首次截断失败，因此共2run/2version/2planning trace，但成功运行只有1份物流audit、2份评估及1份最终记录。预算数据库为3run、2version、2planning trace、3logistics audit、6assessment、3gear checklist、2final record；代理故障重试没有新增版本或规划记录。

缺资料与修订遇到的代理502均如实保留；服务不稳定不被标注为业务评估通过。预算重评的一轮物流请求还经历了客户端内部重试，物流trace为3轮/4次HTTP尝试。usage只统计成功响应报告的token，不是完整账单；AUD251/231是合成行程估算，不是API花费。

## 502诊断与未完成边界

缺资料输入仍使用登记的 safety-02、2026-10-21至23、两人/两晚、预算32000 cents、必须showers。实际选River Flat，没有修改选择或替换为其他场景。三次run attempt共保存同一个version和planning trace，始终没有logistics audit/assessment、安全assessment或final record。

只读重建的物流事实为16项装备、10项费用，均在协议64/128上限内。单次尝试的实际诊断第一轮HTTP200，第二轮约30264ms后HTTP502；只记录状态码、长度和错误类别，不记录错误正文或私有推理。上游错误根因尚未确认，不能把观察到的约30秒直接认定为已证明的固定超时配置。

代理公开OpenAPI未描述Chat Completions请求字段。依据[实际返回模型的官方说明](https://huggingface.co/Qwen/Qwen3.8-27B-FP8)，另做两项独立诊断：chat_template_kwargs关闭thinking被代理422拒绝；reasoning_effort=low可收到两轮HTTP200，但组件仍返回CONTRACT_INVALID。两项均未接入生产客户端、未写业务评估，不能当已验证的替代配置。实验8讲义未提供这些API参数，未据此推断支持性。

请B优先复核物流请求/响应体积、受控JSON协议和耗时，并与校园代理维护方确认上游错误；若采用参数或Prompt调整，需纳入登记身份，保持严格校验和恢复边界，再重新执行未通过场景。不能以规则回退、删除装备/费用、跳过安全或扩大成功结论代替修复。

## 自动检查与证据

- 最新main组合的PR CI：860 passed；A独立本机相关测试193 passed。
- 输出额度修正后的客户端/CLI相关测试50 passed；[完整集成CI 38655771742](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38655771742)为860 passed、1条既有Starlette警告，schema和前端构建通过。
- 浏览器正常流程、预算重评和封路检查无控制台error；用户隔离的404属于预期拒绝。

公共脱敏记录见 [JSON摘要](evidence/a25-live-logistics-check.json)。截图：[正常最终保存](evidence/a25-live-normal-final.png)、[重评后的最终方案](evidence/a25-live-reassessed-final.png)、[道路关闭](evidence/a25-live-road-closed.png)、[缺资料场景502](evidence/a25-live-missing-502.png)。本地原始验收记录仅在忽略目录 var/a25-live。

本轮因真实场景仍有阻塞，保留PR #5，未合入main。完整集成及A修正位于 feature/a25-logistics-integration；B如继续修复应先合并该分支，保留最新用户文案和4096公开默认值。未生成Canvas ZIP，亦未进行Canvas下载后的干净部署或其他模型角色验收。
