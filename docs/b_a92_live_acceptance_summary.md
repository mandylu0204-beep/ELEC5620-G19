# B → A：A92 Sydney 2.2 / Safety v3 真实验收汇总

日期：2026-10-23，Australia/Sydney（UTC+11）。分支：`feature/sydney-v22-model-safety`。

## 固定应用与控制源

三轮应用源码均固定为 `1450631ad95fed13997f5410f14078a873c0481b`；控制提交为 `b5e6b4a678c8e09ad151487b477f24ccfac4d1eb`（`tools/a92-v3-live-acceptance`）。此次归档只新增报告及脱敏 JSON，不改应用、数据、个人配置或控制源，不合 main。

每轮均由用户分别授权，使用独立数据库与快照、新 PLAN；单轮最多 8 次实际校园请求，其中安全最多 4 次。首次模型错误立即停止，不自动追加探针、重试、恢复或第二个 PLAN。三轮实际合计 19 次，不是本次归档又发起 19 次调用；归档阶段新增调用 0。

## 三轮结果

| 配置 | 实际请求（规划 / 物流 / 安全） | 结果 |
| --- | --- | --- |
| 2048 / reasoning_effort 未设置 | 4（2 / 2 / 0） | 物流第二次 HTTP 200、length，22.350 秒；未进入安全阶段 |
| 4096 / low | 8（2 / 3 / 3） | 全部 HTTP 200、stop；新 PLAN、安全审计保存、应用重建回读、用户隔离与只读浏览器展示通过 |
| 2048 / low | 7（2 / 3 / 2） | 安全第二次 HTTP 200、length，23.634 秒；CONTRACT_INVALID，停止于 ASSESSING_SAFETY |

4096/low 的安全审计、回执和 run/version/assessment 关联均已核对；只读浏览器进程禁用模型 complete、出站传输与业务写入。展示前后保存产物及 transport 报告摘要一致，浏览器新增校园请求 0；未冒充人工批准或最终保存。

2048/low 失败后保留版本、规划 trace、物流 assessment 与 audit；安全 audit/安全回执均为 0，无规则成功回退或补造 trace。该轮不是 HTTP 502，也不是 45 秒客户端超时。失败请求关联 ID：`req_480343ae38c547129f2f90cfdc465147`。

两种 low 配置使用同源与相同合成输入生成方式，但独立运行身份和重新生成内容，并非逐字节一致的单变量重放。可确认 2048/low 本轮仍截断，不能标为已验收；4096/low 是本次正常场景实际通过的配置，不保证所有输入成功。其安全第二次响应 completion 计数为 2192；失败轮次的 usage 未采集，不补造为 2048。

## 证据索引

- 首轮历史失败：[报告](b_a92_v3_live_acceptance_initial.md)、[JSON](../evidence/b-a92-v3-initial-live.json)。
- 4096/low：[报告](b_a92_v3_live_acceptance_4096_low.md)、[JSON](../evidence/b-a92-v3-4096-low-live.json)。
- 2048/low：[报告](b_a92_v3_live_acceptance_2048_low.md)、[JSON](../evidence/b-a92-v3-2048-low-live.json)。

原报告/JSON 按当次结束时状态归档，保留其中“未 commit/push”和分阶段 browser=PENDING 等历史字段；独立只读浏览器的最终结论在 4096/low 报告及 JSON 的 browser_acceptance 中。此次提交推送来自用户后续独立授权，不倒改历史证据。

共享材料仅含有限元数据、摘要、计数、时间及允许名单响应头 ID；不含密钥、Authorization/Cookie、完整提示、原始回复或私有推理，不提交私有数据库、快照或本地凭据。

## 请 A 复核及下一步

请独立复核冻结应用 1450631 与正式 v3 审计/读取接口、来源身份及上述 4096/low 验收证据。默认安全仍为 rules，个人配置未改；不应仅为支持 2048 而放宽输出校验。

本轮真实验收范围是正常新 PLAN、正式审计保存、回读、用户隔离和只读展示；未覆盖真实 REVISE、REASSESS、旧失败 run 恢复或最终保存。此前离线覆盖不能代替这些真实场景。请先确认合并与用户测试所需剩余范围，避免 A/B 重复正常 PLAN；新增真实模型调用仍需用户另行授权。不使用 A 的 Actions，不把未执行 CI 标为通过。
