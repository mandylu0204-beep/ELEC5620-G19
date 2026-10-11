# B PR 审查修复记录

日期：2026-10-11。依据 A 的 PR 审查与接入统一回复，记录 B 侧已修改的代码问题。当前数据 Adapter 仍针对 Git v1，未切换应用数据版本。

## 修复项

| A 审查项 | B 修改 |
| --- | --- |
| Windows 缺少 IANA 时区数据库 | 在 Windows 依赖中加入 tzdata 2026.5，并纳入锁文件；保留 ZoneInfo 的 Australia/Sydney 夏令时规则 |
| 负数/小数时长和人数被正整数后缀误识别 | 解析完整 numeric token；负值、小数值返回 INVALID；days、nights、people 均覆盖，explicit_fields 仍优先 |
| v1 Adapter 接受混合来源 | Adapter 对每条业务记录强制要求完整 v1 source_name，未来共享 Provenance schema 扩展也不会让 v1 加载器静默接收其他包 |
| Windows 普通用户不能创建 symlink | 仅 Windows 明确的 permission error (WinError 5/1314) 时跳过对应路径测试；其他 OSError 仍失败，生产路径守卫不变 |
| B 把最终 eligibility 当作已提交 run 的事实 | B 在 route 后发完成意向、过滤运行时序产生的 RUN_NOT_SUCCEEDED，返回 RunResult；由 A 校验后提交最终状态并计算最终 eligibility |

新增 parser、source mixing、A11 完成提交顺序和 Windows symlink 权限边界回归测试。实际完整后端回归：406 passed，1 条既有 Starlette/httpx 弃用警告；针对性测试 202 passed；共享 schema 保持同步。

## 数据修订状态

数据包 SHA-256 `8066f252a50d8dc024d5ee4fa1cd8f1a8b6adcf59c377c2120fd8f9232d6ed0a` 与审查意见记录完全一致。已从原始 ZIP 建立独立修订副本 `data/synthetic_demo_v2/`；Git v1 的 `data/synthetic_demo` 和 v1 Adapter 均未切换或覆盖。

独立副本已统一餐食模式、用 Decimal/整数分逐项 HALF_UP 计算金额、固定完整场景时钟，并补强 test-43/test-56 的身份与全部前置评估，增加 test-57/test-58 条件解除控制。包内静态验证为 68 项通过、0 项失败；58 条验收规格仍标记 NOT_RUN，未宣称实际运行 Agent 或应用。

## A/B 接线要求

- A 提供 A11 启动/重试 dispatcher、completion result validation、最终成功提交、数据上下文提供器和 Web/UI 接口。
- A/B 把 `WorkflowConfiguration.context` 用于确认/start/claim/retry，并由 A 重新检查磁盘输入的当前摘要。
- A/B 对齐主路由状态及同时出现的 blocker/review/revision 展示语义。
- 需要完整四场景输入及运行时真实 HTTP/应用联调；独立 pytest fixture 不替代 Canvas/Windows 干净安装验收。
