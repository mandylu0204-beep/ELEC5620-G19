# 结构化要求与规划前人工协助

> 2026-10-29 后续：已删除新请求的露营想法输入，改用表单直接整理摘要，详见 [结构化摘要交接](structured_request_summary_handoff.md)。本地迁移 12 已在用户随后明确要求重启时执行并备份；下文的“尚未部署”保留原实现阶段记录。

## 范围及冻结接口

用户确认：三类输入（同行特殊需求、偏好、必须条件）采用多选项＋其他要求；露营想法描述保留。无法对应已有条件时先由 Founder 协助明确，不能直接批准未知要求。用户已分配迁移 12；仅在隔离测试数据库执行，不迁移原用户数据库。

1. `GET /api/v1/request-context` 新增 `requirement_choices`（version＋fields）；`GET /api/v1/requirement-choices` 为登录用户提供同一只读目录。值来自现有规则支持词表，不从前端臆造。
2. 需求读取新增 `requirement_help`：needed、items、profile_revision、当前绑定任务。已确认需求不重新读取最新个人资料进行此判断。
3. `POST /api/v1/requests/{request_id}/requirement-help`：expected_revision、expected_profile_revision、command_key。仅所有者可提交；按请求 revision＋资料 revision 固定原文及其他要求。
4. `GET /api/v1/requirement-help`：仅 Founder 的当前待办；`GET /api/v1/requirement-help/{task_id}`：Owner／Founder 读取。删除需求不暴露协助历史；已过期资料仅回看，不能处理。
5. `POST /api/v1/requirement-help/{task_id}/decision`：expected_revision、command_key、decision、reason、mappings。decision 仅 PROPOSE_MAPPING 或 RETURN_FOR_DETAILS；映射必须完整覆盖原项（field/index/original），只能选择该字段已有的 canonical 值。不是风险审批，也不授予营地事实、安全结论或最终保存资格。
6. `POST /api/v1/requirement-help/{task_id}/adopt`：expected_revision、expected_profile_revision、expected_task_revision、command_key。仅 Owner 显式采用；同事务替换对应条件，必要时保存新的同行需求 profile revision，将原需求回到 DRAFT 并使旧摘要失效。采用之后仍须重新生成、核对并确认摘要。
7. 创建、人工处理和采用都有持久化幂等回执及审计事件。资料或需求变化后旧任务不能应用；原确认快照、方案版本、审核、最终记录不改写。
8. 生成摘要前及确认前都由后端检查未明确的其他要求。未知项不会被静默丢弃或靠批准绕过。完全对应已有选项的同义表达不进入此队列；语义否定、限定条件、混合要求不会被模糊匹配。

## 分阶段实现

- 阶段一：去掉登录必填徽标、交通未明确选项和黄色说明；装备名称保留原非空校验，去掉上轮新增徽标。
- 阶段二：后端选项目录、三类复选框及保留其他原文。
- 阶段三：独立需求协助队列、人工映射／退回、用户采用和幂等事务。
- 阶段四：权限、revision、历史不可变及读写回归，最后对最终组合执行检查。

## 迁移 12

新增 requirement_help_tasks／requirement_help_commands／requirement_help_events，分别保存固定任务、命令回执、追加审计。不复用方案审核表，不修改共享运行契约、模型 Prompt、装备或安全规则。原有 migration 1–11 内容不改。运行新版后端会自动执行迁移 12；本轮不重启原服务，不迁移用户数据库。部署前须与 A 对齐编号并备份，或先使用数据库副本。

## 人工协助界面

普通用户在未确认需求详情中提交／刷新状态，核对建议后点击“确认采用建议，暂不规划”。Founder 从侧栏“需求协助”处理。此入口与方案生成后的“人工审核”独立。任何读取、保存、送协助、审核建议和采用操作都不调用真实模型；只有显式生成摘要／规划沿用原执行路径。

## 网页验收步骤（新版后端就绪后）

