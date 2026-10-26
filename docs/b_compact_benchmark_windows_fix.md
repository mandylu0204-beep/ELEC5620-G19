# B → A：Windows 紧凑基准脚本兼容修复

基线 `57bbdc0`；独立分支 `fix/windows-compact-benchmark`。日期：2026-10-26，Australia/Sydney。

## 修复范围

只修改 `scripts/safety_compact_benchmark.py`，新增脚本回归和本说明/脱敏证据。核心 v4 编解码、提示、schema、身份、纯校验器、原组件测试、生产注册与默认 rules 均未改变。没有新增真实调用或正式评估/审计，也没有合 main。

此前脚本先 patch socket.connect/connect_ex，再调用 asyncio.run。Windows 标准库在创建事件循环时可能需要本机 TCP socketpair，因而在真正的 Mock 比较开始前就被误拦。这不应通过放开任意 localhost 解决。

现在使用以下生命周期：

1. 先进入标准库 asyncio.Runner，让其创建事件循环和内部唤醒通道；此时不加载基准夹具或执行模型/应用逻辑。
2. 启用全局连接和真实 HTTP 拦截，再加载夹具、执行同一循环中的两版 Mock 比较。
3. 在拦截仍生效时关闭 Runner：取消未完成任务、关闭异步生成器、清理执行器和事件循环。
4. 最后恢复原函数；外层 Runner context 的再次 close 为幂等空操作。

普通外网、校园地址、IPv4/IPv6 loopback 的 connect、connect_ex、create_connection 及同步/异步真实 httpx transport 仍一律拒绝，不存在任意 localhost 白名单。新增测试也确认清理阶段不能通过后台任务或异步生成器发送连接。

## 验证结果

本机 macOS / Python 3.12.15：

- 首轮 86 passed，后补异步生成器清理检查，最终 **87 passed / 0 failed / 0 errors / 0 skipped**，退出码 0，11.986 秒。
- 其中新增基准兼容/网络保护测试 24 项，既有 v4 候选测试 63 项。全局真实 HTTP transport 触发数 0。
- Windows 风格的“循环启动需要本机连接”用无网络流量 sentinel 模拟，通过后验证应用阶段同地址仍被拒绝。
- CLI 原生进程运行退出码 0，解析后的全部 JSON 指标、请求摘要与 57bbdc0 的 portable_fixture_metrics 精确一致；第二轮仍为 v3 17321 / v4 12481 bytes。
- CLI 回归使用解析后的 JSON，不固定 LF/CRLF 行尾。
- 原 v4/v3/共享 schema 检查通过，核心候选文件摘要与 57bbdc0 证据一致。既有 Starlette/httpx 弃用警告保留。

**未在本机原生 Windows 运行。** 模拟检查及 macOS CLI 不能冒充 Windows 验收通过，请 A 在原生 Windows 离线复跑。A 对 57bbdc0 的 388 项协议测试和 43 项证据检查属于此前结果，本轮不混算或宣称重跑全量。

## A 的 Windows 离线复跑

在仓库根目录使用现有开发环境；临时目录须选未使用的新后缀，避免 pytest 清理旧证据。无需校园网络或真实密钥，不运行 Actions：

```powershell
$env:PYTHONPATH = "scripts"
$env:PYTHONDONTWRITEBYTECODE = "1"
.\.venv\Scripts\python.exe -m pytest -p v22_offline_transport_guard backend/tests/test_safety_compact_benchmark.py backend/tests/test_safety_compact.py -p no:cacheprovider --basetemp var/pytest-compact-windows-review-unique
.\.venv\Scripts\python.exe -B scripts/safety_compact_benchmark.py
```

PYTHONPATH 设置仅用于该终端的此次离线复跑，可结束终端或恢复原值。compare() 现在自行管理完整事件循环及保护生命周期；不要再在调用它之前另行 blanket patch 所有 socket.connect，否则会重新拦截 Windows 标准库启动。

## 交接与证据边界

兼容补丁只变更基准控制方法，不改变请求/响应协议，适合独立提交后供 A 接线分支接入。原 57bbdc0 报告及源摘要保留原样，不改写历史证据；本次基准新摘要与回归摘要见 [JSON](../evidence/b-compact-benchmark-windows-fix.json)。

本轮校园调用 0、Actions/云端测试 0，未改个人配置或原数据库，未 commit/push。请先核对这个窄补丁及原生 Windows 结果，不为此重复真实 SafetyAgent 调用或 normal PLAN。
