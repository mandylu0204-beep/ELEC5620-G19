import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { ApiFailure, loadStatus, previewRequest, type ApiError, type Meta, type PreviewResult, type Ready } from './api';
import { FinalPage } from './finals';
import { ReviewQueue, ReviewPage } from './reviews';
import { AccountControl, LoginPage, Protected, SessionProvider, useSession } from './session';
import { ProfilePage } from './profile';
import { RequestDetail, RequestsPage } from './requests';
import { PlansPage, PlanPage } from './plans';

const DISCLAIMER = 'This prototype uses synthetic demonstration data. It must not be used for real trip planning, campsite availability, or safety decisions.';
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
        <NavLink to="/" end><span>◫</span>项目概览</NavLink>
        <NavLink to="/request"><span>↗</span>露营请求</NavLink>
        <NavLink to="/profile"><span>◎</span>露营资料</NavLink>
        <NavLink to="/plans"><span>≋</span>方案与历史</NavLink>
        {session?.user.role === 'FOUNDER' && <NavLink to="/review"><span>◇</span>人工审核</NavLink>}
      </nav>
      <div className="sidebar-note"><span className="eyebrow">STAGE 2 / FOUNDATION</span><p>从清晰的需求开始，<br />让每一步都有依据。</p><span className="tag">Synthetic demo only</span></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>小组项目 · 开发预览</span><div className="topbar-right"><span className={`connection ${status?.ready.status === 'ready' ? 'connected' : ''}`}><i />{error ? '服务未连接' : status ? (status.ready.status === 'ready' ? '开发基础可用' : '依赖未就绪') : '正在连接…'}</span><AccountControl /></div></header>
      <main>
        <div className="mode-notice"><strong>{status?.meta.execution_mode.toUpperCase() ?? '开发环境'}</strong><span>{status?.meta.agent_configuration_error ? '当前数据与运行配置未就绪，暂不能开始规划。已保存的资料和方案仍可查看。' : status?.meta.features.planning ? '确认需求后可开始规划，查看保存进度；可恢复的失败可在方案页重试。' : '资料、需求确认、方案展示、人工审核与最终化已接入。规划流程尚未启用。'}</span></div>
        {error && <div className="error-box" role="alert"><strong>无法连接后端</strong><p>{error}。请检查启动终端。</p><button onClick={() => setRefresh(value => value + 1)}>重新连接</button></div>}
        <Routes>
          <Route path="/" element={<Overview status={status} />} />
          <Route path="/request" element={<Protected role="CAMPER"><RequestsPage /></Protected>} />
          <Route path="/request/:requestId" element={<Protected role="CAMPER"><RequestDetail /></Protected>} />
          <Route path="/dev/request-preview" element={<RequestPreview enabled={status?.meta.features.request_preview === true && status.ready.status === 'ready'} />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/profile" element={<Protected role="CAMPER"><ProfilePage demoAvailable={status?.meta.execution_mode === 'deterministic_demo' && status.meta.dataset_version === '2.0.0'} datasetVersion={status?.meta.dataset_version} /></Protected>} />
          <Route path="/plans" element={<Protected role="CAMPER"><PlansPage /></Protected>} />
          <Route path="/plans/:planId/finals/:finalId" element={<Protected role="CAMPER"><FinalPage /></Protected>} />
          <Route path="/plans/:planId" element={<Protected role="CAMPER"><PlanPage /></Protected>} />
          <Route path="/review/:planId" element={<Protected role="FOUNDER"><ReviewPage /></Protected>} />
          <Route path="/review" element={<Protected role="FOUNDER"><ReviewQueue /></Protected>} />
          <Route path="*" element={<Upcoming title="页面不存在" description="请使用左侧导航返回项目概览。" />} />
        </Routes>
      </main>
      <footer><span className="tag">SYNTHETIC</span><p>{status?.meta.disclaimer ?? DISCLAIMER}</p><span>CampMate AI · ELEC5620</span></footer>
    </div>
  </div>;
}

