# B → A：安全第二轮离线优化候选（尚未接线）

日期：2026-10-26，Australia/Sydney。基线 main `0c56764`；分支 `feature/safety-offline-optimization`。

归档说明：本文记录离线阶段，保留当时的授权与调用计数。后续另经用户授权完成的单轮真实独立测试见 [v4 真实测试报告](b_safety_compact_live_20261026.md) 和 [脱敏 JSON](../evidence/b-safety-compact-live-20261026.json)：3 次请求全部 200/stop，但尚未正式接线，不代表 502 已稳定修复。报告中的“未提交”均指测试结束时状态，本次归档不倒改历史计数。

## 结论与边界

已实现独立 agent-4 / tools-4 / validation-4 离线候选，未改当前 v3 生产协议，也未加入工厂、正式审计写入/读取 dispatch 或界面版本白名单。默认安全仍为 rules，共享 DTO/审计 envelope 仍为 1.0，无迁移、保存签名、数据库、数据包或个人配置变更。

本轮真实校园调用 0，Actions/云端测试 0。字节下降是离线可复核结果，不是 token/耗时实测，不构成“502 已修复”或真实模型验收。

## 实际字节对照

两版均以相同输入、相同动作/优先级和相同简短建议文本，通过 MockTransport 执行三轮。候选用一段建议，原形状的两个 unverified 字段复制同一段文字；不伪造第二段模型解释。两版展开后的完整 plan 和确定性 SafetyResult 精确相等。

| B 保留的正常输入 | v3 | v4 候选 | 减少 |
| --- | ---: | ---: | ---: |
| 第二轮实际序列化 HTTP 正文 | 17,631 bytes | 12,839 bytes | 27.18% |
| 事实工具投影 | 9,913 bytes | 6,419 bytes | 35.25% |
| 模拟 evaluate 动作正文 | 2,258 bytes | 873 bytes | 61.34% |

6 个 finding、23 项事实全部保留。原 v3 第二轮正文摘要仍为 `39b3c30db97143575aba03aa002eed4fe22ce22017021e3842110040ae5de91c`，与此前成功/失败独立观测一致。原数据库只读，旧 scope、日期、来源与正式审计未重写；为了离线候选比较，另由相同 snapshot 派生无旧 a_safety_* 标记的独立候选 context，不能把它用于旧运行恢复或正式保存。

可公开复现的仓库夹具也得到第二轮 17,321 → 12,481 bytes（27.94%），事实 9,621 → 6,079 bytes（36.82%）。该夹具营地不同于 B 保留的 Euroka，不能混称同一场景。模拟候选的 usage 固定来自测试 envelope，未当作真实 token 或费用报告。

## 事实与输出协议

- `safety_compact.py`：SourceRef 和 Provenance 去重到显式表，原有效日期不合并；$source/$provenance 为表引用，原文中的保留标签通过 $object 转义，防止碰撞。原路径、值、来源、未知项、天气重查提示和 official_clearance=false 全部保留。
- 模型可见短 finding id 和短 fact 引用；完整 finding key、原 fact/source refs 仍由宿主绑定。构造工具时必须把压缩投影无损还原，并与完整 v3 投影逐字段规范化比较，否则拒绝。
- 每个 canonical finding 仍必须且只能出现一次，最多 64，不通过少报风险缩短输出。priority 同样完整唯一；proposal 必须回传本次 facts_sha256，不能跨事实集复用短 id。
- 每项只生成一个 advice：最多 96 字符、12 个空白分词；summary 最多 160 字符、24 个分词；另有 UTF-8 字节上限。沿用全部原文本排除规则，不归一化、不截断、不清洗补救。
- 模型仍选择允许动作与优先级，而非仅生成说明。动作必须属于该 finding 的宿主 allowed actions。
- 仍为 read_safety_facts → evaluate_safety_plan → exact final；最后输出必须精确复制最后一次已评估的紧凑 proposal，不采用哈希回执代替实际模型生成记录。
- trace 的响应摘要来自实际 Mock 回应；proposal_sha256 明确定义为宿主展开后的完整 proposal 摘要。单段 advice 同时填入 interpretation_unverified/action_unverified，属于可验证兼容映射，不声称是两段独立生成或事实认证。
- 确定性结果完整相等，数量、费用、预算、风险、资料状态、硬 blocker、人工审核要求均不可由模型改变。

