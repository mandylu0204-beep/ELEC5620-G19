# 公共交通最小支持：实现与交接

> 2026-10-27 后续修正：Sydney 2.2 新运行改由系统负责筛选与准备，不再要求用户提前登记路线计划。见 [系统出行准备交接](system_trip_preparation_handoff.md)。本文保留 `public-transport-minimal-1` 的旧策略与验证记录，供历史恢复及 2.0／2.1 兼容使用，不能用其旧填写步骤验收当前 Sydney 新流程。

日期：2026-10-27（Australia/Sydney）。基线：fix/transport-profile-guidance，5e6258a；保留阶段一以及此前物流诊断／费用协议的未提交改动。

## 交付范围

正式的新 v2 运行保留 CAR 与 PUBLIC_TRANSPORT。公共交通复用现有营地 public_transport_access、装备记录 transport_itinerary、交通说明 transport.assumptions 及 cost-03 模拟往返费用。不新增路线服务、班次查询、分段交通模型、数据库表、迁移或共享 DTO 字段。

公共交通本次运输可行的最低条件为：

1. 每个选中营地都有明确的公共交通可达标记 True。未知不等于可以到达；False 不得放行。筛选继续使用已有保守检查。
2. transport_itinerary 至少一份，单位 plan，数量明确且用户已确认。未知、零份、错误单位或未确认均不能当成有效计划。
3. transport.assumptions 至少有一条非空说明。页面要求描述去程、返程和最后接驳，确认勾选明确表示用户已核对这些安排。

第三项不解析自然语言、猜测班次或宣称说明完整正确。它是“用户声明并确认安排”，不是“系统核实了实际路线”。未知安排可以先保存在个人资料，正式检查仍保留缺项。

费用继续使用按人数计算的模拟往返参考，保留整数分／Decimal；没有实时报价、订票或确认租借。缺单价或未知费用不补零。自驾已有车辆、座位、公里、燃油及停车计算保持不变。装备和安全硬性缺口、审核及最终保存守卫不放宽。

## 规则身份与恢复

新增交通子策略：selection_config.b_transport_policy = public-transport-minimal-1。

- AgentRuntime 为新建的托管 v2 运行登记此服务端标记；WorkflowConfiguration 在完整 rules_version 尾部增加同名版本。
- 直接构造独立组件／调用 factory 时，没有提供标记就有意保留旧行为。A 如有绕过 AgentRuntime 的接线，需明确传入同一标记，不能仅因代码已更新就假定采用了新策略。
- 标记及完整规则身份参与 DatasetContext、输入指纹、模型审计的完整 workflow_context 和配置指纹。它不是客户端授权字段。
- 核心／数据规则版本及冻结安全 Prompt、schema、codec 不变；本次是单独登记的交通输入解释子策略，不修改安全文本协议或已有内核／数据版本配对。
- 显式 PUBLIC_TRANSPORT 的规则变量 vehicle_count 表示本次参与运输的私人车辆数，派生为 0。它不代表用户没有车；不把资料里的 null 改成 0，不更改库存、座位或拥有确认。其他／未知方式不获得这个派生值。
- 旧记录没有标记时，保留原交通规则。for_scope 根据已保存标记或其缺省状态重建运行；未知标记及登记冲突拒绝执行。其余模型配置、文件摘要、时钟和租约检查继续生效。
- RuleAgent、Hybrid 的规则和模型物流路径、Hybrid 产物校验与 Dispatcher 的正式保存验证均传入同一标记；模型方案与持久化不能使用两套不同基线。
- 历史审计继续使用已保存输入、原规则事实和原 seed 纯回放。新策略不改写原快照或旧结果。当前最终化仍检查当前身份；旧评估若已过期，需要明确开启新检查，不能把历史成功视为新策略下已通过。

## HTTP 与页面变化

现有 GET /api/v1/request-context 新增只读 supported_transport_modes，值为 [CAR, PUBLIC_TRANSPORT]；无新增写接口。

- 资料页读取该列表提供选项。WALKING／OTHER 旧值保留可见但标注暂不支持，绝不自动改为 CAR。列表缺失或读取失败时不伪造支持范围。
- 个人资料可保存未知或旧方式；新策略在需求解释（模型调用之前）、确认和正式创建运行时拒绝不支持或未明确的交通方式。确认／运行命令的原幂等回执规则保留。
- 公共交通自动准备一行空白、未确认的连接计划，不伪造数量或安排；已有记录和用户名称保留。
- 交通说明用于记录往返及接驳；连接计划确认框改为“已核对本次往返及接驳安排”。公共交通范围说明在资料页及需求确认页面明确展示。
- transport.assumptions 的结构化问题投影为可编辑 PROFILE 待办，定位到实际说明框；缺营地可达资料是 OPERATOR／DATA_GAP，不给虚假的车辆资料编辑入口。
- 阶段一的字段适用性、实际输入定位、提示计数去重及“表单完成不等于正式通过”继续保留。
- 普通用户读取仍裁剪诊断和完整配置；原始内部 DTO 不使用 HTTP 裁剪结果回填。

## A 复核重点

接口／迁移需求已压缩到上述一个读取字段和一个运行身份维度，没有新数据库迁移。请 A 联合复核：

