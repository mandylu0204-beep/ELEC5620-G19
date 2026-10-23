type Options<T> = {
  read:(signal:AbortSignal)=>Promise<T>;
  progress?:(previous:T,signal:AbortSignal)=>Promise<T|null>;
  poll:(value:T)=>boolean;
  onValue:(value:T)=>void;
  onError:(reason:unknown)=>void;
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
  async function read(){
    if(controller.signal.aborted)return;
    try{
      const update=previous!==null&&options.progress?await options.progress(previous,controller.signal):null;
      if(controller.signal.aborted)return;
      const value=update??await options.read(controller.signal);
      if(controller.signal.aborted)return;
      previous=value;options.onValue(value);
      if(!controller.signal.aborted&&options.poll(value))timer=schedule(()=>void read());
    }catch(reason){
      if(!controller.signal.aborted)options.onError(reason);
    }
  }
  void read();
  return ()=>{controller.abort();if(timer!==undefined)cancel(timer);};
}
