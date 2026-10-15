import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { ApiFailure, loadStatus, previewRequest, type ApiError, type Meta, type PreviewResult, type Ready } from './api';
import { FinalPage } from './finals';
import { ReviewQueue, ReviewPage } from './reviews';
import { AccountControl, LoginPage, Protected, SessionProvider, useSession } from './session';
import { ProfilePage } from './profile';
import { RequestDetail, RequestsPage } from './requests';
import { PlansPage, PlanPage } from './plans';

const DISCLAIMER = '本项目使用模拟数据，仅供演示，请勿据此安排真实出行。';
type Status = { meta: Meta; ready: Ready };

function Mountain({ small = false }: { small?: boolean }) {
  return <svg viewBox="0 0 240 150" fill="none" aria-hidden="true" className={small ? 'brand-icon' : 'mountain'}>
    <path d="M9 134L83 24l40 60 27-35 82 85H9Z" fill="currentColor" opacity=".12" />
    <path d="M22 132L83 40l40 58 28-35 68 69M58 77l25-37 20 30-19-8-26 15Z" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" />
    <path d="M160 132V99m-16 20 16-24 16 24m-30-7 14-23 14 23" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
  </svg>;
}

export function App() {
  return <SessionProvider><AppContent /></SessionProvider>;
}

function AppContent() {
  const { session } = useSession();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setStatus(null); setError(null);
    loadStatus(controller.signal).then(setStatus).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '连接失败');
    });
    return () => controller.abort();
  }, [refresh]);

  return <div className="app-shell">
    <aside className="sidebar">
      <Link className="brand" to="/"><Mountain small /><span>CampMate<span className="brand-ai">AI</span></span></Link>
      <div className="sidebar-caption">YOUR CAMPING COMPANION</div>
      <nav aria-label="主导航">
        <NavLink to="/" end><span>◫</span>首页</NavLink>
        <NavLink to="/request"><span>↗</span>露营请求</NavLink>
        <NavLink to="/profile"><span>◎</span>露营资料</NavLink>
        <NavLink to="/plans"><span>≋</span>方案与历史</NavLink>
        {session?.user.role === 'FOUNDER' && <NavLink to="/review"><span>◇</span>人工审核</NavLink>}
      </nav>
      <div className="sidebar-note"><span className="eyebrow">PLAN YOUR NEXT ESCAPE</span><p>从清晰的需求开始，<br />让每一步都有依据。</p></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>你的露营伙伴</span><div className="topbar-right"><span className={`connection ${status?.ready.status === 'ready' ? 'connected' : ''}`}><i />{error ? '服务未连接' : status ? (status.ready.status === 'ready' ? '服务可用' : '服务暂不可用') : '正在连接…'}</span><AccountControl /></div></header>
      <main>
        <>{status?.meta.agent_configuration_error && <p className="mode-notice" role="alert">规划服务暂不可用，请稍后重试。</p>}</>
        {error && <div className="error-box" role="alert"><strong>无法连接服务</strong><p>{error}。请稍后刷新重试。</p><button onClick={() => setRefresh(value => value + 1)}>重新连接</button></div>}
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/request" element={<Protected role="CAMPER"><RequestsPage /></Protected>} />
          <Route path="/request/:requestId" element={<Protected role="CAMPER"><RequestDetail /></Protected>} />
          <Route path="/dev/request-preview" element={<RequestPreview enabled={status?.meta.features.request_preview === true && status.ready.status === 'ready'} />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/profile" element={<Protected role="CAMPER"><ProfilePage demoAvailable={['deterministic_demo','agent'].includes(status?.meta.execution_mode ?? '') && ['2.0.0','2.1.0'].includes(status?.meta.dataset_version ?? '')} datasetVersion={status?.meta.dataset_version} /></Protected>} />
          <Route path="/plans" element={<Protected role="CAMPER"><PlansPage /></Protected>} />
          <Route path="/plans/:planId/finals/:finalId" element={<Protected role="CAMPER"><FinalPage /></Protected>} />
          <Route path="/plans/:planId" element={<Protected role="CAMPER"><PlanPage /></Protected>} />
          <Route path="/review/:planId" element={<Protected role="FOUNDER"><ReviewPage /></Protected>} />
          <Route path="/review" element={<Protected role="FOUNDER"><ReviewQueue /></Protected>} />
          <Route path="*" element={<Upcoming title="页面不存在" description="请使用左侧导航返回首页。" />} />
        </Routes>
      </main>
      <footer><span className="tag">演示数据</span><p>{DISCLAIMER}</p><span>CampMate AI · ELEC5620</span></footer>
    </div>
  </div>;
}

function Overview() {
  return <>
    <section className="hero"><div><span className="eyebrow">A LITTLE LESS GUESSWORK</span><h1>一次露营，<br />从一份清晰的计划开始。</h1><p>规划行程，准备装备，<br className="desktop-break" />让下一次出发更从容。</p><Link className="primary-button" to="/request">开始规划 <span>↗</span></Link></div><div className="hero-art"><span>EXPLORE WITH CLARITY</span><Mountain /><div>PLAN · CHECK · REVIEW</div></div></section>
    <section className="section-heading"><div><span className="eyebrow">THE JOURNEY</span><h2>为下一次出发做好准备</h2></div></section>
    <div className="journey">{[['01', '说说你的计划', '目的地、日期与预算'], ['02', '找到合适的营地', '比较营地，查看行程'], ['03', '准备好再出发', '核对装备、费用与安全'], ['04', '保存你的方案', '保留方案，随时回看']].map(([number, title, description]) => <div key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{description}</p></div>)}</div>
    <div className="bottom-grid"><section className="panel"><span className="eyebrow">YOUR GROUP</span><h2>完善露营资料</h2><p>告诉我们同行人数、已有装备和交通安排。</p><Link className="text-link" to="/profile">编辑资料 ↗</Link></section><section className="panel next-panel"><span className="eyebrow">YOUR PLANS</span><h2>继续你的计划</h2><p>查看已有方案，调整行程或回看保存的安排。</p><Link className="text-link" to="/plans">查看我的方案 ↗</Link></section></div>
  </>;
}

