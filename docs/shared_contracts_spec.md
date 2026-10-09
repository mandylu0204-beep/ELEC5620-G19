# CampMate AI 共享契约实施说明

> 本文为 1.0 接口冻结时的设计记录；其中实施状态描述保留当时语境。当前代码和验证进度见 [实施状态](implementation_status.md)。

日期：2026-10-08。schema_version：1.0。本文是 A 按 B 请求提供的端口与异常设计，不是已实现代码。D-01 至 D-06、风险路由及六个 Agent 入口已经 B 确认；本轮新增签名、内部类型和错误码由 A 提供，待 B 首版 schema 时核对。所有示例都是设计示例，不是运行记录。

基线见 [A/B 交接](developer_b_handoff.md)，数据库与 HTTP 入口见 [A 应用设计](developer_a_contract_draft.md)，实施顺序见 [A 任务清单](developer_a_backlog.md)。

## 1 共同 contracts 位置与职责

应用根目录：`C:/Users/87901/Desktop/ELEC5620/Stage2/campmate_app`。

共同契约目录：`C:/Users/87901/Desktop/ELEC5620/Stage2/campmate_app/backend/app/contracts`。

以上代码目录尚未创建。相对项目根目录的文件规划如下：

| 文件 | 内容 | 主责 |
| --- | --- | --- |
| backend/app/contracts/enums.py | 三类业务枚举、运行模式、阶段和错误码 | A 合并，A/B 审阅 |
| backend/app/contracts/dto.py | 六项 Agent 能力输入输出、快照、来源、评估及版本上下文 | B 提供 Agent schema，A 补应用 DTO |
| backend/app/contracts/ports.py | AgentPort 与 PersistencePort 的接口定义 | A 提供签名，B 核对调用要求 |
| backend/app/contracts/errors.py | ContractError 及通用错误 DTO | A |
| backend/app/contracts/__init__.py | 明确导出，便于双方从共同位置导入 | A |

contracts 只依赖基本类型与 schema 库，不依赖数据库 ORM、Agent 实现、FastAPI 路由或前端。A 实现 PersistencePort；B 实现 AgentPort。双方不能在各自模块复制另一套同名字段。A 负责合并与契约版本管理；B 可先提交 DTO/schema，无需等待前端完成。

本文锁定语义与边界，实际 schema 库及依赖版本在代码阶段确定。新增可选字段记录版本变化；重命名、删除字段或改变枚举、单位等兼容性变化，先更新契约与调用方。

## 2 序列化与共同字段

| 项目 | 约定 |
| --- | --- |
| 标识符 | A 生成的 ID 为不透明字符串；原包 record_id 只作来源 ID，不能当作登录身份 |
| schema_version | 字符串 `1.0`，与 dataset_version 分开 |
| 日期 | YYYY-MM-DD；未知值 null，非法原值留在字段错误中 |
| 记录时间 | 带时区的 ISO 8601 时间；数据库记录时间与固定 demo_today 分开 |
| Decimal | 内部 Decimal；JSON 为十进制字符串，例如 `"2.5"`；未知为 null |
| Money | 整数 cents 或 null，币种 AUD；禁止把 boolean 当作金额整数 |
| 数量 | 装备数量通常是非负整数；饮水、公里及费用 quantity 可为 Decimal；单位必填 |
| 原始输入 | 显式无效值不能用 Profile 默认值覆盖；null、无效和不支持分别表达 |
| 列表 | 没有元素为 []；必要数据整体缺失时另有 missing 信息，不能用 [] 假装检查通过 |
| 运行模式 | stub / deterministic_demo / agent；运行及所有产物均带 execution_mode |
| 解释与来源 | Agent 输出带 source_refs、assumptions、uncertainties；无法取得来源时说明原因 |

schema 必须拒绝无效金额、未知枚举及关键身份/版本字段伪造。B 返回的结构不符合 schema 是技术错误；用户信息不足则是正常业务结果，返回 clarifications 或 field_errors。

