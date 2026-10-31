import {RequirementHelpQueue,RequirementHelpReview} from './requirement_help';
import { useEffect, useState, type FormEvent } from 'react';
import { Link, NavLink, Route, Routes } from 'react-router-dom';
import { ApiFailure, loadStatus, previewRequest, type ApiError, type Meta, type PreviewResult, type Ready } from './api';
import { FinalPage } from './finals';
import { ReviewQueue, ReviewPage } from './reviews';
import { AccountControl, LoginPage, Protected, SessionProvider, useSession } from './session';
import { ProfilePage } from './profile';
import { RequestDetail, RequestsPage } from './requests';
import { PlansPage, PlanPage } from './plans';
import { RegisterPage } from './register';
import { TripUpdateEntry } from './replan';

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
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Connection failed');
    });
    return () => controller.abort();
  }, [refresh]);

  return <div className="app-shell">
    <aside className="sidebar">
      <Link className="brand" to="/"><Mountain small /><span>CampMate<span className="brand-ai">AI</span></span></Link>
      <div className="sidebar-caption">Your camping companion</div>
      <nav aria-label="Main navigation">
        <NavLink to="/" end><span>◫</span>Home</NavLink>
        {session?.user.role !== 'FOUNDER' && <>
          <NavLink to="/profile"><span>◎</span>Camping profile</NavLink>
          <NavLink to="/request"><span>↗</span>Camping request</NavLink>
          <NavLink to="/plans"><span>≋</span>Plans and history</NavLink>
        </>}
        {session?.user.role === 'FOUNDER' && <><NavLink to="/review"><span>◇</span>Human review</NavLink><NavLink to="/requirement-help"><span>?</span>Request assistance</NavLink></>}
      </nav>
      <div className="sidebar-note"><span className="eyebrow">Plan your next trip</span><p>Start with clear requirements,<br />give every step a sound basis.</p></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>Your camping companion</span><div className="topbar-right"><AccountControl /></div></header>
      <main>
        <>{status?.meta.agent_configuration_error && <p className="mode-notice" role="alert">Planning is temporarily unavailable. Please try again later.</p>}</>
        {error && <div className="error-box" role="alert"><strong>Cannot connect to the service</strong><p>{error}.Refresh and try again later.</p><button onClick={() => setRefresh(value => value + 1)}>Reconnect</button></div>}
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/request" element={<Protected role="CAMPER"><RequestsPage /></Protected>} />
          <Route path="/request/:requestId" element={<Protected role="CAMPER"><RequestDetail /></Protected>} />
          <Route path="/dev/request-preview" element={<RequestPreview enabled={status?.meta.features.request_preview === true && status.ready.status === 'ready'} />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/profile" element={<Protected role="CAMPER"><ProfilePage datasetVersion={status?.meta.dataset_version} /></Protected>} />
          <Route path="/plans" element={<Protected role="CAMPER"><PlansPage /></Protected>} />
          <Route path="/plans/:planId/update" element={<Protected role="CAMPER"><TripUpdateEntry /></Protected>} />
          <Route path="/plans/:planId/finals/:finalId" element={<Protected role="CAMPER"><FinalPage /></Protected>} />
          <Route path="/plans/:planId" element={<Protected role="CAMPER"><PlanPage /></Protected>} />
          <Route path="/review/:planId" element={<Protected role="FOUNDER"><ReviewPage /></Protected>} />
          <Route path="/requirement-help" element={<Protected role="FOUNDER"><RequirementHelpQueue/></Protected>}/>
          <Route path="/requirement-help/:taskId" element={<Protected role="FOUNDER"><RequirementHelpReview/></Protected>}/>
          <Route path="/review" element={<Protected role="FOUNDER"><ReviewQueue /></Protected>} />
          <Route path="*" element={<Upcoming title="Page not found" description="Use the navigation to return home." />} />
        </Routes>
      </main>
      <footer><p>Plan your next trip and keep your arrangements together.</p><span>CampMate AI · ELEC5620</span></footer>
    </div>
  </div>;
}

