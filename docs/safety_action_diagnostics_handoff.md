# 安全动作错误：脱敏诊断与一次受控纠正

## 已确认的现象和证据边界

用户截图对应 run `8eff288308084d569bb787dcc60ea13a`，停在 `ASSESSING_SAFETY`。只读检查确认：行程和物流结果已保存，物流为 PASSED、运输可行，无物流缺项／blocker；安全审计尚未保存。本次使用 2.2 compact／v4，错误出自安全提案受控校验，不是模型 HTTP 超时。

compact 展开先核对完整事项集合及事实摘要，再检查每条事项允许的处理动作。原异常把提案结构、事项覆盖、动作不适用和内部来源绑定等不同失败统一为一条英文错误。因此重点指向不适用动作，但**旧失败未保留原提案或违规条目，不能事后断言具体 f 编号、实际动作，或彻底排除当次内部绑定问题**。本轮没有重跑该真实请求，也没有修改它的状态或记录。

离线复现已验证的薄弱点：输出 schema 的 ActionCode 是全局合法动作集合，但每条事项只允许它对应的子集。模型能产生 JSON／枚举合法、单条语义不合法的方案。旧工具立即终止，没有把具体约束反馈给模型。修复此类故障不应由代码自动换动作、漏掉事项或跳过校验。

## 修复内容

### 分开错误及脱敏诊断

`safety_tools.py` 与 compact 展开分别报告：

- `PROPOSAL_SCHEMA`：提案结构未通过。
- `FINDING_COVERAGE`：未完整覆盖正式事项，记录数量、至多 16 个缺少的服务端事项 ID；不回显未知模型 ID。
- `FACT_IDENTITY`：compact 事实摘要不匹配。
- `ACTION_NOT_ALLOWED`：记录正式 finding ID、compact 短 ID（若有）、实际动作及允许动作。
- `FACT_BINDING`／`PLAN_VALIDATION`：内部来源绑定或最终建议完整性问题，不误称为模型选错动作。

诊断版本为 `safety-structural-diagnostics-1`，以有界 JSON 字符串写入 `ContractError.context.safety_validation_diagnostics`。调用方补入角色、协议、轮数、HTTP 尝试数、响应字节和耗时；服务端 warning 日志保留这些结构字段。正式 UUID run ID 用于日志关联。

不记录建议原文、Prompt、事实正文、个人资料、密钥、请求头或上游响应正文；未知动作／ID 脱敏。普通用户的方案、运行、进度、需求及最终快照继续沿既有权限裁剪。内部保存保持完整错误；有原权限的 Founder 可读取脱敏诊断，不新增跨用户访问能力。

### 只给一种错误一次纠正机会

新政策 `selection_config.b_safety_action_feedback=safety-allowed-action-feedback-1`：

1. 仅完整、结构合法、事实身份一致的提案出现 `ACTION_NOT_ALLOWED` 时适用。
2. 当前轮数必须仍够“重新提案＋最终提交”；单次安全工具循环至多反馈一次。恢复尚未提交的安全步骤是新一次调用，仍受原单次轮数上限约束；已提交审计则直接复用。
3. 返回只读、明确标记拒绝的工具结果，以及每个服务端事项允许的动作集合。模型必须重新提交完整提案，系统不替模型选择、替换或补齐动作。
4. 纠正提案经过同一套全量校验；最终输出仍须与最后一次成功评估完全一致。收到拒绝反馈后直接 final、再次选错、遗漏事项、资料漂移均不能放行。
5. 正常流程仍为三轮；第二轮发生该错误时可在原四轮上限内以第四轮完成。没有增加配置的 max_turns、HTTP 重试、token 或超时。可用轮数不足时保持终止，不申请额外调用。

不对语法错误、未知枚举、缺失事项、事实摘要错误、来源或安全规则问题自动重试。真实使用时，发生合资格的动作错误可能比正常流程多一次安全响应；不会重新生成已保存的营地、行程或物流产物。

## 身份、恢复和 A 接线

- Sydney 2.2 托管、model safety 的新运行登记上述反馈政策，标准 v3 与 compact v4 都支持。
- WorkflowConfiguration 将政策版本追加到完整 workflow rules_version，配置和输入指纹因此区分新旧行为；冻结 system Prompt、输出 schema、原 v3／v4 seed 字段和核心规则不改动。
- 新增的是有独立版本身份的拒绝工具结果。以后修改反馈语义应升级该政策，不能静默更改旧运行。
- `AgentRuntime.resolve(..., safety_feedback_policy=...)` 为内部入口；`for_scope` 从保存标记重建，旧记录无标记就保留原来立即终止的行为。未知标记／登记冲突拒绝。
- 审计仍只保存校验通过的最终建议、正式评估和 trace。成功纠正时 trace 包含四轮响应摘要与三次工具调用。纠正前的拒绝通过脱敏服务端日志定位，不能伪装成有效评估。
- 纯回放不调用模型，旧成功记录继续按原内容和身份校验。当前最终保存仍核对当前身份；旧评估不自动变成新政策下通过。
- checkpoint、heartbeat、回执和事务沿原路径；已保存的纠正后安全审计在丢回执恢复时直接复用，不重跑模型补 trace。

不新增数据库表、迁移、HTTP 写接口或共享 DTO schema。A 集成须同时带入诊断、反馈政策、Agent 循环、运行注册和恢复参数，不能只拿其中一个循环改动。原用户数据库、环境文件、密钥和封存数据未更改，服务未擅自重启。

## 修改文件

- 新模块：`llm/safety_diagnostics.py`、`llm/safety_feedback.py`。
- 工具：`llm/safety_tools.py`、`llm/safety_compact.py`。
- 循环：`llm/safety_agent.py`、`llm/safety_v4.py`。
- 登记：`application/agent_runtime.py`、`workflow/configuration.py`。
- 回归：`tests/test_safety_diagnostics.py`。

## 验证与未完成范围

本轮全部模型测试使用 MockTransport，真实 HTTP 被 offline_http_guard 禁止；数据库均位于隔离测试目录。覆盖两个协议的错误动作定位、正常纠正、再次错误、缺失事项、直接 final、反馈次数／轮数限制、旧身份恢复、原始 HTTP 裁剪、审计保存及纠正后丢回执重启恢复。历史协议、文本政策、最终保存资格及角色组合继续跑相关回归。

最终组合后端 **1894 项全部通过，0 失败、0 跳过、0 真实 HTTP 尝试**。按同一收集清单分为 474／474／473／473 项，互不重复且无遗漏，四组退出状态及 XML 已核对。测试前后后端代码、测试、新距离表的源码指纹不变：`c72f677adc246eccd1814f2a84006efb7fc5f5f831d30abf65ae82f05872da65`。证明文件为 `var/pytest-safety-feedback-full-qrv1_gea/verified-summary.json`；不与前轮 1872 或局部回归数字相加。

前端最终 150 项、TypeScript、Vite 生产构建、共享 schema 检查及 git diff --check 均通过。三个封存包 31／11／11 个文件摘要全部保持一致。只有既有 Starlette TestClient 弃用及 Vite 大 chunk 提示。

没有执行真实校园模型或浏览器验收；尚不能证明用户原提案中具体哪条选错。后端重启后新检查才能采用新政策。不会自动重开原 CONTRACT_INVALID 运行，也不会改写原审计；旧失败如需重新检查，使用明确的新检查操作并保留原记录。
