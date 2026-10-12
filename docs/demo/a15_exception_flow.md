# A-15 异常流程与审核后操作

执行记录：2026-10-12；整理日期：2026-10-13。本轮保留封存 v2 数据和默认 stub/v1，新增的输入只在 docs/demo/v2_inputs.json 中。

## 可复现的两个额外 v2 场景

使用现有 Python 环境，在项目根目录选择一个命令。固定时钟、数据与独立数据库由脚本设置；先停止上一场景并退出账户再切换。

```powershell
.\.venv\Scripts\python.exe scripts/demo.py --case conflict_revision
.\.venv\Scripts\python.exe scripts/demo.py --case no_match
```

沿用 [v2 浏览器指南](v2_browser_demo.md) 的登录、载入并保存资料、摘要及明确确认步骤。

| 输入 | conflict_revision | no_match |
| --- | --- | --- |
| demo_today | 2026-10-26 | 2026-11-05 |
| 开始日期 / 时长 | 2026-10-27 / 2晚 | 2026-11-06 / 2晚 |
| 目的地 | CampMate Demo Region | CampMate Demo Region |
| 预算 AUD | 400 | 1 |
| 偏好 | ready-to-eat meals | ready-to-eat meals |
| 必须条件 | showers | 空 |
| 证据 | safety-14及safety-08 | safety-15，搜索无匹配时不执行安全评估 |

原始想法分别为：

```text
Two people in CampMate Demo Region from 2026-10-27 for two nights, AUD 400. We want ready-to-eat meals. Must have showers.
Two people in CampMate Demo Region from 2026-11-06 for two nights, AUD 1. We want ready-to-eat meals.
```

冲突场景初次真实推荐为 River Flat，可进入最终化检查。选择“更换营地”修改后，真实规则选择 Lake Meadow，形成版本2；其天气和营火证据均 CONFLICTING，页面显示“先解决证据冲突”，批准和最终保存禁用。Founder明确选择“要求修订”并填写理由后，Camper页面显示本次理由，仍不能最终化。

无匹配场景将全部10个营地排除，工作流作为成功搜索结束，但没有行程或评估。页面显示“没有满足需求的营地”和调整需求入口，不提供技术重试，不生成最终方案。

## 从审核/输入错误返回需求确认

当前方案有“接下来怎么做”提示，按服务器保存的状态区分修订、审核、证据问题、业务输入不支持和技术中断。提示不代替服务器权限、eligibility和功能开关。

- “调整需求并重新确认”只读取本人原请求，复制至新表单；尚未保存或确认。结束日期/天数的派生值不作为旧约束带入，修改开始日期或晚数后重新生成摘要。
- 修改预算等字段时，同时核对原始想法，防止文字与显式字段冲突。新摘要使用当前保存的Profile，需重新勾选确认。
- 原请求、已确认Profile、审核与最终快照不会被覆盖。浏览器实际验证旧资料INTERMEDIATE/预算400，新资料EXPERIENCED/预算450分别保留。
- 另一名Camper复制该请求返回“请求不存在”，表单为空且保存禁用。可以明确选择“开始空白请求”，另行填写自己的需求。
- 不支持的修改意见得到INPUT_INVALID，显示具体原因和调整入口，不给重复技术重试按钮；技术故障仍按原恢复协议处理。

## 审核状态自动更新与验证范围

Founder默认不预选批准，必须明确选择决定并填写理由。Camper当前版本仅等待审核且无其他阻止原因时，页面定期读取保存状态。批准后提示可以最终保存，仍需Camper阅读并明确确认。新评估的审核记录按新run绑定，旧批准不能沿用。

本轮用独立v1测试夹具的真实RuleAgent结果验证上述批准路径：首先由HTTP集成测试生成待审核记录，浏览器从该真实保存记录开始，以127.0.0.1的Camper和localhost的Founder分离会话。Founder批准后，Camper不手动刷新即看到新状态，并明确保存最终快照；再次重新评估后重新等待审核且保存禁用。没有插入伪造评估或批准记录，但该夹具**不是封存v2高风险演示输入**。

正式v2高风险、过期天气和禁止营火的完整运行输入仍需B补充，见 [给B的补充需求](../a15_b_scenario_followup.md)。

## 验证证据

新增5项真实规则/HTTP测试通过。全量512 passed / 44 Windows文件符号链接权限跳过、schema1.0同步、TypeScript/Vite52模块构建通过。现有junction用例正常执行；跳过不计作通过。

[检查及只读记录复核](../evidence/a15-integration-check.json)、[冲突修订终态](../evidence/a15-conflict-guidance.png)、[无匹配引导](../evidence/a15-no-match.png)、[输入错误](../evidence/a15-input-failure.png)、[复制请求](../evidence/a15-copy-request.png)、[复制权限隔离](../evidence/a15-copy-isolation.png)、[v1夹具批准](../evidence/a15-fixture-approved.png)、[v1夹具重新等待审核](../evidence/a15-fixture-fresh-review.png)。

本轮仅现有开发安装环境验证，服务/浏览器标签已关闭；未进行真实模型调用、最新版ZIP干净安装或Canvas实际下载验收。