function Overview() {
  return <>
    <section className="hero"><div><span className="eyebrow">Prepare with confidence</span><h1>A camping trip,<br />starting with a clear plan.</h1><p>Plan your itinerary and prepare your equipment,<br className="desktop-break" />so you can set off with confidence.</p><Link className="primary-button" to="/profile">Start planning <span>↗</span></Link></div><div className="hero-art"><span>Plan clearly, travel confidently</span><Mountain /><div>Plan · Check · Review</div></div></section>
    <section className="section-heading"><div><span className="eyebrow">Trip preparation</span><h2>Get ready for your next trip</h2></div></section>
    <div className="journey">{[['01', 'Describe your plans', 'Destination, dates and budget'], ['02', 'Find a suitable campsite', 'Compare campsites and view your itinerary'], ['03', 'Prepare before departure', 'Review equipment, costs and safety'], ['04', 'Save your plan', 'Keep your plan for later']].map(([number, title, description]) => <div key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{description}</p></div>)}</div>
    <div className="bottom-grid"><section className="panel"><span className="eyebrow">Travel group</span><h2>Complete your camping profile</h2><p>Tell us about your group, available equipment and transport.</p><Link className="text-link" to="/profile">Edit profile ↗</Link></section><section className="panel next-panel"><span className="eyebrow">Existing plans</span><h2>Continue your plan</h2><p>View existing plans, adjust an itinerary or revisit saved arrangements.</p><Link className="text-link" to="/plans">View my plans ↗</Link></section></div>
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
      else setNetworkError('No preview was received. Check the connection and try again.');
    } finally { setBusy(false); }
  }

  return <><div className="page-heading"><span className="eyebrow">Request field preview</span><h1>Tell us about your ideal camping trip.</h1><p>Test the frontend/backend field handoff. This preview does not confirm a request or start planning.</p></div><div className="preview-grid"><section className="panel"><div className="panel-title"><h2>Camping request</h2><span className="tag">STUB</span></div><p className="muted">Stub No natural-language interpretation is performed. Explicit fields are echoed below. Do not enter real personal information.</p><form onSubmit={submit}><label htmlFor="raw-text">Your camping ideas</label><textarea id="raw-text" value={rawText} maxLength={8000} required placeholder="For example: a two-night camping trip with friends; preview the request summary first." onChange={event => { setRawText(event.target.value); invalidate(); }} disabled={busy} /><div className="form-grid"><div><label htmlFor="destination">Explicit destination (optional)</label><input id="destination" value={destination} onChange={event => { setDestination(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="start-date">Start date (optional)</label><input id="start-date" type="date" value={startDate} onChange={event => { setStartDate(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="nights">Number of nights (optional)</label><input id="nights" type="number" min="1" step="1" value={nights} onChange={event => { setNights(event.target.value); invalidate(); }} disabled={busy} /></div><div><label htmlFor="budget">Group budget AUD(optional)</label><input id="budget" type="text" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" value={budget} placeholder="250.00" onChange={event => { setBudget(event.target.value); invalidate(); }} disabled={busy} /></div></div><button className="primary-button" disabled={!enabled || busy || !rawText.trim()}>{busy ? 'Loading preview…' : 'Preview field handoff'} <span>↗</span></button>{!enabled && <p className="muted">Connect to a ready  stub  environment to preview.</p>}</form></section><section className="panel result-panel" aria-live="polite"><span className="eyebrow">Field summary</span><h2>Field summary</h2>{error && <div className="error-box" role="alert"><strong>{error.error.code}</strong><p>{error.error.message}</p><ul>{error.error.field_errors.map((item, index) => <li key={index}>{item.field}: {item.message}</li>)}</ul><small>Trace: {error.trace_id}</small></div>}{networkError && <p className="error-box" role="alert">{networkError}</p>}{result ? <><div className="result-mode">{result.execution_mode.toUpperCase()} · Schema {result.schema_version}</div><dl>{[['Destination', result.extracted_requirements.destination], ['Start date', result.extracted_requirements.start_date], ['Number of nights', result.extracted_requirements.duration_nights], ['Budget AUD', result.extracted_requirements.budget_cents === null ? null : (result.extracted_requirements.budget_cents / 100).toFixed(2)]].map(([label, value]) => <div key={String(label)}><dt>{label}</dt><dd>{value ?? 'Not provided'}</dd></div>)}</dl>{result.clarifications.length > 0 && <div className="clarifications"><h3>Fields to clarify</h3>{result.clarifications.map(item => <p key={item.field}>○ {item.question}</p>)}</div>}<p className="muted">{result.uncertainties.join(' ')}</p></> : <div className="empty-state"><span>⌁</span><p>After entering a request,<br />view explicit fields and missing information here.</p></div>}<Link className="text-link" to="/request">Open the camping request to confirm and plan ↗</Link></section></div></>;
}

function Upcoming({ title, description }: { title: string; description: string }) {
  return <><div className="page-heading"><span className="eyebrow">Page not found</span><h1>{title}</h1></div><section className="panel upcoming"><Mountain /><h2>This page could not be found</h2><p>{description}</p><Link to="/profile" className="text-link">Start planning ↗</Link></section></>;
}
