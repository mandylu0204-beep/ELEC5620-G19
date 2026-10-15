# A → B：真实物流联合验收反馈

2026-10-15。请先保留PR #5，暂不合main。

已通过真实校园调用及浏览器验收的部分：正常PLAN及最终保存；超预算REVISE（Wattle Rest 25100 cents → Moonlit Field 23100 cents，预算24500）；同版本REASSESS（保留行程/原规划trace，新增本次物流audit）；重启回读、历史最终快照和owner隔离；道路关闭BLOCKED且最终保存/人工批准均409。另用真实模型产物验证物流已提交后丢回执：重启恢复0新增模型调用，原audit/版本/trace保持。

发现并已由A修正：2048输出额度真实截断，返回length、content=null；公开默认值及模板改4096。独立诊断和正常应用完整调用均通过。个人配置文件未改；已有文件若指定2048仍需显式调整。完整集成分支是 `feature/a25-logistics-integration`，包含你的bc5c74f、main 9b54143和A修正4c07ddf；该提交CI 860 passed，schema/前端构建通过。

**合并前仍需处理：** 未改动的missing_evidence输入实际选择River Flat，物流第二轮连续502，初次加两次恢复都失败。1version/1planning trace一直复用，0logistics audit、0assessment、0final；因此尚未验收安全缺资料结果。额外未知帐篷数量变体也在物流阶段502，尚未覆盖其真实未确认/未知费用路径。

诊断：missing_evidence为16项装备、10项费用，未超协议上限；独立真实请求第二轮约30秒后返回上游502。根因尚未确认，不能只提高本机timeout或把它标为已通过。代理拒绝chat_template_kwargs（422）；独立reasoning_effort=low诊断可得HTTP200但组件仍CONTRACT_INVALID，均未正式接线。

请先合并A集成分支再检查物流请求/响应体积、JSON协议和调用耗时，并确认校园代理的上游错误；调整Prompt或参数时保持身份登记、严格事实校验和checkpoint语义。修复后联合重跑missing_evidence与未知数量变体，不要规则回退、跳过安全或补造trace。

详细证据见 [真实验收报告](logistics_live_acceptance.md) 和 [脱敏JSON摘要](evidence/a25-live-logistics-check.json)。本轮尚未证明四场景全部真实通过，也未做Canvas下载部署验收。
