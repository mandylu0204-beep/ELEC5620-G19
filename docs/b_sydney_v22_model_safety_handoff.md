# B → A：悉尼 2.2/v3 模型安全组件及完整接线

日期：2026-10-23（Australia/Sydney）。
分支：`feature/sydney-v22-model-safety`。
共同基线：main `180701c`；前置提案/离线检查已单独提交推送为 `1b407f7`。

## 交付范围与复核状态

按用户明确授权，B 在新分支实现 2.2 安全组件、工厂/runtime、Hybrid、现有正式审计的最小接线改动，而不是仅提供提案后继续等待 A 编码。涉及 A-owned 注册和审计文件，请 A 独立复核本候选；不声称协议已由 A 冻结或已获合并批准。

默认安全保持 rules，不改个人模型配置、现有数据库、封存数据、模型超时/重试/token 或规则结论。共享 DTO/schema、审计 envelope、保存接口继续 1.0；不新增迁移、表或独立 trace 数据库。

本轮真实校园调用 0、Actions/云端运行 0。所有模型响应来自 MockTransport；前端界面与浏览器真实模型验收未执行，不把旧 A64/A88/A90 的结果挪作本轮证据。

## 精确协议矩阵

| 数据版本 | 新模型安全写入 | 历史读取 |
| --- | --- | --- |
| 2.1.0 | 现有 agent-2 / tools-2 / validation-2，当前 kernel/rules | 原 v1/v2 及其已支持内核，原身份回放 |
| 2.2.0 | 独立 agent-3 / tools-3 / validation-3，当前精确 kernel/rules | 按保存的 v3 身份回放 |
| 其他/未知 | 拒绝 | 未安装/不匹配验证版本拒绝，不生成替代 trace |

三元组完整字符串分别为 `campus-safety-advisory-agent-N`、`safety-read-only-tools-N`、`safety-advisory-validation-N`。v3 当前 kernel 为 `b02-v1-rules-2/a-meal-clarification-v1/a-profile-essentials-v1`；dataset rules 为 `b02-v2-rules-2/a-meal-clarification-v1/a-profile-essentials-v1/trip-evidence-selection-1`。

模型 seed 收齐后绑定同一最终 workflow context。完整身份包含 manifest、catalogue、runtime evidence、选择和每日快照标记；不能把 2.1 的旧 seed/trace 直接改标签用于 2.2。

## 组件与源码组织

- `backend/app/llm/safety_v3.py`：独立 v3 身份、提示摘要、trace 类型、2.2 工具、纯校验器和组件。v3 seed/schema 只接受当前精确配对及实际 v3 提示摘要。
- `safety_agent.py`、`safety_tools.py`：最小策略钩子复用原工具循环和 finding/文本/载荷限制。默认仍为原 2.1/v2；原 v1 代码未改，v2 提示、schema、finding key、返回字节语义不重标为 v3。
- `safety_support.py`：闭集 live 协议矩阵。不使用 >=、前缀匹配或宽泛 Adapter 版本列表启用安全角色。
- `safety_validation.py`：增加延迟加载 v3 dispatch，原 v1/v2 入口继续保留。
- 独立 `docs/contracts/safety_advisory_v3.schema.json`；导出/核对：`python -m app.export_safety_v3 [--check]`。不覆盖 v1/v2 文件。

模型依然实际执行 read_safety_facts → evaluate_safety_plan → exact final。确定性 SafetyResult 必须完整等于宿主基线，模型只能在允许的 action 中选择并排序，建议不能修改风险、费用、数量、资料有效性或人工审核要求。v3 trace 由实际完成的调用生成，不另行伪造审计。

## 来源表述与上限

v3 明确区分有封存来源目录的地点信息、模拟天气/道路/火险动态资料，以及参考费用假设。工具添加最小 `source_provenance`，包括 catalogue 摘要、来源类别和 `official_clearance=false`；不把整个目录或网页内容发送给模型，不增加网络查询工具，不把假天气称为官方实时预报。

冻结的共享 SourceRef 来源族仍保留 SYNTHETIC。这个内部来源族不是对每一条地点事实真假的判断，更不代表实时安全许可。实际来源由宿主 inspect/Adapter 校验；纯 compose 对调用者 context 做摘要不等于证明权限或磁盘来源。

保留 64 findings、512 catalog entries、原 action/text/proposal/facts/完整 payload 上限；超限整体失败，不截断、漏项或自动清洗。模型文本仍禁止链接、数字、控制字符及已识别的越权/伪放行表达。官方链接不由模型编造。

每日快照要求完整 policy/date/base/clock 标记；工具输入日期必须等于该次固定快照日期。日切恢复沿用原 run 的固定上下文，不能把新资料替换进旧审计；新的重评读取新上下文。当前资格/最终化仍走 A 原有日期、身份、权限和审核守卫。

## 接线与持久化

