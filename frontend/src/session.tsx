import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { ApiFailure, type ApiError } from './api';

type User = { user_id: string; username: string; display_name: string; role: 'CAMPER' | 'FOUNDER' };
export type Session = { user: User; csrf_token: string };
type Auth = { session: Session | null; loading: boolean; error: string | null; reload: () => void; login: (username: string, password: string) => Promise<void>; logout: () => Promise<void> };
const SessionContext = createContext<Auth | null>(null);

export async function privateApi<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api/v1' + path, { credentials: 'same-origin', ...options });
  if (response.status === 204) return undefined as T;
  const body = await response.json();
  if (!response.ok) throw new ApiFailure(body as ApiError);
  return body as T;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null);
    privateApi<Session>('/auth/me', { signal: controller.signal }).then(value => { if (!controller.signal.aborted) setSession(value); }).catch(reason => {
      if (controller.signal.aborted) return;
      setSession(null);
      if (!(reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED')) setError('无法读取登录状态，请重试。');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  async function login(username: string, password: string) {
    const value = await privateApi<Session>('/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CampMate-Client': '1' }, body: JSON.stringify({ username, password }) });
    setSession(value); setError(null);
  }
  async function logout() {
    if (!session) return;
    await privateApi<void>('/auth/logout', { method: 'POST', headers: { 'X-CampMate-Client': '1', 'X-CSRF-Token': session.csrf_token } });
    setSession(null);
  }
  return <SessionContext.Provider value={{ session, loading, error, reload: () => setRevision(value => value + 1), login, logout }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const value = useContext(SessionContext);
  if (!value) throw new Error('SessionProvider is required');
  return value;
}

export function AccountControl() {
  const { session, loading, logout } = useSession();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  if (loading) return <span>检查账户…</span>;
  if (!session) return <Link className="account-link" to="/login">登录 ↗</Link>;
  return <div className="account-control"><span>{session.user.display_name} · {session.user.role === 'FOUNDER' ? 'Founder' : 'Camper'}</span><button disabled={busy} onClick={async () => { setBusy(true); setError(''); try { await logout(); navigate('/login'); } catch { setError('退出失败，请重试'); } finally { setBusy(false); } }}>{busy ? '正在退出' : '退出'}</button>{error && <span role="alert">{error}</span>}</div>;
}

export function Protected({ role, children }: { role: User['role']; children: ReactNode }) {
  const { session, loading, error, reload } = useSession();
  if (loading) return <section className="panel">正在检查登录状态…</section>;
  if (error) return <section className="panel"><p role="alert">{error}</p><button onClick={reload}>重新连接</button></section>;
  if (!session) return <section className="panel"><h2>先登录你的账户</h2><p>登录后可访问自己的记录。</p><Link className="primary-button" to="/login">去登录 ↗</Link></section>;
  if (session.user.role !== role) return <section className="panel"><h2>当前账户没有此页面权限</h2><p>Camper 查看自己的资料与方案；Founder 处理人工审核。</p></section>;
  return <div key={session.user.user_id}>{children}</div>;
}

export function LoginPage() {
  const { session, login } = useSession();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (session) return <Navigate to={session.user.role === 'FOUNDER' ? '/review' : '/plans'} replace />;
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await login(username.trim(), password); setPassword(''); }
    catch (reason) { setError(reason instanceof ApiFailure ? reason.message : '登录失败，请检查服务连接。'); }
    finally { setBusy(false); }
  }
  return <><div className="page-heading"><span className="eyebrow">YOUR ACCOUNT</span><h1>欢迎回来。</h1><p>登录后，继续你的露营计划。</p></div><div className="preview-grid"><section className="panel"><h2>账户登录</h2><form onSubmit={submit}><label htmlFor="username">用户名</label><input id="username" autoComplete="username" maxLength={80} required disabled={busy} value={username} onChange={event => setUsername(event.target.value)} /><label htmlFor="password">密码</label><input id="password" type="password" autoComplete="current-password" maxLength={256} required disabled={busy} value={password} onChange={event => setPassword(event.target.value)} />{error && <p className="error-box" role="alert">{error}</p>}<button className="primary-button" disabled={busy}>{busy ? '正在登录…' : '登录'} <span>↗</span></button></form></section><section className="panel next-panel"><span className="tag">SYNTHETIC DEMO ACCOUNTS</span><h2>本地演示账户</h2><p>选择一个角色验证用户隔离。这些是公开的演示凭据。</p><dl className="demo-accounts">{[['camper.a','CampMate-A-2026!'],['camper.b','CampMate-B-2026!'],['founder','CampMate-Founder-2026!']].map(([name, pass]) => <div key={name}><dt>{name}</dt><dd><code>{pass}</code></dd></div>)}</dl><p className="muted">账户与演示数据中的 Profile ID 分开管理。Founder 审核已接入；规划执行与最终化仍待接入。</p></section></div></>;
}