## 身份与兼容

新增 `safety_v4.py`、独立 schema 和导出器，提示/动作 schema 摘要、codec_version、角色/工具/验证版本均进入新身份。保留当前精确 kernel/rules 配对；不能把未知规则版本写成受支持常量。带旧版或不完整 a_safety_* 标记的 context 拒绝挂载候选。

原 safety_v1、v2、v3 组件、提示、schema、纯校验与 live matrix 未改；目前 2.2 新正式写入仍只匹配 v3，production safety_validator_for 不接受 validation-4。未改 Hybrid、Orchestrator、工厂或数据库读取逻辑。

未来接线须 A/B 明确新写入矩阵、旧回放、正式保存、读取及前端身份白名单。不应只把一个开关改成 v4，更不能给 2048 失败 run 或原 v3 run 改身份继续。

## 验证

最终本地安全定向回归：388 passed / 0 failed / 0 errors / 0 skipped，退出码 0，65.591 秒。全局真实 HTTP transport 触发数 0。涵盖新候选及旧组件、文本策略、kernel 身份、2.2 HTTP/快照恢复等离线回归，不是完整项目全量或 Windows/云端结果。

新增检查包括：无损编解码与保留标签碰撞、64 项边界、文本/字节约束、缺项和不允许动作、exact final、facts digest、串改和旧协议重标拒绝、并发/取消隔离、未知活动/装备、未来资料不足、冲突及临时资料道路关闭的完整工具循环。

开发记录保留：首次 52 项为 50 通过/2 失败，新夹具追加了重叠活动、冲突 baseline 又缺少必要审核/状态标记；一次补丁因目录错误未应用，复跑仍有同样失败。仅修正夹具后同 52 项通过，随后 386 项和最终 388 项通过。未放宽生产守卫或删掉失败断言。JUnit 原文件留在本机 var，脱敏统计和摘要见配套 evidence。

v4 独立 schema、原 v3 schema、共享 schema 检查通过。既有 Starlette/httpx 弃用警告保留；依赖不变。既有 tracked 文件没有差异。

## 离线复现

需已有开发依赖。以下临时目录必须未被使用；请换一个新后缀，避免 pytest 清理旧证据。命令禁止真实 HTTP；不需要校园密钥或 VPN。

```sh
cd backend
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=../scripts ../.venv/bin/python -m pytest \
  -p v22_offline_transport_guard tests/test_safety_compact.py \
  tests/test_llm_safety_agent.py tests/test_safety_text_policy.py \
  tests/test_sydney_model_safety.py tests/test_sydney_safety_snapshot_guards.py \
  tests/test_safety_audit_component.py tests/test_safety_kernel_identity.py \
  tests/test_safety_advisory_boundaries.py -p no:cacheprovider \
  --basetemp ../var/pytest-compact-review-unique
cd ..
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/safety_compact_benchmark.py
PYTHONPATH=backend .venv/bin/python -m app.export_safety_v4 --check
```

基准脚本只使用固定测试密钥、MockTransport 和本地夹具，阻止真实 HTTP/socket；输出有限字节/摘要，不输出动态完整提示或模型回复。

## 请 A 复核

先复核新 wire/codec、短引用与事实绑定、单建议映射、完整 finding 与严格长度约束，以及 A-owned 生产注册/审计读取/UI 接口应如何接入。当前只是离线候选，不提前声称 A 已冻结协议。

用户本轮仅授权离线优化；不增加真实调用、不重复 PLAN、不自动恢复原 run、不合 main、不 commit/push。经复核后，如确需验证实际耗时和输出能力，再单独申请有上限、首次错误停止的真实 SafetyAgent 测试。