1. 登录普通账户：登录页不再显示必填徽标；用户名、密码仍需填写。资料页交通下拉只提供已支持方式，空值显示“请选择交通方式”，没有“尚未明确”可选项或黄色说明框。装备名称不显示新增徽标，清空名称仍不能保存。
2. 在同行特殊需求勾选“需要无台阶通道”，保存；在露营请求勾选偏好与必须条件。已有选项只代表明确需求，不代表已有符合的营地。
3. 在其他输入填写已有完整同义表达，例如“需要淋浴”，应对应现有条件，不产生需求协助任务。带否定、私人／热水等限定或复合描述不会按包含关键词粗略合并。
4. 输入目录外的要求，先仅保存草稿。需求详情显示待明确项，可点击“提交人工协助（不调用模型）”。直接生成摘要也会被后端拦截，不消耗模型请求。
5. Founder 登录后进入侧栏“需求协助”，逐项建议对应已有条件并说明理由，或退回补充。此页面没有“批准未知条件”按钮。
6. 用户刷新自己的需求详情，核对原文、对应条件及理由；点击“确认采用建议，暂不规划”。涉及同行需求时会保存新的个人资料 revision。随后重新生成摘要、阅读确认，才可显式开始规划。
7. 等待期间修改需求或个人资料，原任务应失效，不能用旧建议覆盖新输入。重复提交、重复审核和采用丢回执重试不重复写入。
8. 使用其他普通账户读取任务应拒绝；已删除需求的协助记录不再公开。原有方案、最终快照、审批与模型审计仍通过原页面和原权限读取。

## 尚未执行的部署与验收

- 现有用户数据库确认仍为 schema 11，未新增协助表；现有服务未重启。新前端需配合含迁移 12 的后端才能完整使用新增功能，不能只刷新旧后端完成接入。
- 新版后端启动会自动执行迁移 12；本轮仅在隔离测试数据库验证，未迁移原用户数据库。可先由 A 对齐编号并在备份／副本上部署，再进行网页验收。
- 未调用真实校园模型，未完成真实模型或交互式浏览器联合验收。不改变现有模型 Prompt、schema、token、超时或安全审批政策。

## 最终组合验证（2026-10-28）

- 后端全量：1908 项通过，0 失败／错误／跳过；四组各 477 项，已比对完整收集清单，无遗漏或重复。仅统计最终代码组合，之前中断的检查不计入通过数量。
- 证明文件：var/structured-final-full/verified-summary.json；源码 SHA256：468e183968d1532fc734995510c3b1416a168ebb482d9665d033ebd6860e8a50。
- 前端全量：166 项通过；TypeScript、Vite 生产构建、共享 schema 检查及 git diff --check 通过。
- 后端真实 HTTP transport 尝试 0；未调用校园模型。
- 保留已有 Starlette TestClient 弃用及 Vite bundle 大小提示，未产生新的测试失败。

## 修改文件与交接

- 接口及选项目录：backend/app/http_requests.py、application/requirement_choices.py、http_requirement_help.py。
- 任务事务及原始记录：backend/app/storage/requirement_help.py、storage/requests.py、storage/database.py（迁移 12）。
- 仅在显式保存时规范化已知同行需求：backend/app/http_accounts.py；服务路由注册：backend/app/main.py。
- 三类多选及其他：frontend/src/requirement_choices.tsx、profile.tsx、requests.tsx。
- 用户送协助、Founder 处理、用户采用：frontend/src/requirement_help.tsx；路由及角色登录返回：App.tsx、login_return.ts。
- 本轮界面微调：session.tsx、profile.tsx、styles.css；保留前轮装备数量确认及模板入口删除的未提交成果。
- 新增及适配测试：test_requirement_help.py、迁移版本断言、structured_requirements.test.mjs、display_presentation.test.mjs、user_journey.test.mjs。
- 尚需 A 配合部署迁移 12，并按上面的步骤进行网页联合验收。本轮未自动 commit、push 或合并。
