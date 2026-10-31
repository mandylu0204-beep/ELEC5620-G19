import { useRef,useState,type FormEvent } from 'react';
import { Link,Navigate,useLocation,useNavigate } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi,useSession } from './session';
import { loginReturnPath } from './login_return';
import { passwordChecks } from './password_policy';

export function RegisterPage(){
  const {session}=useSession();const location=useLocation();const navigate=useNavigate();
  const locked=useRef(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');const [confirmation,setConfirmation]=useState('');
  const checks=passwordChecks(password);const validPassword=checks.every(item=>item.met);
  if(session)return <Navigate to={loginReturnPath(location.state?.returnTo,session.user.role)} replace/>;
  async function submit(event:FormEvent){
    event.preventDefault();if(locked.current)return;
    if(!validPassword){setError('Meet all password requirements below first.');return;}
    if(password!==confirmation){setError('The passwords do not match.');return;}
    locked.current=true;setBusy(true);setError('');
    try{
      const result=await privateApi<{user:{username:string}}>('/auth/register',{method:'POST',
        headers:{'Content-Type':'application/json','X-CampMate-Client':'1'},
        body:JSON.stringify({username:username.trim(),display_name:username.trim(),password})});
      setPassword('');setConfirmation('');
      navigate('/login',{replace:true,state:{registeredUsername:result.user.username,returnTo:location.state?.returnTo??'/profile'}});
    }catch(reason){setError(reason instanceof ApiFailure?reason.message:'Registration is not yet confirmed. Check your connection. If the account was created, sign in directly.');}
    finally{locked.current=false;setBusy(false);}
  }
  return <><div className="page-heading"><span className="eyebrow">Join CampMate</span><h1>Start your camping journey.</h1><p>Create an account to save your profile and itineraries.</p></div>
    <section className="panel registration-panel"><h2>Create account</h2><form onSubmit={submit}><fieldset disabled={busy}>
      <label htmlFor="register-username">Username <span className="required-mark">Required</span></label><input id="register-username" autoComplete="username" required minLength={3} maxLength={32} pattern="[A-Za-z0-9][A-Za-z0-9_.\-]{2,31}" aria-describedby="register-username-hint" value={username} onChange={event=>setUsername(event.target.value)}/>
      <p id="register-username-hint" className="field-hint">3–32  letters, numbers, dots, underscores or hyphens; start with a letter or number. Case insensitive.</p>
      <label htmlFor="register-password">Password <span className="required-mark">Required</span></label><input id="register-password" type="password" autoComplete="new-password" required minLength={8} maxLength={256} aria-describedby="register-password-hint" value={password} onChange={event=>{setPassword(event.target.value);setError('');}}/>
      <ul id="register-password-hint" className="password-requirements" aria-label="Password requirements" aria-live="polite">{checks.map(item=><li key={item.key} className={item.met?'requirement-met':'requirement-pending'}><span aria-hidden="true">{item.met?'✓':'○'}</span> {item.label} <span className="requirement-state">{item.met?'Met':'Not met'}</span></li>)}</ul>
      <label htmlFor="register-confirmation">Confirm password <span className="required-mark">Required</span></label><input id="register-confirmation" type="password" autoComplete="new-password" required minLength={8} maxLength={256} value={confirmation} onChange={event=>{setConfirmation(event.target.value);setError('');}}/>
      {error&&<p className="error-box" role="alert">{error}</p>}
      <button className="primary-button" disabled={busy||!validPassword}>{busy?'Registering…':'Register and sign in'} ↗</button>
    </fieldset></form><p>Already have an account?<Link className="text-link" to="/login" state={{returnTo:location.state?.returnTo}}>Go to sign in ↗</Link></p></section></>;
}