费用计算为 `subtotal_cents = ROUND_HALF_UP(quantity × unit_price_cents)`，ROUND_HALF_UP 的目标精度是整数分。计算前从十进制文本构造 Decimal。例：`"2.5" × 101 cents = 252.5 cents`，行金额为 253 cents。合计加各行已舍入金额。来源以 AUD 表示的单价先乘 100，在边界按同一规则转为 cents；数量或单价未知时该行 subtotal_cents=null，完整 total_cents 也为 null。已知部分可以另报 known_subtotal_cents，不显示为完整总价。

日期关系为 end_date=start_date+duration_nights，duration_days=duration_nights+1。营地费用按晚；食物和水按确认后的约定天数及规则单位。金额为小组总预算。人数、儿童数、帐篷容量、车辆数量及路程没有数据时不得猜测；ProfileSnapshot 增补 children_count（可空），保留 has_children 原值与缺失说明。

Provenance 固定为：source_type=SYNTHETIC；source_name=CampMate Synthetic Demo Dataset v1；source_date=2026-10-07；demo_only=true。原包与独立 fixture 的衍生来源分别记录，不伪装为实时证据。

界面、Assessment 和 Final Plan 显示：

> This prototype uses synthetic demonstration data. It must not be used for real trip planning, campsite availability, or safety decisions.

## 3 枚举与审核规则

| 类型 | 值 |
| --- | --- |
| RequestStatus | DRAFT、ANALYSING、NEEDS_CLARIFICATION、UNSUPPORTED、AWAITING_CONFIRMATION、CONFIRMED |
| PlanVersionStatus | DRAFT、ASSESSING、REVISION_REQUIRED、ESCALATED、BLOCKED、ELIGIBLE_FOR_FINALISATION、REJECTED、FINALISED |
| AssessmentOutcome | PASSED、REVISION、REVIEW、BLOCKED |
| ReviewDecision | APPROVE、REJECT、REQUEST_REVISION |
| AssessmentKind | LOGISTICS、SAFETY |
| RiskLevel / Confidence | LOW、MEDIUM、HIGH、UNKNOWN；UNKNOWN 不自动当作 LOW |
| DataQuality | AVAILABLE、MISSING、STALE、CONFLICTING |
| RoadState | OPEN、CLOSED、UNKNOWN，与 DataQuality 分开 |
| RunStatus | PENDING、RUNNING、SUCCEEDED、FAILED、CANCELLED、SUPERSEDED |
| RunStage | RECOMMENDING、GENERATING、SAVING_VERSION、ASSESSING_LOGISTICS、ASSESSING_SAFETY、ROUTING、COMPLETED |

RiskLevel、Confidence 及 Run 枚举是 A 本轮补充设计，B 首版 schema 应核对。业务结果与运行结果分别展示；SUCCEEDED 表示本次工作完成，可对应 REVISION_REQUIRED 或 BLOCKED，不等于方案获准最终化。

HUMAN_APPROVED 不属于 PlanVersionStatus。保存 decision=APPROVE 后由 A 重算 eligibility。批准不会修改既有 Assessment 的 outcome。

完整且有效的检查若因高风险需要 REVIEW，可以在当前证据有有效授权批准且无其他阻止条件时满足审核要求；必要证据缺失、过期、冲突、修订未完成或 mandatory blocker 未解决时仍不能最终化。不能仅按 outcome=REVIEW 加 APPROVE 两个值判断通过。

强制 blocker 始终阻止放行；高风险、低置信度或未解冲突进入审核；其余可修复问题进入修订。route 与 blockers 分开返回，同一版本可以被要求修订并带 blocker。

## 4 上下文与幂等边界

| 类型 | 必须包含的字段 |
| --- | --- |
| RunScope | command_id、run_id、plan_id、request_id、operation、expected_current_version_id、demo_context、dataset_context、write_keys |
| VersionContext | plan_id、plan_version_id、run_id、input_fingerprint |
| ConfirmedContext | 已确认需求、ProfileSnapshot、确认记录、DemoContext、DatasetContext |
| StoredVersion | VersionContext、version_number、content、status、revision |
| StoredAssessment | assessment_id、VersionContext、kind、result、gear_checklist_id、depends_on_assessment_id |
| Eligibility | eligible、current_version_id、active_run_id、blocking_reasons、review_required、valid_review_id、allowed_actions |

