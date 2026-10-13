export type ModelTrace = {id:string;run_id:string;version_id:string;attempt_id:string;input_fingerprint:string;
  trace:{requested_model:string;served_models:string[];configuration_fingerprint:string;prompt_sha256:string;tool_version:string;
    turns:number;http_attempts:number;elapsed_ms:number;candidate_ids:string[];selected_campsite_id:string;decision_summary:string;
    usage:Record<string,number>;validation_passed:boolean}};

export function ModelTracePanel({value,currentRunId}:{value:ModelTrace|null|undefined;currentRunId?:string}) {
  if(!value)return null;
  const trace=value.trace;
  const reused=!!currentRunId&&currentRunId!==value.run_id;
  return <section className="panel"><details className="planning-details"><summary>AI 规划说明</summary><h2>模型规划调用记录</h2>{reused&&<p className="mode-notice">本次重评复用原行程，未调用规划模型。以下是原版本生成时的记录，Token usage不是本次重评的消耗。</p>}{trace.served_models.includes('offline-test-only')
    ? <p className="mode-notice">离线接线测试：本次使用模拟模型响应，未调用校园模型。</p>
    : <p>{reused?'原版本行程选择':'本次行程选择'}由校园模型完成。需求解释、营地筛选、装备费用和安全评估仍由规则执行。</p>}
    <dl className="summary-list"><div><dt>请求模型</dt><dd>{trace.requested_model}</dd></div>
      <div><dt>服务返回模型</dt><dd>{trace.served_models.join('、')||'未提供'}</dd></div>
      <div><dt>工具轮数 / HTTP尝试</dt><dd>{trace.turns} / {trace.http_attempts}</dd></div>
      <div><dt>耗时</dt><dd>{(trace.elapsed_ms/1000).toFixed(2)}秒</dd></div>
      <div><dt>Token usage</dt><dd>输入 {trace.usage.prompt_tokens??'未提供'} · 生成 {trace.usage.completion_tokens??'未提供'} · 合计 {trace.usage.total_tokens??'未提供'}</dd></div></dl>
    <p className="muted">usage仅统计服务返回的成功响应，不是完整计费报告。输出校验通过不代表方案安全、获批或已经最终保存。</p>
    <h3>模型选择与意见</h3><p>{trace.selected_campsite_id}</p><p>{trace.decision_summary}</p>
    <details><summary>审计关联与配置摘要</summary><p className="identifier">run：{value.run_id} · version：{value.version_id} · attempt：{value.attempt_id}</p>
      <p className="identifier">配置：{trace.configuration_fingerprint}</p><p className="identifier">Prompt：{trace.prompt_sha256}</p><p>工具版本：{trace.tool_version}</p></details>
  </details></section>;
}
