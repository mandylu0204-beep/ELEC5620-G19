# B → A：校园模型 Planning Coordinator 接线协商

日期：2026-10-12。B 分支：feature/llm-multi-agent-runtime，基于已合入 PR #3 的 main（57a378f）。
本文是本轮组件交付与接线建议，不代表 A 已同意，也不代表真实模型 HTTP/浏览器闭环已经完成。本轮没有向 A 发送消息、注册应用工厂、修改个人应用 .env、commit 或 push。

最新进度：成员 B 已提供校园代理连接及正常场景模型规划成功的 CLI 输出，已归档为 [真实运行文本](evidence/campus_llm_live_run_20261012.txt)。这是成员提供的实测记录，助手本次仅转存，没有重新调用模型；具体证据与边界见第 7 节。

## 1. 交付范围与完成边界

B 已实现：

- ELEC5620 校园代理的异步 HTTP 客户端、独立本地配置及不含密钥的配置身份。
- 内部 PlanningProposal / JSON 动作协议、结构和业务校验。
- Planning Coordinator：请求只读营地工具，选择一个真实候选，返回逐晚安排与简短决策摘要。
- 营地工具：只使用已加载业务快照，并将结果限制为保存推荐中仍满足硬约束的候选。
- 转换为共同 ItineraryResult(mode=agent)，同时返回可关联运行的 PlanningTrace。
- 独立连接探测与规划 CLI、86 项离线组件回归。
- 成员 B 的真实校园 --probe / --plan normal 成功输出已保存；不再仅有模拟响应测试。

尚未实现/验证：

- 完整的模型版 AgentPort、应用中的 agent 工厂与 HTTP/browser 接线。
- 模型版请求解释、Gear/Logistics Agent、Safety Agent、模型修订。
- PlanningTrace 的 A 侧持久化与 run/version/attempt 关联。
- 代理原生 function calling 的兼容性（当前验证的是应用层 JSON 工具循环）。
- 真实模型闭环的恢复/最终化验收、远端 CI 和 Canvas 下载部署。

本轮仅完成第一种 AI 角色的模型规划组件。不能声称三个 LLM 角色均完成。规则模式仍是独立测试基线，不自动回退为“模型成功”。

## 2. 学校代理与本地密钥

依据学校 ELEC5620_Proxy_Connection_Guide.pdf 第 3、5、6 页：

- 请求模型 ID：campus-qwen。
- base URL：http://10.167.60.148:8000/v1。
- POST /chat/completions，Bearer 鉴权，非流式。
- 请求包含 model、messages、max_completion_tokens、stream=false。
- 读取 choices[0].message.content。
- 校园直连不通时需使用 USYD VPN。学校提供的是 HTTP 地址，只在受信校园网络/VPN 中使用。
- 不需要 OpenAI 账号或 OpenAI API key；不安装或更改 OpenCode。

HTTP 消息格式参照 [OpenAI 官方 Chat Completions 文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)，这不证明校园代理支持所有 OpenAI 特性。当前不发送 tools、response_format、temperature、seed 或 SDK 专有参数。

仓库根目录的 .env.llm.local 已为 B 创建，初次创建时 ELEC5620_API_KEY 留空，由本人在本地填写；本文不读取或记录其当前值。它属于个人配置，不进入 Git 或源码 ZIP。其他成员从 config/campus_llm.example 创建自己的同名文件，不覆盖已有配置。主要内容：

```dotenv
ELEC5620_API_KEY=
ELEC5620_BASE_URL=http://10.167.60.148:8000/v1
ELEC5620_MODEL=campus-qwen
ELEC5620_TIMEOUT_SECONDS=45
ELEC5620_MAX_COMPLETION_TOKENS=2048
ELEC5620_MAX_ATTEMPTS=2
ELEC5620_MAX_TURNS=4
```

- CampusModelSettings 独立读取该文件；主应用 Settings 不会自动加载它。
- 同名进程环境变量优先于文件；排查时不要输出密钥。
- API key 使用 SecretStr，排除于 repr/model_dump/public_identity。
- 客户端禁止把密钥作为模型消息发送，也拒绝代理在成功回复中回显密钥。
- 不把密钥放进前端、截图、调用证据、提交包或本文。
- .gitignore 显式忽略此文件，现有发布器也会拒绝强制加入的私人 .env 文件。
- httpx 已在 requirements.lock 中锁为 0.28.1；本轮将其从 dev-only 调整为正式运行依赖，无需新增 SDK/框架。