function RequestPreview({ enabled }: { enabled: boolean }) {
  const [rawText, setRawText] = useState('');
  const [destination, setDestination] = useState('');
  const [startDate, setStartDate] = useState('');
  const [nights, setNights] = useState('');
  const [budget, setBudget] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);

  function invalidate() { setResult(null); setError(null); setNetworkError(null); }
  async function submit(event: FormEvent) {
    event.preventDefault(); invalidate(); setBusy(true);
    try {
      // Input AUD uses two decimal digits. Convert the decimal text without a float multiply.
      const parts = budget.split('.');
      const cents = budget === '' ? null : Number(parts[0]) * 100 + Number((parts[1] ?? '').padEnd(2, '0'));
      setResult(await previewRequest(rawText, { destination: destination.trim() || null, start_date: startDate || null, duration_nights: nights === '' ? null : Number(nights), budget_cents: cents }));
    } catch (reason) {
      if (reason instanceof ApiFailure) setError(reason.envelope);
      else setNetworkError('未取得预览结果，请检查服务连接后重试。');
    } finally { setBusy(false); }
  }

  return <><div className="page-heading"><span className="eyebrow">REQUEST / CONTRACT PREVIEW</span><h1>先把需求说清楚。</h1><p>测试前后端字段交接。此预览不确认请求，也不开始规划。</p></div><div className="preview-grid"><section className="panel"><div className="panel-title"><h2>露营请求</h2><span className="tag">STUB</span></div><p className="muted">Stub 不解析自然语言；下面的明确字段会原样回显。无需输入真实个人信息。</p><form onSubmit={submit}><label htmlFor="raw-text">你的露营想法</label><textarea id="raw-text" value={rawText} maxLength={8000} required placeholder="例如：想和朋友去露营两晚，先看看需求摘要。" onChange={event => { setRawText(event.target.value); invalidate(); }} disabled={busy} /><div className="form-grid"><div><label htmlFor="destination">明确目的地（可留空）</label><input id="destination" value={destination} onChange={event => { setDestination(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="start-date">开始日期（可留空）</label><input id="start-date" type="date" value={startDate} onChange={event => { setStartDate(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="nights">晚数（可留空）</label><input id="nights" type="number" min="1" step="1" value={nights} onChange={event => { setNights(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="budget">小组预算 AUD（可留空）</label><input id="budget" type="text" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" value={budget} placeholder="250.00" onChange={event => { setBudget(event.target.value); invalidate(); }} disabled={busy} /></div></div><button className="primary-button" disabled={!enabled || busy || !rawText.trim()}>{busy ? '正在读取预览…' : '预览字段交接'} <span>↗</span></button>{!enabled && <p className="muted">连接到已就绪的 stub 环境后可预览。</p>}</form></section><section className="panel result-panel" aria-live="polite"><span className="eyebrow">STRUCTURED RESULT</span><h2>字段回显</h2>{error && <div className="error-box" role="alert"><strong>{error.error.code}</strong><p>{error.error.message}</p><ul>{error.error.field_errors.map((item, index) => <li key={index}>{item.field}：{item.message}</li>)}</ul><small>Trace: {error.trace_id}</small></div>}{networkError && <p className="error-box" role="alert">{networkError}</p>}{result ? <><div className="result-mode">{result.execution_mode.toUpperCase()} · Schema {result.schema_version}</div><dl>{[['目的地', result.extracted_requirements.destination], ['开始日期', result.extracted_requirements.start_date], ['晚数', result.extracted_requirements.duration_nights], ['预算 AUD', result.extracted_requirements.budget_cents === null ? null : (result.extracted_requirements.budget_cents / 100).toFixed(2)]].map(([label, value]) => <div key={String(label)}><dt>{label}</dt><dd>{value ?? '未提供'}</dd></div>)}</dl>{result.clarifications.length > 0 && <div className="clarifications"><h3>待明确的字段</h3>{result.clarifications.map(item => <p key={item.field}>○ {item.question}</p>)}</div>}<p className="muted">{result.uncertainties.join(' ')}</p></> : <div className="empty-state"><span>⌁</span><p>填写请求后，<br />在这里查看明确字段与缺失提示。</p></div>}<Link className="text-link" to="/request">前往露营请求进行确认与规划 ↗</Link></section></div></>;
}

function Upcoming({ title, description }: { title: string; description: string }) {
  return <><div className="page-heading"><span className="eyebrow">PAGE NOT FOUND</span><h1>{title}</h1></div><section className="panel upcoming"><Mountain /><h2>没有找到这个页面</h2><p>{description}</p><Link to="/request" className="text-link">开始规划 ↗</Link></section></>;
}
