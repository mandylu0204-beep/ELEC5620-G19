# 数据版本与运行输入交接（A-10 补充）

2026-10-10。此项为不依赖 v2 规则修正的 A 侧接入准备。默认 v1 数据、demo_today=2026-10-08 和 stub 模式保留；原 v2 仅用于独立审阅，没有导入用户资料、创建业务方案或注册 B Agent。

## A 已提供的边界

`app.application.datasets.inspect_dataset(settings)` 返回 DatasetDescriptor：context（DatasetContext）、provenance（Provenance）、regions。`app.application.request_rules.data_context(settings)` 继续返回 `(context, regions)`，现有调用签名不变。

- 无 manifest 的原 v1 继续使用版本 v1；原六份业务文件的 digest key、摘要算法与 rules_version 保持兼容。
- v2 从包内 manifest.json 读取版本与来源，验证和六份业务记录一致；来源名与版本主版本须匹配。v2 需要两份 runtime 输入文件完整存在，不能退回 v1 或忽略缺失文件。
- 对六份业务文件、出现的 runtime_requests.json/runtime_safety_evidence.json、manifest.json 记录 SHA-256。有效运行数据改变会反映在 DatasetContext 中；每次读取重新计算，不缓存旧身份。
- manifest 包含非空 files_sha256 时，核对实际消费的业务/runtime/配置场景文件；不一致返回 ADAPTER_FAILURE。manifest 可在开发阶段省略该表；正式数据包应封存并校验。不加载 tests、docs 或包内脚本作为业务输入。
- 请求分析及确认的 DemoContext.dataset_version 与实际包版本一致；不采用 manifest 中提议的默认时钟。
- readiness 增加 dataset_context_valid；meta 返回实际 dataset_version/provenance。无效包保持 meta 可查询，但这两个值为 null、ready 为 503。来源身份检查不等于规则、证据质量或完整业务场景验收。
- Provenance.source_name 新增可接受的 `CampMate Synthetic Demo Dataset v2`，v1 的默认值及旧持久化记录保持兼容。来源日仍限定 2026-10-07，source_type 仍限定 SYNTHETIC，demo_only 必须为 boolean true。共享 schema 已重新导出；schema_version 与六个 Agent/持久化端口仍为 1.0。B 需更新共同 DTO/schema，不能沿用只接受 v1 的旧副本。

## 独立场景的配置

新增可选环境变量，JSON 格式：

```dotenv
CAMPMATE_DATASET_SCENARIO_FILES=["data/scenarios/demo-normal.json"]
CAMPMATE_DATASET_SELECTION={"scenario_id":"demo-normal","safety_case_id":"safety-normal"}
```

这些是配置示例，示例文件尚未交付。最终场景由 A/B 与数据负责人对齐后提供。路径相对已选数据包根目录，只允许 data/scenarios 下的 JSON，拒绝 tests 路径、越界路径及越界 symlink。场景只存实际运行输入，不能复制完整测试 fixture；setup/actions/assertions 或 expected_*、风险输出等测试标签会被拒绝。

文件摘要保存在 DatasetContext.fixture_digests，服务器选用项保存在 selection_config。这两个既有 DTO 字段未改名或新增类型。配置只登记本次输入上下文，不会自行创建确认事件、执行场景动作或加载 Agent。业务值正确性、场景 ID 引用及字段到共同 DTO 的完整转换仍需 B Adapter/后续联调验证。

## B 与后续 A dispatcher 的使用要求

1. A 在摘要/确认及登记新 run 时使用相同的实际数据版本、场景摘要和选用配置；B 使用 A 提供的 RunScope/ConfirmedContext，不自行构造身份、run_id 或 fingerprint。
2. B Adapter 不应再绕过已登记的上下文读取另一份 runtime/场景数据。后续 dispatcher 在领取/重试和保存工作前读取当前数据上下文并比较，业务输入应从与摘要一致的读取快照构造；这项调度接线仍待 B 实现后完成。
3. 当前改动保证旧摘要确认被拒绝、输入变化时旧 run retry 被拒绝（调用方传入重新读取的上下文），并使新数据上下文改变版本 fingerprint。证据变化须新 run，审核绑定新 run 的实际 assessment IDs。
4. 这不是文件变化自动监控器：仅修改磁盘文件不会自动登记新 run 或改写历史记录。实际规划/重评入口、后台调度及将当前数据检查接入审核/最终化仍须在 B 联调阶段补齐；当前不声称已完整验证文件变化后所有业务入口的处理。
5. 保持 D-03 Decimal/cents、强制 blocker、当前版本/评估绑定及恢复租约规则。数据包中的 meal_mode、参考金额与时钟问题按 [v2 检查报告](synthetic_data_review_v2.md) 修正，不由此模块偷偷调整。

当前 rules_version 只描述 A 的字段规范化。B 的实际规则实现及版本标识仍待交付；实现变化也必须通过约定的规则版本/选用配置反映到上下文，不能在旧 run 中替换计算逻辑。

## 验证范围

新增 20 项独立 A 测试涵盖 v1 兼容、v2 来源/版本显示、确认快照版本、两份 runtime 文件/场景/选用项变化、错误包与封存摘要不匹配、oracle 污染和路径边界，以及证据变化拒绝旧 retry/改变版本 fingerprint。使用生成的独立身份测试数据，未执行 B 的 56 条验收规格。

另对用户原始 v2 解压副本进行只读身份检查：识别版本 2.0.0、v2 来源与 9 个文件摘要（六份业务文件、两份 runtime 文件及 manifest），不执行包内费用或装备脚本、不改变应用配置。完整回归结果见 [实施状态](implementation_status.md)。
