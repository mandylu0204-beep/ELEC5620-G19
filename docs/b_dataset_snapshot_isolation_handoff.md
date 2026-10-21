# B → A：Dataset 来源视图隔离修复

分支：`fix/dataset-snapshot-isolation`。共同应用基线：`418ae1e93c153e9a925db34edd9d0cfe5ba5f945`。

本补丁不包含 CLI 修复或 A73 控制代码，不实现 runtime 缓存，不修改个人配置、封存数据、schema、数据库、角色开关、模型参数、超时、租约、审计接口或恢复流程。默认安全角色仍为 rules。

## 修复内容

`SyntheticDataset` 在构造时复制 v2_policy、runtime_requests、safety_facts、runtime_profiles，避免原始构造参数继续持有内部来源字典的别名。四个公开属性只返回脱离内部状态的深拷贝，没有 setter；修改返回值不再改变快照，也不能通过公开属性重新绑定来源对象。

request_input 直接读取私有来源并复制所需 ProfileSnapshot，不因单条请求解释而导出整份 runtime 字典。原有 context、营地、装备、费用、资料等 DTO 拷贝接口保持不变。

规则热路径使用以下新增接口，避免每次条件检查或取一条记录都复制整个公开视图：

| 接口 | 行为 |
| --- | --- |
| has_v2_policy | 仅返回是否存在 v2 策略，不复制字典 |
| get_gear_policy(gear_rule_id) | 返回单条 gear 策略的深拷贝；不存在时为 ADAPTER_FAILURE |
| get_cost_policy(cost_id) | 返回单条 cost 策略的深拷贝；不存在时为 ADAPTER_FAILURE |
| get_safety_facts(safety_case_id) | 返回单条事实的深拷贝；不存在时保持旧 .get(..., {}) 的空字典语义 |

公开全量属性继续保留原有 dict／DTO／Decimal 结构，供显式导出或兼容读取；不能靠修改这些返回值更新业务输入。需要变更输入时仍应修改受控来源并重新检查、加载与登记。

## 验证

本机 macOS/Python 3.12 离线定向回归 **474 passed，0 failed／errors／skipped**，不是全量应用或原生 Windows 验收。该轮包含新增的 27 项隔离测试，以及 Adapter、规划／物流／安全规则、证据选择、物流／安全模型 Mock 组件、Hybrid 与 checkpoint 编排测试。

最后进一步加强了隔离测试的预期值拷贝，避免预期值自身也引用被测字典而产生假通过；27 项单独复验全部通过。这个复验是 474 项的同名子集，不另计为 501 项。

新增覆盖：v2.0/v2.1 的四类公开来源嵌套修改与清空、公开属性重新绑定拒绝、构造参数别名、单条 runtime 请求资料、按记录 getter、不同反馈／场景的配置隔离、并发导出视图修改。热路径测试在禁用所有公开全量来源属性后仍执行推荐、物流评估和 request_input，证明这些路径不依赖整包导出。

另在两个独立 Python 进程中比较未改动的冻结 418ae1e 导出与当前补丁，**18 组投影一致**：

- 两个数据版本的来源视图、context 和 runtime 请求投影。
- 规则 binding，以及物流／安全四种 rules/model 组合的 Hybrid 注册 context。
- 四套规划输入、三个预算的物流方案、四种安全输入。

比较涵盖所测 context／身份、结果／方案、Mock 请求内容及 trace（仅排除 elapsed_ms）。这只是有限假配置与 Mock 场景，不证明所有输入、所有身份或真实模型输出相同。未更改 Adapter／规则／共享契约版本标识；当前所测有效业务输出和登记身份保持一致。

Shared JSON schema 检查通过，git diff --check 通过。模型组件测试阻止外部 socket 连接，只使用 MockTransport；校园真实调用 **0 次**。

本机 XML 位于 var/snapshot-isolation-final-20261021.xml（474 项）及 var/snapshot-isolation-checks-20261021.xml（27 项）。修复前测试失败及中间回归也保留在 var，不作为共享原始日志发布。

## 留给 A 的 runtime 边界

这不是“整个 Dataset／binding 已不可变”的承诺。Python 私有成员仍可由受信代码访问；本补丁不防御任意进程内恶意改写。

特别是 build_v2_binding 仍给新加载的 Dataset 设置 selected_safety_case_ids。A 不应在不同选择的 binding 之间共享一个实例并原地重设该属性。应保持绑定局部隔离，或以完整选择身份隔离条目；后续设计如需改变此行为，需共同复核。

完整缓存键、工厂更新、密钥清空／轮换、模型客户端创建、角色能力检查、当前输入校验、跨日 for_scope／validate_scope 语义、缓存淘汰和重建仍由 A 的补丁负责。不能把本次来源视图隔离当作跳过这些检查的依据。

构造时取得来源所有权仍有一次复制成本，外部显式读取全量属性也会复制；本轮只验证热路径不做整包导出，没有宣称完成缓存性能优化或保证总耗时改善。A 的实际缓存补丁到位后，应再共同测量命中／失效、登记身份一致性、跨日恢复、保存回执及原 20 秒 HTTP 用例。

本轮没有运行 HTTP 代表用例、浏览器或全量验收，没有操作原 run／原数据库，不关闭 A68，不合并 PR #6。
