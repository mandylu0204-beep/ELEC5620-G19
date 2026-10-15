# A26：重新检查反馈与资料匹配接入准备

2026-10-15 更新：B 2.1 选择器与页面接入已完成本地组合验证，当前进度见 [组合审查与验收](a26_trip_integration_review.md)。下文保留原阶段记录。

日期：2026-10-15。基于完整 A25 集成 `fa33ac4`，位于独立分支 `feature/a26-check-feedback`。

## 用户行为

点击“保留行程，重新检查”后显示启动提示，后台任务登记后显示检查进度。完成后显示完成时间，以及检查结果与同一行程版本上一次成功检查相比是否变化。即使结论相同也有可见反馈，刷新或重开页面不依赖浏览器内存。

“完成检查”和“方案可以保存”分别表达。道路关闭、资料不足或装备缺口仍按原有服务端结果处理；资料不足时重复检查不会补造资料，也不会解除最终保存限制。

资料或配置变化使用明确的 `CHANGED` 分类；无法核对的服务错误使用 `UNAVAILABLE`。页面不再从错误文字中搜索“变化”等词来猜测原因，服务不可用时不提供误导的修改/重评入口。天气计算缺口使用已知字段的中文说明，不让用户去确认后台天气规则参数。

检查进行中不显示“尚未完成评估”作为需要用户处理的警告；本轮金额和安全结果尚未保存时仍显示未知，避免把旧检查混入新运行。

## 只读 HTTP 扩展

`GET /plans/{id}` 与 `GET /runs/{id}` 在已授权查询内增加：

```json
{
  "current_inputs_state": null,
  "check_feedback": {
    "status": "COMPLETED",
    "started_at": "2026-10-15T04:18:34.790399+00:00",
    "completed_at": "2026-10-15T04:18:47.761431+00:00",
    "comparison": "UNCHANGED",
    "compared_run_id": "previous-authorized-run",
    "changed_sections": []
  }
}
```

`check_feedback` 只用于 REASSESS。状态为 IN_PROGRESS、COMPLETED、FAILED 或 INCOMPLETE；比较为 UNCHANGED、CHANGED 或 NOT_COMPARABLE。只有本轮成功结束且装备、安全评估保存完整并关联一致时才报告完成。完成时间来自实际成功事件，不以开始时间冒充。

比较选择同一方案、同一行程版本、当前运行之前最近的成功完成运行。比较已保存的 LogisticsResult 和 SafetyResult，保留费用、数量、未知值、结论、建议和来源变化；剔除必然变化的 version_context 与 depends_on_assessment_id。新评估 ID、run ID 或模型 token 用量不被误算成业务结果变化。

这里比较的是正式检查结果，不比较独立模型物流建议 plan/trace 的全部内容，不宣称模型每次给出的准备建议逐字相同。旧记录不完整或不能比较时不给出“结果一致”。比较读操作不创建运行、评估或模型调用，不影响 eligibility。

共享 schema 1.0、数据库结构、保存端口、模型输入身份和历史 final snapshot 均未更改。页面分类与比较不是最终保存/审批的授权条件。

## 验证

- 新增 6 项集成测试，与原有方案修订/重评回归合计 **19 passed**，包含结果一致但新记录已保存、道路关闭变更、缺资料仍阻止保存、未完成不宣称成功、服务错误按代码分类、用户隔离及新应用实例回读。
- 前端 TypeScript 与生产构建通过（59 modules）；共享 schema 检查通过。
- 全量后端回归：**822 passed、44 skipped、0 failed**（共 866 项）。跳过项均为当前 Windows 环境不能创建文件符号链接的用例；另有既有 Starlette/httpx 弃用警告 1 项。未把这些跳过项计为通过。原始 JUnit 保存在忽略目录 `var/a26-check-feedback/backend-results.xml`。
- 浏览器使用独立 v1 RuleAgent 数据与 SQLite，经实际登录、按钮操作和 HTTP 流程完成 4 次重新检查。对比顺序为 UNCHANGED、CHANGED、CHANGED、UNCHANGED；数据库最终 5 个运行、1 个行程版本、10 个评估，未执行最终保存。
- 页面验证进行中、结果一致、刷新后保留、道路关闭更新、缺资料更新及重复检查仍缺资料；浏览器错误日志为空。SQLite integrity_check/foreign_key_check 正常。

机器摘要：[a26-check-feedback.json](evidence/a26-check-feedback.json)。截图：[进行中](evidence/a26-recheck-running.png)、[结果一致](evidence/a26-recheck-unchanged.png)、[安全变化](evidence/a26-recheck-changed.png)、[资料仍缺失](evidence/a26-recheck-missing.png)。临时浏览器页和服务在验收后关闭，测试数据保留在忽略目录 `var/a26-check-feedback`。

本轮没有校园调用，没有修改个人配置、用户数据库或封存 v2。不是新资料选择器、v3 数据或 Canvas 干净部署验收。

## 下一步边界

A 已完成 [按行程选择资料接口约定](trip_evidence_selection_contract.md) 与 [给 B 的实施交接](a26_evidence_handoff_to_b.md)。当前自动匹配尚未实现，正常运行仍使用原有显式场景配置。需要 B 返回选择器、新数据和业务接线后，A 再完成工厂登记、结构化覆盖提示及联合验收。

未推送、未合 main。A25 真校园物流 502 阻塞仍保留，不能以本轮离线/规则 UI 通过替代真实模型验收。
