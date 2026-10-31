import { failureGuidance } from './failure_guidance';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import type { PlanDetail } from './plans';
import { privateApi, useSession } from './session';
import { tripUpdatePath } from './trip_update';
import {revisionReview} from './review_revision';

export function revealRevisionPanel(id:string,find:(id:string)=>HTMLElement|null=id=>document.getElementById(id)){
  const panel=find(id);
  if(!panel)return false;
  if(panel.tagName==='DETAILS')(panel as HTMLDetailsElement).open=true;
  panel.scrollIntoView({block:'start'});
  find('revision-choice')?.focus();
  return true;
}

export function preservedRevisionNotice(reason:unknown):string|null {
  if(!(reason instanceof ApiFailure)||reason.envelope.error.code!=='INPUT_INVALID')return null;
  return ['NO_CHEAPER_CAMPSITE','CAMPSITE_FEE_UNKNOWN'].includes(reason.envelope.error.context?.revision_outcome)
    ?reason.message:null;
}

export function ChangePlanning({ data, refresh, choice, onChoiceChange,reviewRequest=0 }: { reviewRequest?:number;data: PlanDetail; refresh: () => void;choice:string;onChoiceChange:(choice:string)=>void }) {
  const { session, reload } = useSession();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState('');
  const [sourceReviewId,setSourceReviewId]=useState<string|null>(null);
  const reviewSource=revisionReview(data);
  function useReview(){if(reviewSource){onChoiceChange('custom');setFeedback(reviewSource.reason);setSourceReviewId(reviewSource.review_id);}}
  useEffect(()=>{if(reviewRequest>0)useReview();},[reviewRequest]);
  const [busy, setBusy] = useState<'revise'|'reassess'|null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const command = useRef<{ payload: string; key: string } | null>(null);
  if (!data.run?.is_active || (!data.revision_available && !data.reassessment_available)) return null;
  async function submit(operation: 'revise' | 'reassess') {
    if (!session || !data.run || busy || data.current_version_revision == null) return;
    const text = choice === 'custom' ? feedback.trim() : choice;
    if (operation === 'revise' && !text) { setError('Enter revision feedback.'); return; }
    const body = { expected_current_version_id: data.plan.current_version_id,
      expected_active_run_id: data.run.run_id, expected_version_revision: data.current_version_revision,
      expected_run_revision: data.run.revision, ...(operation === 'revise' ? { feedback: text,...(choice==='custom'&&sourceReviewId?{source_review_id:sourceReviewId}:{}) } : {}) };
    const payload = JSON.stringify({ operation, ...body });
    if (command.current?.payload !== payload) command.current = { payload, key: crypto.randomUUID() };
    setBusy(operation); setError(''); setNotice('');
    try {
      await privateApi('/plans/' + data.plan.plan_id + '/' + (operation==='revise'?'revision-proposals':operation), {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CampMate-Client': '1', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify({ ...body, command_key: command.current.key }),
      });
      // Planning entry URLs may pin the original run_id. A new operation must
      // show the active run rather than refreshing that now-historical URL.
      navigate('/plans/' + data.plan.plan_id);
      refresh();
    } catch (reason) {
      const preserved=preservedRevisionNotice(reason);
      if(preserved)setNotice(preserved);
      else setError(reason instanceof ApiFailure ? `${reason.message}(Trace ID ${reason.envelope.trace_id})` : 'Submission is unconfirmed. Refresh the record or submit the same action again.');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(null); }
  }
  return <section className="panel planning-change"><h2>Adjust plan and recheck</h2>
    <p>Compare and choose whether to adopt the new plan after generation. Rechecking keeps the current itinerary.</p>
    <div className="modify-paths"><h3>Change requirements or profile</h3><p>Review and reconfirm changes to group size, dates, budget, required conditions or available equipment first.</p><Link className="text-link" to={tripUpdatePath(data.plan.plan_id)}>Edit and reconfirm requirements and profile ↗</Link></div>
    <h3>Revise itinerary arrangements</h3><p>Keep confirmed requirements and generate a proposed plan to compare. To update check evidence only, use Recheck below.</p>
    {reviewSource&&<div className="review-revision-source"><h3>Reviewer requested revision</h3><blockquote>{reviewSource.reason}</blockquote><button type="button" className="secondary-button" disabled={!!busy} onClick={useReview}>Use this reviewer feedback</button>{sourceReviewId&&<p>Original review linked. Review the feedback; the model runs only after selecting Generate proposed plan.</p>}</div>}
    <label htmlFor="revision-choice">Revision goal</label><select id="revision-choice" value={choice} disabled={!!busy} onChange={event => onChoiceChange(event.target.value)}>
      <option value="change campsite">Change campsite</option><option value="cheaper campsite">Find a campsite with lower fees</option><option value="custom">Enter other revision feedback</option>
    </select>
    {choice==='cheaper campsite'&&<p className="mode-notice">Keep the budget {data.confirmed_context?.requirements.budget_cents==null?'(amount loading)':`AUD ${(data.confirmed_context.requirements.budget_cents/100).toFixed(2)}`}, Try to find a cheaper campsite. The total may still exceed the budget.</p>}
    {choice === 'custom' && <><label htmlFor="revision-feedback">Revision feedback</label><textarea id="revision-feedback" value={feedback} maxLength={4000} disabled={!!busy} onChange={event => setFeedback(event.target.value)} /></>}
    <div className="plan-actions"><button className="primary-button" disabled={!!busy || !data.revision_available} onClick={() => void submit('revise')}>{busy==='revise' ? 'Generating proposed plan…' : choice==='cheaper campsite'?'Find a cheaper campsite':'Generate proposed plan'}</button>
      <button className="secondary-button" disabled={!!busy || !data.reassessment_available} onClick={() => void submit('reassess')}>{busy==='reassess'?'Starting checks…':'Keep itinerary and recheck'}</button></div>
    {notice && <p className="mode-notice" role="status">{notice}</p>}
    {error && <p className="error-box" role="alert">{error}</p>}
  </section>;
}

