import { useRef,useState,type FormEvent } from 'react';
import { Link,Navigate,useLocation,useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi,useSession } from './session';
import { loginReturnPath } from './login_return';

export function RegisterPage(){
  const {session}=useSession();const location=useLocation();const navigate=useNavigate();
  const locked=useRef(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [username,setUsername]=useState('');const [name,setName]=useState('');
  const [password,setPassword]=useState('');const [confirmation,setConfirmation]=useState('');
  if(session)return <Navigate to={loginReturnPath(location.state?.returnTo,session.user.role)} replace/>;
  async function submit(event:FormEvent){
    event.preventDefault();if(locked.current)return;
    if(password!==confirmation){setError('两次输入的密码不一致。');return;}
    locked.current=true;setBusy(true);setError('');
    try{
      const result=await privateApi<{user:{username:string}}>('/auth/register',{method:'POST',
        headers:{'Content-Type':'application/json','X-CampMate-Client':'1'},
        body:JSON.stringify({username:username.trim(),display_name:name.trim(),password})});
      setPassword('');setConfirmation('');
      navigate('/login',{replace:true,state:{registeredUsername:result.user.username,returnTo:location.state?.returnTo??'/profile'}});
    }catch(reason){setError(reason instanceof ApiFailure?reason.message:'注册结果暂未确认，请检查连接；如账号已创建，可直接登录。');}
    finally{locked.current=false;setBusy(false);}
  }
  return <><div className="page-heading"><span className="eyebrow">JOIN CAMPMATE</span><h1>开启你的露营计划。</h1><p>创建账户，保存专属于你的资料与行程。</p></div>
    <section className="panel registration-panel"><h2>注册账户</h2><form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="register-name">昵称</label><input id="register-name" autoComplete="nickname" required maxLength={80} value={name} onChange={event=>setName(event.target.value)}/>
      <label htmlFor="register-username">用户名</label><input id="register-username" autoComplete="username" required minLength={3} maxLength={32} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{2,31}" aria-describedby="register-username-hint" value={username} onChange={event=>setUsername(event.target.value)}/>
      <p id="register-username-hint" className="field-hint">3–32 位英文字母、数字、点、下划线或短横线，以字母或数字开头；不区分大小写。</p>
      <label htmlFor="register-password">密码</label><input id="register-password" type="password" autoComplete="new-password" required minLength={8} maxLength={256} aria-describedby="register-password-hint" value={password} onChange={event=>setPassword(event.target.value)}/>
      <p id="register-password-hint" className="field-hint">至少 8 个字符。</p>
      <label htmlFor="register-confirmation">确认密码</label><input id="register-confirmation" type="password" autoComplete="new-password" required minLength={8} maxLength={256} value={confirmation} onChange={event=>setConfirmation(event.target.value)}/>
      {error&&<p className="error-box" role="alert">{error}</p>}
      <button className="primary-button" disabled={busy}>{busy?'正在注册…':'注册并前往登录'} ↗</button>
    </fieldset></form><p>已有账户？<Link className="text-link" to="/login" state={{returnTo:location.state?.returnTo}}>前往登录 ↗</Link></p></section></>;
}
