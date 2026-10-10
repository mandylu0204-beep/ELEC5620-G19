import { useRef, useState } from 'react';
import { ApiFailure } from './api';
import type { PlanDetail } from './plans';
import { privateApi, useSession } from './session';

export function RetryPlanning({ data, refresh }: { data: PlanDetail; refresh: () => void }) {
  const { session, reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const command = useRef<{ runId: string; revision: number; key: string } | null>(null);
  const run = data.run;
  if (!run || run.status !== 'FAILED') return null;
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