export function RetryPlanning({ data, refresh }: { data: PlanDetail; refresh: () => void }) {
  const { session, reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<{ runId: string; revision: number; key: string } | null>(null);
  const run = data.run;
  if (!run || run.status !== 'FAILED' || !run.is_active || data.trip_series?.is_current===false) return null;
  const guidance=failureGuidance(data)!;
  if (['INPUT_INVALID','REQUEST_NOT_CONFIRMED'].includes(run.error?.code??'')) return <><p>These requirements need review. Continuing directly will not update confirmed information.</p><Link className="text-link" to={tripUpdatePath(data.plan.plan_id)}>Review and reconfirm this trip requirements ↗</Link></>;
  async function retry() {
    if (!run || !session || busy || !guidance.canRetry) return;
    if (command.current?.runId !== run.run_id || command.current.revision !== run.revision) {
      command.current = { runId: run.run_id, revision: run.revision, key: crypto.randomUUID() };
    }
    setBusy(true); setError('');
    try {
      await privateApi('/runs/' + run.run_id + '/retry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CampMate-Client': '1', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify({ command_key: command.current.key, expected_run_revision: run.revision }),
      });
      refresh();
    } catch (reason) {
      setError(reason instanceof ApiFailure ? `${reason.message}(Trace ID ${reason.envelope.trace_id})` : 'Submission is unconfirmed. Refresh the record or submit the same retry again.');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  return <div className="planning-retry">
    {guidance.canRetry ? <><p>{guidance.retryDescription}</p><button className="primary-button" disabled={busy} onClick={retry}>{busy ? 'Submitting…' : guidance.retryLabel}</button></> : <><p className="muted">This run cannot resume directly. Existing records are retained. Contact the maintainer to investigate.</p>{data.retry_unavailable_reason&&<details><summary>Why this cannot continue</summary><p>{data.retry_unavailable_reason}</p></details>}</>}
    {error && <p className="error-box" role="alert">{error}</p>}
  </div>;
}
