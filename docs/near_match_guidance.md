# A-18：无匹配时的营地比较与调整引导

日期：2026-10-13。开发分支 `feature/a18-near-matches`，基于A17报告分支13a7064（与main9996e74的业务代码一致）。当前本地实施，尚未推送/合main。

## 用户现在可以做什么

无完全匹配结果时，页面直接展示最接近的3个营地，包含名称、已知费用、每项未满足/未核实条件、原需求与营地情况对照，以及调整建议。对照放在规划进度前，原始全部排除理由仍可展开查看。

排序按需要处理的筛选条件数从少到多，同分优先信息明确、已知预算缺口小、偏好匹配多、营地费低，最终按营地ID稳定排序。未知金额不是零，不提供不存在的报价或容量。费用是合成营地小计，明确未包含交通、食物、水和装备，不表示完整行程总费用或付款。

浏览器复现用户输入：两人、2026-11-09开始、22晚/23天、AUD320、quiet/ready-to-eat meals。10个营地全部被排除，最接近的结果为：

| 比较 | 22晚营地费 | 比小组预算多 | 其他显示 |
| --- | --- | --- | --- |
| Demo Moonlit Field | AUD440 | AUD120 | 安静环境未确认 |
| Demo River Flat | AUD550 | AUD230 | 安静环境未确认 |
| Demo Wattle Rest | AUD660 | AUD340 | 合成资料的安静偏好匹配 |

点击任一“参考差异，调整需求”只载入本人原需求表单，原预算320、晚数22、日期11月9日和偏好保留。用户编辑后必须保存、重新生成摘要并明确确认；不会自动降低条件、替换原确认或生成行程。无障碍建议保留真实需求，禁火限制不能靠改表单解除。

## A/B接口与数据边界

新增A-owned HTTP读模型 `recommendation_guidance`，位置在 `GET /api/v1/plans/{id}` 与 `GET /api/v1/runs/{id}` 的顶层；非NO_MATCH为null。结构包含 `near_matches`（最多3条）、excluded_count、ranking、metadata_note、scope。每条含rank/id/name、issues（field/title/status/expected/actual/detail/suggestion/original_reason）、费用/预算缺口、偏好/未知信息和source_ref。

它由本run保存的 `excluded_candidates` 派生，使用原确认需求/Profile。只有当前数据、时钟和完整配置身份与原scope一致，且现规则的逐营地排除理由与保存理由一致，才补充名称、价格、容量等来源事实。来源或配置变化时仍可比较原理由，但原报价/容量/设施保持未知并提示变化；不以新资料改写旧结果。

B共同DTO/schema仍1.0，`RecommendCampsitesResult.candidates`、NO_MATCH结果和硬过滤逻辑均未改；没有新数据库迁移。**near_matches不是可用的Agent候选，不能传入模型营地工具或ItineraryInput候选，也不能解除审核/最终化限制。**本轮不需要B改方法签名。需要B知悉新展示语义，以免后续把未满足条件的比较项当成已匹配营地。

本功能只读，不写推荐、版本、评估或审批；也不调用LLM。已有无匹配记录在相同配置重启后即可展示对照，无需为展示重新规划。原NO_MATCH工作流仍在推荐后结束，不产生行程、评估或model trace。

## 验证与使用

新增9项测试覆盖排序/预算差额、最多3项/稳定同分、明确false与未知区分、人数/季节/无障碍、历史来源变化、匹配结果保持、原确认不被Profile修改覆盖、用户隔离，以及agent无匹配/比较回读无模型调用。修正读模型默认字段后，新功能与最终化的定向复测32项通过（29.80秒），原断言保持。

首轮完整检查644 passed/44 skipped/3 failed（371.29秒）；三项均是HTTP增加null字段，而storage默认读取缺少该字段，导致同一已保存记录的两种读取结果不同。修正PlanQueries默认字段后进行最终完整复测，结果见 [检查摘要](evidence/a18-near-matches-check.json)。没有修改现有安全守卫来通过测试。

最终scripts/check.py退出0：647 passed/44 skipped/1条既有Starlette警告，391.36秒；44项为Windows文件符号链接权限跳过，junction用例实际执行。共同schema1.0同步；TypeScript/Vite54模块构建通过（1.67秒）；pip check、git diff --check通过。

真实浏览器完成登录、Profile保存、需求澄清/确认、实际agent调度、NO_MATCH对照和返回编辑。只读数据库复核返回编辑后仍为1请求/1run/1推荐，0版本/评估/model trace/最终记录；原请求CONFIRMED，copy字段保留，前端error为空，数据库完整性通过。证据：[营地对照](evidence/a18-near-matches.png)、[返回原需求](evidence/a18-copy-original.png)。验收服务/标签已关闭，个人配置、数据包与用户默认数据库未改。

本机查看新功能：在你启动项目的终端按Ctrl+C，再用原来的启动配置重新启动前后端，然后刷新已有的无匹配方案。后端需要重启来加载新读模型；无需清空数据库或重新创建原请求。Canvas干净安装与最终提交包仍待后续验收。

可转发给B：

> A18增加无匹配时的3个最接近营地对照和调整建议，仅是A-owned读模型。共享DTO/schema1.0和Agent签名不变；原candidates仍为空，不自动放松硬条件。请勿将near_matches放入模型工具或行程候选。用户修改后仍须重新确认需求，再按正常工作流筛选/规划/评估。
