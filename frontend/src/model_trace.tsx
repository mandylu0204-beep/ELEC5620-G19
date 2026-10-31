export type ModelTrace = {id:string;run_id:string;version_id:string;attempt_id:string;input_fingerprint:string;
  trace:{requested_model:string;served_models:string[];configuration_fingerprint:string;prompt_sha256:string;tool_version:string;
    turns:number;http_attempts:number;elapsed_ms:number;candidate_ids:string[];selected_campsite_id:string;decision_summary:string;
    usage:Record<string,number>;validation_passed:boolean}};

export function ModelTracePanel({value,currentRunId,logisticsModel=false,safetyModel=false}:{value:ModelTrace|null|undefined;currentRunId?:string;logisticsModel?:boolean;safetyModel?:boolean}) {
  if(!value)return null;
  const trace=value.trace;
  const reused=!!currentRunId&&currentRunId!==value.run_id;
  return <section className="panel"><details className="planning-details"><summary>AI Planning explanation</summary><h2>Planning model call record</h2>{reused&&<p className="mode-notice">This reassessment reuses the original itinerary and did not call the planning model. The following record belongs to original generation, Token usagenot usage for this reassessment.</p>}{trace.served_models.includes('offline-test-only')
    ? <p className="mode-notice">Offline integration test: simulated model responses, no campus model call.</p>
    : <p>{reused?'Original itinerary choice':'Itinerary choice for this run'} was made by the campus model.{logisticsModel?'Equipment and budget suggestions have a separate logistics model assessment record.':'Equipment costs are assessed by rules.'}Request interpretation and campsite filtering use rules; {safetyModel?'safety suggestions are model-assisted, while deterministic code validates safety rules.':'Safety assessment uses rules.'}</p>}
    <dl className="summary-list"><div><dt>Requested model</dt><dd>{trace.requested_model}</dd></div>
      <div><dt>Reported response model</dt><dd>{trace.served_models.join(', ')||'Not provided'}</dd></div>
      <div><dt>Tool turns / HTTPAttempts</dt><dd>{trace.turns} / {trace.http_attempts}</dd></div>
      <div><dt>Duration</dt><dd>{(trace.elapsed_ms/1000).toFixed(2)} seconds</dd></div>
      <div><dt>Token usage</dt><dd>Input {trace.usage.prompt_tokens??'Not provided'} · Generate {trace.usage.completion_tokens??'Not provided'} · Total {trace.usage.total_tokens??'Not provided'}</dd></div></dl>
    <p className="muted">usageCounts only successful service responses; not a complete billing report. Valid output does not establish safety, approval or final saving.</p>
    <h3>Model choice and suggestions</h3><p>{trace.selected_campsite_id}</p><p>{trace.decision_summary}</p>
    <details><summary>Audit links and configuration summary</summary><p className="identifier">run: {value.run_id} · version: {value.version_id} · attempt: {value.attempt_id}</p>
      <p className="identifier">Configuration: {trace.configuration_fingerprint}</p><p className="identifier">Prompt: {trace.prompt_sha256}</p><p>Tool version: {trace.tool_version}</p></details>
  </details></section>;
}