## 3. 代码位置与可调用接口

| 文件 | 能力 |
| --- | --- |
| backend/app/llm/config.py | CampusModelSettings、根目录本地配置路径 |
| backend/app/llm/client.py | CampusModelClient.complete(messages)、validate_configuration() |
| backend/app/llm/planning_schema.py | PlanningProposal、动作解析及 validated_itinerary() |
| backend/app/llm/tools.py | recommend_for_model()、CampsiteToolset.search_campsites() |
| backend/app/llm/coordinator.py | PlanningCoordinator.plan(ItineraryInput) → PlanningOutcome |
| backend/app/llm/__main__.py | 独立 --probe / --plan CLI |

接线示意（不是已经注册的应用工厂）：

```python
model_settings = CampusModelSettings()
client = CampusModelClient(model_settings)
client.validate_configuration()  # 离线检查，不调用模型

dataset = SyntheticDatasetV2Adapter(settings.dataset_path).load(
    expected_context=descriptor.context
)
coordinator = PlanningCoordinator(dataset, client)

# 必须使用 A 保存的真实确认与推荐；不能从 CLI fixture 伪造确认记录。
outcome = await coordinator.plan(itinerary_input)
# 按协商后的 A 审计入口保存 outcome.trace，并关联本次 scope。
# AgentPort.generate_or_revise_itinerary 必须只返回共同 DTO：
return outcome.itinerary
```

plan 的输入约束：

- ItineraryInput 和 recommendations 都明确为 agent 模式。
- 数据版本必须与实际快照一致，行程不能早于固定 demo_today。
- 只支持首次 PLAN；previous_version/feedback 非空时明确失败。
- MVP 一个营地覆盖全部晚数，最多 30 晚，不生成任意旅游活动或跨营地交通。
- 单纯调用本组件不会创建版本、评估、审核或最终记录。

PlanningOutcome 包含：

- itinerary：共有 ItineraryResult，execution_mode=agent，source_refs 来自实际营地记录，不由模型编写。
- trace：请求/服务模型标识、Prompt hash、配置指纹、工具版本、回合/HTTP 尝试数、耗时、候选与选择、简短决策摘要、回复 hash 和可用 token usage。
- trace 不存原始提示全文、模型私有推理、Authorization、API key 或原始错误响应体。HTTP 重试可能在服务端产生额外调用；usage 仅汇总成功响应提供的数据，不是准确计费报告。

## 4. 工具协议与输出校验

为兼容指南仅证明的聊天接口，模型用内容 JSON 请求工具，由应用执行白名单动作。这是应用层工具循环，不声称使用了代理原生 function calling。

第一步必须是：

```json
{"action":"tool","name":"search_campsites","arguments":{}}
```

工具根据已确认需求/Profile 和保存推荐返回真实 business snapshot 的候选。无模型可控的路径、SQL、budget/date/profile 参数；不读取 tests/oracles，不连接真实营地网站。

模型随后可返回：

```json
{
  "action": "final",
  "proposal": {
    "campsite_id": "demo-wattle-rest",
    "nights": ["2026-11-06", "2026-11-07"],
    "decision_summary": "Matches the confirmed quiet preference; assessments remain pending."
  }
}
```

上例仅解释格式，代码没有强制模型选择 Wattle Rest。选择其他合法候选可能导致后续证据不足或超预算；必须保留真实评估结果，不能为了演示成功强行替换选择。

校验拒绝：

- 不存在/未向模型暴露/不在保存推荐中的 campsite_id。
- 不满足确认的目的地、容量、季节、交通、无障碍或营地费硬条件。
- 漏晚、重复晚、倒序、越界日期或数字时间戳。
- 未知动作、非法参数、重复 JSON key、NaN、额外预算/来源/数据库 ID/审批字段。
- 不经过工具就输出 final、超限工具循环、截断或无法解析的回复。
- 静默切换模式、回退规则、修改确认需求或虚构记录。

