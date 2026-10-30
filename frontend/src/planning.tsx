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
    if (operation === 'revise' && !text) { setError('请填写修改意见。'); return; }
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
      else setError(reason instanceof ApiFailure ? `${reason.message}（追踪号 ${reason.envelope.trace_id}）` : '提交结果尚未确认。请刷新记录，或再次提交同一次操作。');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(null); }
  }
  return <section className="panel planning-change"><h2>调整方案与重新检查</h2>
    <p>新方案生成后，可对比并选择是否采用。重新检查会保留当前行程。</p>
    <div className="modify-paths"><h3>修改需求或资料</h3><p>人数、日期、预算、必须条件或已有装备有变化时，先核对并重新确认。</p><Link className="text-link" to={tripUpdatePath(data.plan.plan_id)}>修改需求与资料并重新确认 ↗</Link></div>
    <h3>修改行程安排</h3><p>保留已确认需求，生成待选方案后对比选择；若只更新检查依据，请使用下方重新检查。</p>
    {reviewSource&&<div className="review-revision-source"><h3>审核员要求修改</h3><blockquote>{reviewSource.reason}</blockquote><button type="button" className="secondary-button" disabled={!!busy} onClick={useReview}>采用这条审核意见</button>{sourceReviewId&&<p>已关联原审核记录；核对修改意见后，点击生成待选方案才会执行模型。</p>}</div>}
    <label htmlFor="revision-choice">修改目标</label><select id="revision-choice" value={choice} disabled={!!busy} onChange={event => onChoiceChange(event.target.value)}>
      <option value="change campsite">更换营地</option><option value="cheaper campsite">寻找费用更低的营地</option><option value="custom">填写其他修改意见</option>
    </select>
    {choice==='cheaper campsite'&&<p className="mode-notice">保留预算 {data.confirmed_context?.requirements.budget_cents==null?'（金额待读取）':`AUD ${(data.confirmed_context.requirements.budget_cents/100).toFixed(2)}`}，尝试寻找更便宜的营地。总费用仍可能超出预算。</p>}
    {choice === 'custom' && <><label htmlFor="revision-feedback">修改意见</label><textarea id="revision-feedback" value={feedback} maxLength={4000} disabled={!!busy} onChange={event => setFeedback(event.target.value)} /></>}
    <div className="plan-actions"><button className="primary-button" disabled={!!busy || !data.revision_available} onClick={() => void submit('revise')}>{busy==='revise' ? '正在生成待选方案…' : choice==='cheaper campsite'?'寻找更便宜的营地':'生成待选方案'}</button>
      <button className="secondary-button" disabled={!!busy || !data.reassessment_available} onClick={() => void submit('reassess')}>{busy==='reassess'?'正在启动检查…':'保留行程，重新检查'}</button></div>
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
  if (['INPUT_INVALID','REQUEST_NOT_CONFIRMED'].includes(run.error?.code??'')) return <><p>本次要求需要重新核对，直接继续不会更新已确认的资料。</p><Link className="text-link" to={tripUpdatePath(data.plan.plan_id)}>调整本次需求并重新确认 ↗</Link></>;
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
      setError(reason instanceof ApiFailure ? `${reason.message}（追踪号 ${reason.envelope.trace_id}）` : '提交结果尚未确认。请刷新记录查看状态，或再次提交同一次重试。');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  return <div className="planning-retry">
    {guidance.canRetry ? <><p>{guidance.retryDescription}</p><button className="primary-button" disabled={busy} onClick={retry}>{busy ? '正在提交…' : guidance.retryLabel}</button></> : <><p className="muted">这次执行暂不能直接继续。已有记录会保留，请联系项目负责人核对原因。</p>{data.retry_unavailable_reason&&<details><summary>查看无法继续的原因</summary><p>{data.retry_unavailable_reason}</p></details>}</>}
    {error && <p className="error-box" role="alert">{error}</p>}
  </div>;
}