RunScope 由 A 创建。PersistencePort 实例绑定经过授权的命令作用域；B 不传 owner_user_id 或 reviewer_user_id。A 从服务器认证和命令登记取得身份，不相信客户端送来的 run_id、ID 归属或 fingerprint。

首次生成尚无已保存版本：A 先登记 run_id、冻结确认需求和数据上下文；plan_version_id、版本 input_fingerprint 此时可空。append_plan_version 成功后 A 返回完整 VersionContext，再开始评估。命令去重的 payload_digest 与版本 input_fingerprint 是不同用途。

Fingerprint 由 A 对以下不可变内容的规范化快照生成：版本内容、确认需求、Profile 快照、DatasetContext 以及 DemoContext 中影响执行的配置。DatasetContext 包含数据包及独立 fixture 的文件摘要、选用配置和规则版本；来源/fixture 变更必须反映到它。序列化键顺序、日期和 Decimal 文本标准化，排除 mutable status、revision、评估保存时间和 run_id。B 不自行重算或更改 fingerprint；A 提供固定测试向量后双方核对。

同一版本也可以开启新评估 run。A 原子登记新 run 和 active_run_id，旧审批即使 fingerprint 相同也不能跨 run 自动沿用。FINALISED 是历史最终快照，不能用新证据原地重评并覆盖；需新建内容版本再复评。

同一输入的未完成失败可恢复原 run；已完成阶段的重试返回原产物。证据、规则或确认需求变更不是技术重试，需要新 run，需求或行程内容变化还需要新 PlanVersion。

公开命令按 actor_user_id+command_key 去重，同 key 的 operation 和 payload_digest 必须相同；不一致返回 IDEMPOTENCY_CONFLICT。内部写入使用 A 登记在 RunScope.write_keys 的阶段键，按 run_id、操作类型及 write_key 去重，不能将一个公开 command_key 无区别用于所有保存阶段。返回已存产物只是重放结果，不重新激活旧 run 或版本。

## 5 B 的 AgentPort 签名

以下为设计签名，所有调用为异步接口，具体内部实现可以同步。DTO 字段语义继承 [交接文档](developer_b_handoff.md) 第 2、3 节；Python None 对应 JSON null。

```text
interpret_request(input: InterpretRequestInput) -> InterpretRequestResult
recommend_campsites(input: RecommendCampsitesInput) -> RecommendCampsitesResult
generate_or_revise_itinerary(input: ItineraryInput) -> ItineraryResult
assess_gear_and_logistics(input: LogisticsInput) -> LogisticsResult
assess_safety(input: SafetyInput) -> SafetyResult
orchestrate(input: OrchestrateInput, persistence: PersistencePort) -> RunResult
```

OrchestrateInput 包含 A 登记的 RunScope、ConfirmedContext 及可空的 previous_version。RunResult 含 run_id、run_status、stage、产物引用、route、blockers 和可空的 error；不包含可由 B直接写入的最终化指令。

LogisticsInput 带 VersionContext 与已保存版本。SafetyInput 在此之外带 StoredAssessment 类型的 saved_logistics_assessment；SafetyResult 带 depends_on_assessment_id。A 校验该物流记录属于同一 run、版本和 fingerprint。审阅时使用实际已保存的 assessment_ids，不按客户端摘要批准。

B 从 Adapter 得到证据和规则，不能将 expected_*、expected_outcome、测试 missing_fields、标注 severity/confidence 直接传给 Agent 或复制为输出。UNKNOWN 风险/置信度需给出原因并保守处理，不当作已完成判断。

## 6 A 的 PersistencePort 签名

以下为绑定授权 RunScope 的异步内部接口；不是 HTTP API。A 在每次写入的短事务中校验作用域、当前版本、active_run_id、fingerprint、状态和写入键。慢速 Agent 调用在事务外执行。

```text
load_confirmed_context() -> ConfirmedContext

save_recommendations(
    result: RecommendCampsitesResult,
    write_key: str
) -> StoredRecommendations

append_plan_version(
    expected_current_version_id: str | None,
    content: ItineraryResult,
    request_id: str,
    reason: str,
    write_key: str
) -> StoredVersion

save_assessment(
    context: VersionContext,
    kind: AssessmentKind,
    result: LogisticsResult | SafetyResult,
    write_key: str
) -> StoredAssessment

report_stage(
    stage: RunStage,
    status: RunStatus,
    error: ContractError | None
) -> RunSnapshot

route_assessed_version(
    context: VersionContext,
    proposed_route: PlanVersionStatus,
    reason: str,
    write_key: str
) -> RouteResult

load_review_result(
    context: VersionContext,
    assessment_ids: list[str]
) -> ValidReview | None

evaluate_eligibility(context: VersionContext) -> Eligibility
```