代码根据有效逐晚安排生成保守 CAMP/休息条目。营地描述和休息段复用原规范文本，避免任意活动描述触发现有安全规则中的未分类活动。模型决策摘要单独标注为未经事实验证的模型意见。时间只是演示占位，不代表真实 check-in/旅行时长。

既有 validate_itinerary 的 deterministic_demo 守卫没有放宽。本轮只提取了 validate_itinerary_content（纯日期/覆盖/关联校验）及 camp_entries（保守渲染），原规则行为仍通过全量回归。

## 5. 请 A/B 确认的接线事项

| 编号 | 协商项 | 建议职责 |
| --- | --- | --- |
| C-01 | agent 模式按数据版本注册 AgentBinding；主运行配置、规划可用性和错误提示接通，不改默认 stub/v1 | A 改应用接线，B 提供绑定/模型能力包装 |
| C-02 | 完整 HybridPlanningAgent 实现六个 AgentPort 方法；只有规划真实调用模型，其余暂为规则工具，并明确显示混合阶段 | B 实现，A 核对能力开关 |
| C-03 | 现有 Orchestrator 调用了 agent._input；现有 RuleAgent._input 和物流/安全的 validate_itinerary 拒绝 agent 模式 | B 提供显式模式校验与共用规则 kernel；A 确认绑定和持久化模式一致 |
| C-04 | Prompt/model/tool/validator 配置指纹纳入 A 保存上下文；保留全部 A 摘要、选用项和规范化身份 | A/B 冻结登记格式 |
| C-05 | trace 通过 A 认可的持久化/审计入口关联 run、attempt、保存版本；处理丢失回执、重启与权限 | A 决定存储位置/签名，B 对接 |
| C-06 | MVP 禁用尚不支持的模型修订/重评操作，或明确拒绝；不能注册幽灵 run 后才发现无能力 | A 确认 HTTP/UI 守卫，B 明确能力范围 |
| C-07 | 模型长调用仍被既有 heartbeat/cancel 管理；retry 从 checkpoint 复用已保存行程和评估 | A/B 实际接线后联合验收 |
| C-08 | 前端经验/交通大小写、装备 key/unit 与规则规范仍需统一；首次模型闭环使用明确规范化的输入，不冒充已经通过真实页面输入 | A/B 协商规范与输入回归 |

C-03 不应通过把 agent 输入复制为 deterministic_demo、运行规则后改回标签来完成。应明确区分运行模式与确定性业务算法，保留 RuleAgent 原有守卫，同时让混合包装在校验 agent 上下文后调用同一纯规则 kernel。金额仍按整数 cents/Decimal；安全 blocker 和最终化权限不由模型决定。

C-04 建议：在原 A context 的 rules_version 前缀后追加 B 模型组件版本和 coordinator.identity 的 configuration_fingerprint；不替换原身份、不丢失 file_digests/fixture_digests/selection_config。指纹包含模型别名、base URL、调用限制、Prompt、输出 schema 和工具/校验版本，不包含 API key。修改这些配置后，旧 run 不得以原写入 key 重算不同内容。代理未披露的底层权重变化无法仅靠别名识别，trace 的 served_models 只提供返回身份信息。

C-05 请明确 trace 是否与版本写入原子保存，或有独立幂等审计收据。不能依赖 Coordinator 的全局“最后一次结果”，否则并发运行会串数据。共享 AgentPort 的行程返回类型不改；trace 不是业务审核/eligibility 的替代物。

工厂就绪检查仅调用 validate_configuration() 与数据/身份校验，不应在每次 GET ready/meta 或 resolve 时进行收费模型探测。真实连通性由显式 probe/live 测试单独记录。缺少凭据不能悄悄回退。

请 A 回复确认 C-01～C-08，尤其是完整包装的责任划分、模式校验、trace 存储接口和首次接线的功能开关。确认后 B 再补 HybridPlanningAgent/工厂；不要把现有 PlanningCoordinator 直接当完整 AgentPort 注册。

## 6. 本地使用与验证

使用按 backend/requirements.lock 安装的 Python 3.12 环境。在 backend 目录执行：

```sh
python -m app.llm --probe
python -m app.llm --plan normal
```

Windows 可从仓库根目录使用已有锁定环境：

```powershell
.\.venv\Scripts\python.exe -m app.llm --help
```

