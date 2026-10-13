# A-17：真实校园模型异常与保存恢复验收

日期：2026-10-13。完整A14/A15、B Hybrid组件和A16已经快进合入远端main，基线为 `9996e74c80fd2b18feb01717d5a98eee03d29694`。原分支 [CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38324483104) 和 [main CI](https://github.com/LyraWangDev/ELEC5620-G19/actions/runs/38324923871)均通过；没有创建PR或强制推送，保留全部原始提交历史。

本轮在 `feature/a17-campus-exceptions` 保存新增验收记录，没有业务代码、共同schema、个人配置或封存数据变更。

## 实际验证

四个独立SQLite数据库，真实校园代理和Client/Coordinator/Hybrid；观察类只统计调用，不替换消息、模型回复、工具结果或网络transport。Profile保存、请求草稿、解释、明确确认和调度均通过实际鉴权HTTP；模型实际选择以下营地，未强制选择。随后浏览器登录并读取三套已保存的异常结果，不把这三套记成“全程由浏览器新建”的验收。

| 场景 | 实际结果 | 服务端与页面限制 |
| --- | --- | --- |
| 超预算 | Wattle Rest，露营估算AUD251、预算AUD245；物流REVISION，安全PASSED | 最终保存HTTP409/FINALISATION_BLOCKED；页面提示需修订，无最终保存入口 |
| 安全证据缺失 | River Flat，天气MISSING，安全REVIEW；天气装备条件未明确，物流REVISION | Founder批准HTTP409/INVALID_STATE；最终保存HTTP409/FINALISATION_BLOCKED；页面要求补齐证据 |
| 道路关闭 | Moonlit Field，物流PASSED，安全BLOCKED，实际ROAD_CLOSED | Founder批准HTTP409/INVALID_STATE；最终保存HTTP409/FINALISATION_BLOCKED；页面明确人工批准不能解除blocker |
| 保存回执丢失恢复 | 真实模型成功后，A已经提交版本和trace，再受控注入一次PERSISTENCE_FAILURE；run先FAILED | 关闭并重建实际应用/调度器，同数据库重试SUCCEEDED；原版本/内容/trace/生成attempt不变，没有额外模型调用 |

恢复测试中的故障是受控注入A持久化响应丢失，不是实际校园代理宕机、超时或非法回复；这些网络故障未在本轮验证。模型HTTP仍真实执行。恢复后的正常输入可满足eligibility，但本轮不再次创建最终记录。

四次真实规划合计8次HTTP尝试，服务返回身份均为 `Qwen/Qwen3.8-27B-FP8`；成功响应usage为输入14594、生成2802、合计17396。usage不是完整计费报告，没有校园收费信息，不能推算金额。上表AUD金额是合成露营费用估算，没有实际付款/预订。

每个数据库均为1run/1版本/1trace/2评估，0审核记录、0最终记录。受控恢复复用同一个run，原生成trace仍一致。只读复核通过实际审计校验、SQLite integrity_check和foreign_key_check；三个页面error日志为空，最终保存按钮均不存在。截图见 [超预算](evidence/a17-live-budget.png)、[缺失证据](evidence/a17-live-missing.png)、[封路](evidence/a17-live-road.png)；完整受控trace/校验结果见 [JSON证据](evidence/a17-live-exceptions-check.json)。

首次验收脚本把“审批拒绝”的错误类型预期成FINALISATION_BLOCKED，导致缺失/封路两个命令断言失败。核对既有ReviewService后，实际HTTP409/INVALID_STATE符合审批契约；使用同一保存记录复核，未重新调用模型，没有弱化或改动应用守卫。最终保存拒绝仍使用FINALISATION_BLOCKED。

## 给B的交接

请从最新main的9996e74开始后续开发，无需再依赖旧A16分支。工厂、实际端口和trace恢复见 [A16接线](campus_model_wiring.md)。正常场景及本轮异常的真实校园调用证据分别保留，不能把只运行模型CLI当作应用闭环。

下一项模型能力仍是REVISE/REASSESS和其他角色。开启能力前须明确supported_operations、修改意见/确认快照、版本/run/评估身份及trace必需语义；原审核与最终快照不能自动沿用，强制blocker和证据不足仍不能人工放行。当前PLAN-only保持，界面通过新建/确认需求处理变更。

可转发：

> 完整A16及正常场景真实验收已合main（9996e74），CI通过，请从更新main继续开发。新增真实模型测试确认超预算、缺失天气和封路均不能最终保存，缺失/封路不能人工批准；实际模型成功后保存回执丢失，重启重试复用原版本和trace、不再次调用模型。审批拒绝使用HTTP409/INVALID_STATE，最终保存拒绝使用HTTP409/FINALISATION_BLOCKED。后续请继续PLAN-only以外的能力接口协商，保留这些守卫。

本轮测试服务与三个标签已关闭，8651–8653/5251–5253端口释放。受控测试脚本和数据库仅在忽略的var内，密钥未进入证据或Git。最新干净安装、Canvas下载、第二电脑、完整三个模型角色和模型修订/重评仍待完成，未生成最终ZIP。