- `agent_runtime.py` 按 2.1/v2 或 2.2/v3 创建实际安全组件；缺失 Hybrid/Orchestrator 能力在创建模型客户端前拒绝。runtime 再校验闭集 seed 与 audit 标记。
- Hybrid 验证实际对象、最终 context、完整 seed/fingerprint、接口和轮数，不只检查角色标签。
- Orchestrator 使用已存在的正式安全分支，无需复制流程；仍通过 `save_model_safety_assessment` 保存 assessment、plan、trace、回执的同一事务。
- `safety_audit.py` 增加 v3 及“dataset + agent/tool/validation + current kernel”的新写入配对，保留 2.1/v2 新写入。旧 v1/v2 记录继续读其原版本，不能升级、降级或补模型 trace。
- 安全保存前失败：已有规划/物流不重做，只对缺失安全步骤重新执行。提交后丢回执：checkpoint 复用原安全 audit/trace/attempt，不再调用模型。原 lease、heartbeat、恢复、失败关闭和 finalisation 权限不放宽。

## 显式启动入口（本轮未执行）

普通运行仍为 `python scripts/sydney.py`，安全 rules。仅在用户批准真实模型调用后，可显式选择：

```sh
python scripts/sydney.py --mode agent --logistics model --safety model
```

该命令会使用已有本地模型配置，并可能消耗额度；不是离线验收或健康检查命令。仅 `--mode agent` 仍只有规划模型；`--safety model` 缺少 agent 模式时拒绝。继承环境的安全 model 值不能偷偷覆盖默认 rules。启动器不修改环境文件，不接管/停止现有端口进程。

## 离线验证与开发记录

新增 `test_sydney_model_safety.py` 使用实际组件、HTTP 认证/确认/Dispatcher、独立 SQLite 和 MockTransport；再用本地 pytest 控制插件全局阻止真实 httpx 传输运行完整后端回归。精确统计见 `evidence/b-sydney-v22-model-safety-offline.json`。

实际结果（macOS 本地，不是 Windows/云端）：

- 首轮全量收集 1585 项：1558 passed / 0 failed / 27 errors / 0 skipped，退出码 1，694.29 秒。27 项均为同一旧存储夹具把 2.0 登记为 v2 的 setup 错误；不能将该轮记为全量通过。
- 只将 `test_safety_audit_storage.py` 夹具改为实际 2.1 输入与自动证据选择，保持原断言；完整模块 28 passed / 0 failed / 0 errors / 0 skipped，退出码 0，12.63 秒。按 classname/name 精确匹配，原 27 个错误均已由该轮覆盖通过。全量后生产代码未再变化。
- 新组件/HTTP 模块 28 项均在上述全量中通过。另加的道路关闭/跨日恢复 2 项在全量收集后加入，独立运行 2 passed，8.07 秒。
- 上述去重并集为 1587 个用例，不将 1558+28+2 直接相加；没有再声称修正夹具后执行过一次零错误全量。保留原始失败和修正证据，A 可据此决定是否补一次完整验收。
- 所有三轮正式回归控制器的真实 HTTP 传输触发数为 0；共享/v3 schema 检查、pip check 和 Git 空白检查通过。一条既有 Starlette TestClient/httpx 弃用警告保留。
- 未改前端，不重复跑 A90 前端/浏览器验收。源码差异检查确认原数据包、v1 组件、v1/v2 schema 和共享 schema 未变。

可复用的 pytest 网络控制源在 `scripts/v22_offline_transport_guard.py`，与本轮本地控制器逐字节相同，仅测试时加载，不属于运行时接线。复现定向检查（需已有开发依赖；临时目录须选新名称，避免覆盖旧证据）：

```sh
cd backend
PYTHONPATH=../scripts ../.venv/bin/python -m pytest -p v22_offline_transport_guard tests/test_sydney_model_safety.py tests/test_sydney_safety_snapshot_guards.py tests/test_safety_audit_storage.py --basetemp ../var/v22-review-unique -p no:cacheprovider
```

覆盖封存/每日快照、物流 rules/model、安全 v3；实际三轮协议、来源投影、篡改拒绝、v2/v3 错配、并发结果和事实视图隔离；PLAN/换营地 REVISE/同版本 REASSESS、最终快照、重启回读和其他用户拒绝；安全保存前失败/提交后丢回执；远期天气不足保持原规则结论，非法输出不转规则成功；显式启动和默认值。

前置测试中原“2.2 一律拒绝”现改为“未接齐审计能力必须在客户端创建前拒绝”，不是删除校验；旧 v2 组件继续拒绝 2.2。原 `1b407f7` 的 15 项结果与初始测试源码属于历史记录，不表述为适配后新源码的结果。

开发阶段两次 HTTP 夹具失败已保留：首次确认命令键不足接口规定的长度；随后儿童数量未明确确认，规则正确要求补充。只修正测试输入，不在生产中推断儿童数量或放宽长度限制。修正后首轮新增模块 23 项通过；之后又补充并发/新写入降级和启动器检查，最终统计以完整回归为准，不累计重叠轮次。

## 给 A 的下一步

请先复核 2.2/v3 的精确注册矩阵、A-owned new_write/读取 dispatch、完整来源身份、默认 rules 及旧回放边界。代码候选经过离线验证不等于真实模型成功，不直接合 main。

独立复核无阻塞后再安排一次用户批准、有请求上限的 2.2 校园验收，并检查模型建议、正式审计保存、重启回读和用户界面；无需重复旧 A88/A90 的纯显示验收。不因一次 502 放宽 deadline、输出上限、校验或默认退回规则。