| 方法 | 返回与事务要求 |
| --- | --- |
| load_confirmed_context | 返回真实确认记录与冻结快照；未确认或归属不符时拒绝 |
| save_recommendations | StoredRecommendations 含 recommendation_id、request_id、run_id、result；NO_MATCH 可正常保存，Adapter 加载失败不能保存为 NO_MATCH |
| append_plan_version | 首次 expected_current_version_id=null；修订必须等于当前指针。原子生成版本号、保存内容、绑定 run 与 fingerprint、切换 current 指针；旧内容不变 |
| save_assessment LOGISTICS | LogisticsResult 已含 gear_checklist；A 在同一事务保存清单、物流评估和关联，返回 gear_checklist_id。B 无需单独保存清单 |
| save_assessment SAFETY | result.depends_on_assessment_id 必须是当前 run 已保存物流评估；来源关系和结构校验后保存，禁止改写评估所依赖的物流结果 |
| report_stage | 仅报告该 run，保持合法单调进度；阶段失败记录 error，不将业务版本改成成功。终结状态不能被迟到消息重新打开 |
| route_assessed_version | 只接收本次有效评估对应的 REVISION_REQUIRED / ESCALATED / BLOCKED / ELIGIBLE_FOR_FINALISATION 建议；A 再校验，不接受 FINALISED、REJECTED 或 HUMAN_APPROVED |
| load_review_result | 仅返回精确匹配当前 run、fingerprint 和证据集且有授权的有效审核；无有效审核为 None，不隐式沿用旧结果 |
| evaluate_eligibility | 返回阻止原因和真实允许动作，无保存最终记录的副作用。最终化 HTTP 服务还需在最终事务中重算 |

原 0.2 草案的 save_gear_checklist 能力合并到 save_assessment(LOGISTICS) 的事务中；若 A 内部有同名 helper，不作为 B 必需调用入口。这避免清单与评估保存一半却被认作完成。

A 负责运行登记、用户审核记录和最终保存，三者不通过 B 的 PersistencePort 执行。证据变化时 A 的应用服务先建立新 RunScope，再调用 B 的 orchestrate。前端重试和人工动作仍走 A 的权限与版本检查。

陈旧写入统一拒绝推进当前状态并返回 STALE_CONTEXT。此前已保存的历史产物保留；迟到结果可写入独立运行诊断日志，不能塞入当前有效 assessment 或解除 blocker。

## 7 异常结构及业务结果

ContractError 字段：code、message、field_errors、recoverable、allowed_actions、context。HTTP 层另附 trace_id。context 可以含 request_id、plan_id、plan_version_id、run_id；没有或无权查看的 ID 不返回。原始堆栈、密钥、数据库连接信息不返回给前端。

业务上的澄清、NO_MATCH、REVISION、REVIEW、BLOCKED 作为成功的结构化结果返回。缺失安全证据不是 Adapter 崩溃；有数据状态的 Evidence 返回 MISSING。文件不存在、解析崩溃或返回不符合 schema 才是技术异常。

| code | 公开 HTTP 状态 | recoverable / 处理 |
| --- | --- | --- |
| UNAUTHENTICATED | 401 | 登录后重新操作 |
| FORBIDDEN | 403 | 不自动重试 |
| NOT_FOUND | 404 | 包括不应向其他 Camper 泄露的资源 |
| INPUT_INVALID | 422 | 修改字段后重新提交 |
| REQUEST_NOT_CONFIRMED | 409 | 先确认当前摘要 |
| STALE_CONTEXT / VERSION_CONFLICT | 409 | 刷新当前版本；不重放陈旧写入 |
| IDEMPOTENCY_CONFLICT | 409 | 同 key 内容冲突；重新发起新的合法命令 |
| INVALID_STATE / FINALISATION_BLOCKED | 409 | 展示阻止原因及实际允许动作 |
| CONTRACT_INVALID | 502 | Agent 返回格式不合法；保留最后有效状态，交由开发修复 |
| ADAPTER_FAILURE / AGENT_FAILURE | 503 | 按具体原因设 recoverable；可恢复时允许重试 |
| PERSISTENCE_FAILURE | 503 | 事务回滚；输入未变且存储恢复后可重试 |

