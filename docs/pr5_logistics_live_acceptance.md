# PR #5：真实校园双模型验收（部分通过，暂不合并）

日期：2026-10-15（Australia/Sydney）。结论：**本轮真实验收不是全绿，PR #5 继续保留，不据此合入 main。**

源代码为 B `bc5c74f` 与 main `9b54143` 的组合，临时合并树为 `1d7134c91f252d2f8915182cacd9ae61367de247`。只在 `/private/tmp/campmate-pr5-live.0r6F2H` 导出的副本中运行，未改变工作分支、应用业务代码、默认配置、私人环境文件、原用户数据库或封存数据。未 commit/push、未合并 PR、未向 A 自动发送消息。

使用本地已配置的校园凭据和真实网络连接。目标 `campus-qwen`，成功响应报告 `Qwen/Qwen3.8-27B-FP8`；不独立证明模型权重身份。不使用 MockTransport、预存回复或固定模型营地选择。观察用 Client 子类只记录角色、回合返回、尝试/usage/耗时、回复摘要及 finish_reason；所有模型消息和成功结果仍由原 Client/Coordinator/LogisticsAgent 处理。

脱敏机器证据：[pr5-live-logistics-check-20261015.json](evidence/pr5-live-logistics-check-20261015.json)。未发布原始 Prompt/messages/replies、私有推理、密钥、会话、数据库或完整内部事实快照。

## 1. 原配置与对照配置必须分开

原本地配置：`max_completion_tokens=2048`、`timeout_seconds=45`、`max_turns=4`、`max_attempts=2`。原配置的真实正常 PLAN 失败，不能被后续对照结果覆盖。

为定位并继续检查接线，仅在验收进程中把 `max_completion_tokens` 提高到 **8192**，其余限制不变。新配置使用新的隔离数据库、新确认、新 run 及正式身份登记，不改 `.env.llm.local`，不改变失败 run 的配置或复用其写入 key。下表的正常成功、重评与回执恢复均属于该临时对照配置，不是默认配置的无条件通过证明。

## 2. 实际结果

| 项目 | 实际结果 | 是否完成 |
| --- | --- | --- |
| 原配置正常 PLAN（浏览器完整创建） | 模型选 Wattle Rest，规划版本/trace 已保存；物流回复被判为格式无效或截断，CONTRACT_INVALID、不可自动重试 | 未通过 |
| 8192-token 正常 PLAN（HTTP 创建，浏览器核对） | 模型选 Wattle Rest；费用 AUD251，预算 AUD320；物流/安全均 PASSED，保存1份独立物流 audit | 对照通过 |
| 浏览器装备/费用/安全/记录 | 显示逐项装备建议、缺口、预算分配和独立模型记录；原事实未被改成虚构拥有，原可选缺口保留 | 对照通过 |
| 明确最终保存、前后端重启、用户隔离 | 浏览器勾选后保存最终快照；重启前后快照逐字节相等，调用计数不变；Camper B 读取被拒绝 | 对照通过 |
| 同版本 REASSESS | 原行程/版本不变，新 run、新物流 assessment/audit；只新增3轮物流调用，规划新增0次 | 对照通过 |
| 重评物流提交后受控丢回执 | 已保存物流及 audit 后单次返回可恢复 PERSISTENCE_FAILURE；重启服务、正式 RETRY 后完成安全/路由，恢复新增模型调用0次 | 对照通过 |
| 超预算 PLAN 与单次 RETRY | 规划保存 Wattle Rest；物流步骤校园代理返回502，重试仍502；未重跑规划、未伪造评估或允许最终化 | 未通过 |
| 真实 REVISE：cheaper campsite | 规划模型选 Moonlit Field，新版本2及新规划trace保存成功；后续物流返回502，整条 REVISE 尚未完成 | 部分完成，未通过 |

所有金额为模拟数据的行程估算，不是现实报价、预订或模型费用。没有为了得到成功结果而强制营地、改变预算、放宽证据或替换模型回复。

## 3. 已验证的保存、身份与恢复边界

正常对照初次 PLAN：1 request、1 plan、1 run、1 version、2 assessments、1 gear checklist、1 planning trace、1 logistics audit。最终保存后新增1 final record。

重评的受控回执丢失发生在 **A 正式物流原子事务已提交后**，不是校园网络的自然故障。暂停时本次物流 assessment/audit 已完整存在；服务重启后从正式 HTTP RETRY 恢复：

- 同一个保存版本/内容/本次 VersionContext 被复用；原规划 trace 的 ID、生成 run、attempt、usage 与时间不变。
- 本次物流 audit 的完整 plan、trace、assessment/gear/attempt 关联逐项相等；恢复不产生另一份 audit。
- 安全步骤引用已保存物流 assessment，继续完成安全、route 与成功提交。
- 回执丢失前后累计模型成功调用数保持 `PLANNING=2 / LOGISTICS=6`；其中后3次物流调用属于重评本身，恢复新增为0。
- 恢复后数据库为2 runs、1 version、4 assessments、2 gear checklists、1 planning trace、2 logistics audits、1 final record，无重复版本/审计。
- 原最终快照在重评及后续失败修订后都保持不变；SQLite integrity_check=ok，foreign_key_check无错误。

