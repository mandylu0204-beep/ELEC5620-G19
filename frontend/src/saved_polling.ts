type Options<T> = {
  read:(signal:AbortSignal)=>Promise<T>;
  progress?:(previous:T,signal:AbortSignal)=>Promise<T|null>;
  poll:(value:T)=>boolean;
  onValue:(value:T)=>void;
  onError:(reason:unknown)=>void;
  retryOnError?:(reason:unknown)=>boolean;
  subscribeRefresh?:(refresh:()=>void)=>()=>void;
  schedule?:(callback:()=>void)=>unknown;
  cancel?:(timer:unknown)=>void;
};

// Each page/read generation owns its signal and timer, even if transport
// ignores cancellation and resolves an obsolete request afterwards.
export function startSavedPolling<T>(options:Options<T>):()=>void {
  const controller=new AbortController();
  const schedule=options.schedule??(callback=>setTimeout(callback,2500));
  const cancel=options.cancel??(timer=>clearTimeout(timer as ReturnType<typeof setTimeout>));
  let previous:T|null=null;
  let timer:unknown;
  let inFlight=false,refreshRequested=false;
  async function read(full=false){
    if(controller.signal.aborted)return;
    if(inFlight){refreshRequested=true;return;}
    if(timer!==undefined){cancel(timer);timer=undefined;}
    inFlight=true;
    let repeat=false,retryFull=false;
    try{
      const update=!full&&previous!==null&&options.progress?await options.progress(previous,controller.signal):null;
      if(controller.signal.aborted)return;
      const value=update??await options.read(controller.signal);
      if(controller.signal.aborted)return;
      previous=value;options.onValue(value);
      repeat=options.poll(value);
    }catch(reason){
      if(!controller.signal.aborted){
        options.onError(reason);
        repeat=previous!==null&&options.poll(previous)&&options.retryOnError?.(reason)===true;
        retryFull=repeat;
      }
    }finally{
      inFlight=false;
      if(!controller.signal.aborted){
        if(refreshRequested){refreshRequested=false;void read(true);}
        else if(repeat)timer=schedule(()=>void read(retryFull));
      }
    }
  }
  const unsubscribe=options.subscribeRefresh?.(()=>void read(true));
  void read();
  return ()=>{controller.abort();if(timer!==undefined)cancel(timer);unsubscribe?.();};
}

export function subscribePageRefresh(refresh:()=>void):()=>void {
  const resume=()=>{if(document.visibilityState==='visible')refresh();};
  window.addEventListener('focus',resume);
  document.addEventListener('visibilitychange',resume);
  return ()=>{window.removeEventListener('focus',resume);document.removeEventListener('visibilitychange',resume);};
}