1. 新子策略在当前规则／模型角色组合的完整身份中正确登记，所有入口消费相同基线。
2. for_scope 对旧标记缺省的重建、丢回执恢复、旧成功记录当前资格失效的边界。
3. 解释、确认和启动的后端守卫，与原命令幂等和权限检查的顺序。

不要求 A 另写一套交通保存 API；现有 profile revision、确认快照和正式运行事务继续复用。本地实现不等于 A 已复核或真实校园验收已通过。

## 修改文件索引

- 子策略与规则：backend/app/agents/rules/transport.py、logistics.py。
- 登记、恢复与正式验证：backend/app/application/agent_runtime.py、dispatcher.py、backend/app/workflow/configuration.py、backend/app/agents/rule_agent.py、hybrid_planning_agent.py、backend/app/llm/logistics_agent.py。
- 支持列表及后端守卫：backend/app/http_requests.py、backend/app/storage/requests.py、repository.py。
- 结构化待办：backend/app/application/logistics_issues.py、frontend/src/logistics_issues.tsx。
- 资料与确认页面：frontend/src/profile.tsx、requests.tsx、profile_guidance.ts、profile_focus.ts、vehicle_profile.ts、vehicle_fields.tsx。部分文件同时包含此前阶段一的修复。
- 新回归：backend/tests/test_minimal_transport.py；前端 profile_guidance、profile_focus、vehicle_profile 和 display_presentation 测试。
- 夹具对齐：backend/tests/test_cooking_preparation.py、test_request_interpretation_lifecycle.py、test_trip_series.py。

工作区另外保留此前已存在的物流 JSON 脱敏诊断和费用优先级协议修复；本轮没有撤回或覆盖它们。提交／评审时请结合各自交接文档区分范围，不将所有未提交差异都归为交通实现。

## 验证记录

新增 tests/test_minimal_transport.py 覆盖车辆未知不误报、旧策略回放、自驾未知不补零、计划确认及说明缺失、营地未知／不可达、缺票价、读取投影、支持方式、个人资料固定和策略身份。标准及 compact 两套离线模型组合覆盖物流已提交后丢回执、重启与同 run 恢复：版本内容、物流评估和审计复用，不重跑规划／物流，只继续缺失安全步骤。

- 针对性后端组合：197 项通过，1 项既有 Starlette 弃用警告。
- 最终前端：140 项通过，TypeScript 类型检查和 Vite 生产构建通过；共享 schema 检查通过。构建仅有既有的 chunk 超过 500 kB 提示。
- 首次全量在发现旧烹饪夹具冲突后中断：夹具原文为即食餐食、显式字段为自行烹饪。已在临时目录的 main / 5e6258a 单独复现同一失败，仅统一该测试的两处用餐输入，不放宽生产规则；7 项烹饪准备测试随后通过。最终全量重新从头执行，不累加此前的局部通过数。
- 新交通入口要求明确方式后再调用解释器，因此为原“只有人数”的模型摘要成功夹具补充明确 CAR；缺失方式的拒绝测试继续保留。需求解释生命周期与公共交通组合 41 项通过。
- 完整分组检查另发现旧系列更新测试也只改显式用餐选项、未改原始陈述。已在未修改的 main / 5e6258a 临时副本复现；只统一该测试每轮的文字与选项，并新增“每轮摘要可确认”的断言，生产冲突守卫不变。系列 11 项复测通过；随后对最终源码重新完整分组检查，不复用失败轮次的通过数。
- 最终完整覆盖使用同一后端源码 SHA-256 指纹生成的 1852 项收集清单，分四组各 463 项并行执行；分组互不重复、合并无遗漏，各自使用独立临时目录。以本轮全部分组的 XML／退出状态验证最终结果，不把前轮 197／41 或中断运行的通过数累加。
- **最终后端：1852 项全部通过，0 失败、0 跳过、0 真实 HTTP 请求尝试。** 四组退出状态和 XML 均已核对，测试前后源码指纹一致：e27664d35fa54d27ff761366485bfa7d6037b626789109a0798348b3b8a6c97c。结果目录为 var/pytest-minimal-transport-release-full-p4rveene，含 manifest.json、四组 XML、summary JSON 和 verified-summary.json。各组只有既有 Starlette TestClient 弃用警告。
- 所有数据库均在 var 下隔离测试目录。完整后端使用 offline_http_guard 禁止真实 httpx 传输；未调用校园模型。
- 不修改个人配置、密钥、原用户数据库、封存数据或历史审计；未重启现有服务，未自动提交、推送或合并。

## 手工测试与未实现范围

代码生效需重启后端，再刷新前端；本轮没有代为重启。

1. 选择公共交通，说明往返及接驳安排；连接计划可先留未知，保存个人资料不应被最终化条件提前阻止。
2. 明确生成需求摘要、确认并启动检查。缺计划数量／确认或说明时，应得到对应待办，没有车辆数量要求。
3. 根据实际安排补充资料，沿同一次出行核对更新，再明确检查；不要把仅保存资料视为已经解决原方案问题。
4. 模拟费用是粗粒度估算；系统不验证实际班次、末班车、实时票价、换乘可行性、携带装备限制或预订。混合交通、步行及其他方式的正式策略仍未实现。

真实模型调用和当前用户浏览器业务会话不在本轮离线验收范围。