以上 HTTP 状态用于直接请求失败。后台任务失败后 GET workflow-runs 仍返回 200 与 RunSnapshot，其中 run_status=FAILED、error.code 等描述失败，不能把轮询读取成功误认成工作流成功。

allowed_actions 的值为 EDIT_INPUT、RETRY、REQUEST_REVISION、REFRESH、WAIT_FOR_REVIEW、CONTACT_OPERATOR 中真正适用的集合。字段是否显示取决于 A 当前权限与状态，不由 B 的建议直接授权。message 用于展示，程序按 code 判断。

字段错误形式为 field、code、message；code 为 MISSING / INVALID / AMBIGUOUS / CONFLICTING / UNSUPPORTED。例如下面是保存故障的格式示例，没有发生真实保存故障：

```json
{
  "error": {
    "code": "PERSISTENCE_FAILURE",
    "message": "最终方案未保存，请稍后重试。",
    "field_errors": [],
    "recoverable": true,
    "allowed_actions": ["RETRY"],
    "context": {
      "plan_id": "example-plan",
      "plan_version_id": "example-version",
      "run_id": "example-run"
    }
  },
  "trace_id": "example-trace"
}
```

## 8 数据交付入口

原始包目录：`C:/Users/87901/Desktop/ELEC5620/Stage2/campmate_synthetic_demo`。部署与 B Adapter 使用可配置路径，不在应用中写死本机路径。

| 文件 | 数量 / 用途 |
| --- | --- |
| [营地](../data/synthetic_demo/data/synthetic_campsites.csv) | 10 个虚构营地 |
| [装备规则](../data/synthetic_demo/data/synthetic_gear_rules.csv) | 30 条 |
| [费用参考](../data/synthetic_demo/data/synthetic_cost_reference.csv) | 16 条 |
| [用户资料](../data/synthetic_demo/data/synthetic_profiles.json) | 5 份来源资料，不是认证账号 |
| [请求](../data/synthetic_demo/data/synthetic_requests.json) | 12 条，标注字段需与真实输入隔离 |
| [安全场景](../data/synthetic_demo/data/synthetic_safety_scenarios.json) | 10 个，部分日期及营地关联需修订 |
| [Agent 测试](../data/synthetic_demo/tests/synthetic_agent_test_cases.csv) | 30 条静态预期，不是运行证据 |
| [字典](../data/synthetic_demo/docs/synthetic_data_dictionary.md) | 嵌套字段、单位、枚举需同步修订 |
| [UI 文案](../data/synthetic_demo/docs/synthetic_ui_content.md) | 30 条 |
| [原验证报告](../data/synthetic_demo/FINAL_VALIDATION_REPORT.md) | 仅静态数据验证，适用范围见独立报告 |

独立复核见 [数据检查报告](synthetic_data_review.md)。原始包保留不改；修订 fixture 另存独立目录与版本，附来源、修改原因和明确输入。不要把 expected_* 混入实际业务输入。

首轮四个场景仍需数据负责人/B 补齐：正常流程的装备数量、容量、交通、五类费用与整段行程证据；超预算的计费单位和低成本替代方案；缺失证据场景的独立 ID、有效范围、缺失项；道路关闭的营地、日期与关闭证据。它们目前是待准备项，不是已有可运行 fixture。

## 9 交接与实施状态

D-01 至 D-06、路由：已确认。本文：A 已提供的设计文档。共享代码目录、schema、端口实现、Agent 规则、stub、运行样例及联调：尚未完成。原始数据文件未修改。

B 可以据此先交付 schema 与 Adapter；A 在用户允许进入代码阶段后可搭建前后端、数据库、权限及 stub 边界。stub 必须显示其运行模式与产物来源，并在模式切换时保持原历史记录的模式标签。