function Overview({ status }: { status: Status | null }) {
  const checks = status?.ready.checks;
  return <>
    <section className="hero"><div><span className="eyebrow">A LITTLE LESS GUESSWORK</span><h1>一次露营，<br />从一份清晰的计划开始。</h1><p>确认需求、规划行程、检查装备与安全，<br className="desktop-break" />把每一次调整保留为可追溯的版本。</p><Link className="primary-button" to="/request">填写露营请求 <span>↗</span></Link></div><div className="hero-art"><span>EXPLORE WITH CLARITY</span><Mountain /><div>PLAN · CHECK · REVIEW</div></div></section>
    <section className="stats" aria-label="环境状态">
      <div><span>运行模式</span><strong>{status?.meta.execution_mode ?? '—'}</strong><small>{status?.meta.execution_mode === 'deterministic_demo' ? '规则演示，使用登记的合成输入' : status?.meta.execution_mode === 'agent' ? '模型模式需配置对应服务' : '字段预览，规划未启用'}</small></div>
      <div><span>演示时钟</span><strong>{status?.meta.demo_today ?? '—'}</strong><small>与实际系统日期分开</small></div>
      <div><span>数据来源</span><strong>{status?.meta.dataset_version ? `Synthetic ${status.meta.dataset_version}` : '—'}</strong><small>{checks ? (checks.dataset_context_valid ? '数据版本与运行输入可验证' : '数据包或场景配置未就绪') : '正在检查源文件…'}</small></div>
    </section>
    <section className="section-heading"><div><span className="eyebrow">THE JOURNEY</span><h2>从请求到最终方案</h2></div><span>{status?.meta.features.planning ? '按已保存结果继续下一步' : '规划入口等待运行配置就绪'}</span></section>
    <div className="journey">{[['01', '确认需求', '资料 · 澄清 · 摘要确认'], ['02', '生成与检查', '推荐 · 行程 · 装备 · 安全'], ['03', '审核与调整', '人工审核 · 修订 · 重新评估'], ['04', '保存与交付', '最终化守卫 · 历史回读']].map(([number, title, description]) => <div key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{description}</p><span className="pending-label">{number==='01'?'可填写与确认':number==='02'?(status?.meta.features.planning?'可执行':'未启用'):number==='03'?'审核可用':'通过检查后可保存'}</span></div>)}</div>
    <div className="bottom-grid"><section className="panel"><span className="eyebrow">FOUNDATION CHECKS</span><h2>当前可验证的基础</h2><ul className="check-list">{[['业务源文件', checks?.dataset_readable], ['SQLite 数据库迁移', checks?.database_migrated], ['配置的 Agent 入口', checks?.configured_agent_available]].map(([title, value]) => <li key={String(title)}><span>{title}</span><span className={value === true ? 'check-ok' : 'check-wait'}>{value === undefined ? '检查中' : value ? '可用' : '未就绪'}</span></li>)}</ul><p className="muted">来源可读不代表业务数据已通过验收。开发预览见 <Link className="text-link" to="/dev/request-preview">字段交接工具</Link>。</p></section><section className="panel next-panel"><span className="eyebrow">NEXT MILESTONE</span><h2>验证四个演示场景</h2><p>已保存的规划阶段与产物可以查看。Founder 可以审核当前证据。Camper 可以保存通过检查的最终快照。已接通方案修订与重新评估。v2 规则流程已接入，四个场景可独立启动。模型版与最终提交验收仍在推进。</p><div className="chips"><span>v2 规则已接入</span><span>修订与重新评估</span><span>四个联调场景</span></div></section></div>
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
  return <><div className="page-heading"><span className="eyebrow">COMING NEXT</span><h1>{title}</h1></div><section className="panel upcoming"><Mountain /><h2>页面位置已预留</h2><p>{description}</p><Link to="/request" className="text-link">先查看当前可用的请求预览 ↗</Link></section></>;
}