同版本重评的新 run 与原 run 的确认数据、规则/模型配置和行程完全相同时，`input_fingerprint` 可以相同，并不单凭该值表示新评估。实际记录通过 run_id、assessment_id、audit_id 区分；`LogisticsInput` 的 `input_sha256` 随本次 VersionContext/run_id 改变。本次没有为了制造不同指纹而修改输入。

## 4. 浏览器证据及范围

原配置失败场景完全从浏览器登录、资料保存、需求草稿、摘要核对/明确确认与“开始规划”触发。8192-token 正常对照、REASSESS、REVISE 和恢复通过真实 HTTP 启动/调度；随后用浏览器核对真实保存产物。不能声称所有操作都从头由浏览器填写触发。

浏览器核对包括：装备数量与缺口、可选延期仍保留缺口、确定性 AUD251 费用及 AUD69 剩余预算、规则安全证据、两个独立模型角色记录、明确最终保存、前后端重启回读和第二用户拒绝读取。正常阶段及重启阶段捕获的浏览器 error 日志为空；跨用户404是预期拒绝，另行记录。

重评页面明确显示“未调用规划模型，以下为原版本生成记录”，并另显示本次物流模型记录。失败修订页面展示 Moonlit Field 版本2、未完成的检查、可恢复错误及禁用最终保存，没有套用旧评估/成功卡片。

截图：

- [原2048配置失败](evidence/pr5-live-original-limit-failure.jpg)
- [临时8192配置的最终保存](evidence/pr5-live-expanded-final.jpg)
- [重评/恢复的原规划与本次物流记录](evidence/pr5-live-reassess-recovered.jpg)
- [修订新版本及502阻断](evidence/pr5-live-revision-502.jpg)
- [跨用户读取拒绝](evidence/pr5-live-owner-isolation.jpg)

## 5. 需要 A/B 处理的两项问题

### LIVE-01：当前2048输出上限未通过真实物流验收

首轮错误为“校园模型响应格式无效或被截断”。该首轮未保存原始回复或 finish_reason，不能仅据错误文案断言具体是哪一个解析条件失败。

对照中物流 evaluate 回合成功响应报告的 completion_tokens 分别为 **2529**（正常）和 **2600**（重评），均超过原2048上限；这是输出预算不足的直接风险依据。8192对照完整通过严格方案、事实、费用与正式保存校验，但并不证明所有允许的最大清单都能在某个较低上限内成功。

建议 A/B 明确模型物流的支持配置与就绪条件：确定最低/推荐输出上限，评估是否需要缩短受控协议或在学校代理确实支持时控制模型思考开销。任何配置/Prompt/协议改变均需正式身份登记、新确认/run 和复测，不能对旧失败 run 临时改配置继续。不能放宽 JSON 校验、截断清单或规则回退来绕过问题。

### LIVE-02：连续502阻止超预算及修订的完整物流闭环

校园代理在超预算初次执行、同配置单次 RETRY、以及正常方案的真实 REVISE 中返回502；错误归类为可恢复 AGENT_FAILURE，产物及审核/最终化边界保持正确。服务端502的具体原因尚未定位，不能宣称一定是本地超时或额度耗尽。

两次成功物流评估各用了3轮/4次HTTP尝试，整体耗时66.576秒与68.674秒，其中 evaluate 回合约58秒且成功于第2次尝试。说明45秒的单次等待限制与当前真实延迟存在需要评估的匹配风险；但这不能独立解释全部502。失败/超时服务调用可能仍消耗额外token，不承诺 exactly-once。

建议先核对老师代理的稳定性、上游等待限制和正式支持的参数；A/B 冻结合适的输出/超时配置后再用新登记上下文复测超预算 PLAN、完整 REVISE 和修订版本的 REASSESS。客户端重试上限保持受控，不进行无限付费重试。

## 6. 调用统计与下一步

本轮观察到22次 Client.complete 开始、18次成功返回、4次失败返回；不等同于底层HTTP总请求数。成功响应报告 usage 合计：输入58558、生成10031、总计68589 tokens。失败/超时/取消尝试的用量不完整，以上不是账单，也不应当作总消费上限。

本轮不修改业务代码来迎合验收，也不合并 PR。离线 PR CI 的860项及 A 的193项复核来自 A 已提供的记录；本轮没有冒称重新执行这些检查。高风险/过期/禁火、缺证据/封路的全部真实双模型场景、干净部署和最终Canvas验收未在本轮执行。

下一步请 A 先看 LIVE-01/LIVE-02，与 B 确定支持配置/必要调整，再补齐未通过的真实流程。当前结论仍是部分验收，不满足“所有真实流程通过后合入 main”的条件。

清理：本次自建前后端及浏览器标签已关闭，8705～8707、5305～5307端口已释放。临时副本和隔离数据库保留供后续排查，没有删除用户数据；运行数据库不随证据提交。
