import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import type { PlanDetail } from './plans';
import { privateApi, useSession } from './session';

export function ChangePlanning({ data, refresh }: { data: PlanDetail; refresh: () => void }) {
  const { session, reload } = useSession();
  const navigate = useNavigate();
  const [choice, setChoice] = useState('change campsite');
  const [feedback, setFeedback] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<{ payload: string; key: string } | null>(null);
  if (!data.run?.is_active || (!data.revision_available && !data.reassessment_available)) return null;
  async function submit(operation: 'revise' | 'reassess') {
    if (!session || !data.run || busy || data.current_version_revision == null) return;
    const text = choice === 'custom' ? feedback.trim() : choice;
    if (operation === 'revise' && !text) { setError('请填写修改意见。'); return; }
    const body = { expected_current_version_id: data.plan.current_version_id,
      expected_active_run_id: data.run.run_id, expected_version_revision: data.current_version_revision,
      expected_run_revision: data.run.revision, ...(operation === 'revise' ? { feedback: text } : {}) };
    const payload = JSON.stringify({ operation, ...body });
    if (command.current?.payload !== payload) command.current = { payload, key: crypto.randomUUID() };
    setBusy(true); setError('');
    try {
      await privateApi('/plans/' + data.plan.plan_id + '/' + operation, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CampMate-Client': '1', 'X-CSRF-Token': session.csrf_token },
        body: JSON.stringify({ ...body, command_key: command.current.key }),
      });
      // Planning entry URLs may pin the original run_id. A new operation must
      // show the active run rather than refreshing that now-historical URL.
      navigate('/plans/' + data.plan.plan_id);
      refresh();
    } catch (reason) {
      setError(reason instanceof ApiFailure ? `${reason.message}（追踪号 ${reason.envelope.trace_id}）` : '提交结果尚未确认。请刷新记录，或再次提交同一次操作。');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  return <section className="panel planning-change"><h2>调整方案与重新检查</h2>
    <p>修改方案会生成新版本。重新评估会保留当前行程，用最新证据重新检查装备、费用和安全。两种操作都会开启新运行，原有审核和最终方案保留在历史记录中。</p>
    <p className="muted">本次沿用已确认的需求和露营资料快照。若人数、日期、预算或资料改变，请先重新提交并确认需求。</p>
    <label htmlFor="revision-choice">修改目标</label><select id="revision-choice" value={choice} disabled={busy} onChange={event => setChoice(event.target.value)}>
      <option value="change campsite">更换营地</option><option value="cheaper campsite">寻找费用更低的营地</option><option value="custom">填写其他修改意见</option>
    </select>
    {choice === 'custom' && <><label htmlFor="revision-feedback">修改意见</label><textarea id="revision-feedback" value={feedback} maxLength={4000} disabled={busy} onChange={event => setFeedback(event.target.value)} /></>}
    <div className="plan-actions"><button className="primary-button" disabled={busy || !data.revision_available} onClick={() => void submit('revise')}>{busy ? '正在提交…' : '修改方案'}</button>
      <button className="secondary-button" disabled={busy || !data.reassessment_available} onClick={() => void submit('reassess')}>重新评估</button></div>
    {error && <p className="error-box" role="alert">{error}</p>}
  </section>;
}

export function RetryPlanning({ data, refresh }: { data: PlanDetail; refresh: () => void }) {
  const { session, reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<{ runId: string; revision: number; key: string } | null>(null);
  const run = data.run;
  if (!run || run.status !== 'FAILED') return null;
  if (run.error?.code === 'INPUT_INVALID') return <p className="muted">当前输入或修改意见需要调整。重试不会修改已登记的要求，请使用“调整需求并重新确认”入口。</p>;
  async function retry() {
    if (!run || !session || busy || !data.retry_available) return;
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
    {data.retry_available ? <><p>重试会保留已保存的版本与评估，从中断位置继续；不会解除安全阻止条件。</p><button className="primary-button" disabled={busy} onClick={retry}>{busy ? '正在提交重试…' : '重试规划'}</button></> : <p className="muted">{data.retry_unavailable_reason ?? '当前运行不能重试。'}</p>}
    {error && <p className="error-box" role="alert">{error}</p>}
  </div>;
}