上面的 -m 命令必须能导入本仓库 backend/app（setup.py 的 editable 安装可做到）。若未 editable 安装，进入 backend 后再使用正确的 Python 完整路径。不要用导入到其他 checkout 的环境。

--probe 只进行短连接检查，返回状态/usage，不输出原始模型文本。
--plan 使用 docs/demo/v2_inputs.json 的显式 synthetic 输入，检查规划组件并输出 itinerary/trace。它不是已保存的用户确认，不访问数据库，不执行物流/安全/最终化，也不替代 HTTP/browser 验收。其他三个 case 可用于组件探测，但不保证模型选择与原规则演示相同。

离线回归：

```sh
python -m pytest tests/test_campus_model_client.py tests/test_model_planning.py tests/test_llm_cli.py --basetemp ../var/pytest-campus-components
python -m pytest --basetemp ../var/pytest-campus-full
python -m app.export_contracts --check
```

2026-10-12 本机结果：

- 新增模型组件测试：86 passed。使用 MockTransport/独立假密钥，不需要 VPN，不连接真实服务。
- 完整后端：634 passed，0 skipped，0 failed，47.63 秒；包含原四套真实规则 HTTP、恢复和封存回归。
- 共享 schema 1.0、pip check、git diff --check 通过。
- synthetic_demo_v2 静态验证：68 passed、0 failed；58 条应用规格仍为静态 NOT_RUN。
- TypeScript 与 Vite 构建通过；前端源代码没有更改。
- Python 3.12.14 / Pydantic 2.13.5 / httpx 0.28.1；前端 Node 24.19.0。
- 既有 Starlette TestClient 弃用警告仍保留。
- 数据包、requirements.lock、共享 schema、默认应用配置和原 .env 未变。
- 前述自动化回归未访问真实校园代理；另次成员 B 提供的真实 CLI 输出见第 7 节。实际模型 HTTP/browser、远端 CI、Windows 新平台执行和最终提交包验收仍未完成。

## 7. 真实校园组件运行证据（成员 B 提供）

文件：[docs/evidence/campus_llm_live_run_20261012.txt](evidence/campus_llm_live_run_20261012.txt)。

- 记录日期：2026-10-12；来源为成员 B 在项目对话粘贴的两段终端输出，不是助手重新执行。
- 完整保留两段 JSON 的值，省略终端用户名、电脑名和环境提示符；不伪造原始运行时间、依赖版本或精确代码提交号。
- --probe：PROXY_RESPONSE_RECEIVED，1 次尝试，114 Token。
- --plan normal：PLANNING_COMPONENT_VALIDATED，2 轮/2 次 HTTP 尝试，9506 ms；执行 search_campsites，在 8 个候选中选择 demo-wattle-rest，validation_passed=true。
- 请求模型别名 campus-qwen，服务端报告模型 Qwen/Qwen3.8-27B-FP8。
- 规划 Token：输入 3887、生成 818、合计 4705；连同 probe 为 4819。这是代理返回的 usage 汇总，不是单次请求量或计费金额。
- 本次输出仍明确 application_registered=false、assessments_run=false、finalisation_performed=false；不作为应用 HTTP/页面、评估、保存或恢复成功证明。
- 文本未发现 API key、Authorization 值、Cookie、密码、真实个人 Profile 或学生资料。模型名、工具版本和摘要并非凭据；如公开开源，仍须遵守学校服务披露政策。

Token 使用决定：当前保留角色约束、输出 schema、确认需求/Profile、候选事实和两轮工具交互，不因单次规划约 4.7k Token 而减少测试或删除安全边界。3887 输入 Token 是主要部分，第二轮包含第一轮消息与工具结果，所以存在重复上下文；将来可在不改变语义和来源约束的前提下精简冗余字段。没有学校配额/收费规则，不能断言免费或推断金额。

离线 pytest 使用 MockTransport 与假密钥，不消耗校园模型 Token；--probe/--plan 才会访问真实代理。本轮归档没有再运行任何真实调用，也没有修改 Prompt、模型配置、候选范围或测试代码。

本轮组件实现、离线验证和 B 的真实连接/单组件输出已有证据。下一项是 A/B 模式/审计/恢复接线 → 真实 HTTP 与浏览器 → 正常、超预算、缺失证据、道路关闭与人工审核 → 最终下载包验收。
