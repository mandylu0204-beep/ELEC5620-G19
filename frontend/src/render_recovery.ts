// Last-resort UI after React has reported an uncaught render/commit error.
// Keep this outside the failed React tree and never retry a saved command here.
export function isDomMutationError(error:unknown):boolean {
  if(!error||typeof error!=='object')return false;
  const value=error as {name?:unknown;message?:unknown};
  return value.name==='NotFoundError'&&typeof value.message==='string'&&
    /removeChild|insertBefore/.test(value.message);
}

export function recoveryPlanPath(pathname:string):string {
  const match=/^\/plans\/([a-zA-Z0-9_-]{1,100})(?:\/update|\/finals\/[a-zA-Z0-9_-]{1,100})?$/.exec(pathname);
  return match?'/plans/'+encodeURIComponent(match[1]):'/plans';
}

export function showRenderRecovery(container:HTMLElement,error:unknown):void {
  const document=container.ownerDocument;
  const panel=document.createElement('section');
  panel.className='panel render-recovery notranslate';
  panel.setAttribute('translate','no');
  panel.setAttribute('role','alert');
  const heading=document.createElement('h1');heading.textContent='This page could not be displayed.';
  const message=document.createElement('p');
  message.textContent='Your saved records are kept. Reload to view the latest status.';
  panel.append(heading,message);
  if(isDomMutationError(error)){
    const hint=document.createElement('p');
    hint.textContent='Turn off automatic page translation for CampMate, then reload.';
    panel.append(hint);
  }
  const actions=document.createElement('div');actions.className='form-actions';
  const reload=document.createElement('button');reload.type='button';reload.className='primary-button';
  reload.textContent='Reload page';reload.addEventListener('click',()=>document.defaultView?.location.reload());
  const back=document.createElement('a');back.className='secondary-button';back.textContent='Return to my plan';
  back.href=recoveryPlanPath(document.defaultView?.location.pathname??'');
  actions.append(reload,back);panel.append(actions);
  // React's root error callback runs after its failed tree is unmounted. Replace
  // that container only; do not patch DOM prototypes or swallow stale updates.
  container.replaceChildren(panel);
}
