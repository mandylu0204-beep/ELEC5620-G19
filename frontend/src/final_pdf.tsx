import {useState} from 'react';
import {ApiFailure,type ApiError} from './api';

export function FinalPdfDownload({planId,finalId}:{planId:string;finalId:string}){
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  async function download(){
    if(busy)return;setBusy(true);setError('');
    try{
      const response=await fetch('/api/v1/plans/'+encodeURIComponent(planId)+'/finals/'+encodeURIComponent(finalId)+'/pdf',{credentials:'same-origin'});
      if(!response.ok)throw new ApiFailure(await response.json() as ApiError);
      if(!response.headers.get('content-type')?.includes('application/pdf'))throw new Error('PDF Export did not finish. The saved final plan is retained.');
      const blob=await response.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement('a');
      anchor.href=url;anchor.download='campmate-final-'+finalId+'.pdf';document.body.appendChild(anchor);anchor.click();anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(value){setError(value instanceof Error?value.message:'PDF Export did not finish. Try again; the final plan is unaffected.');}finally{setBusy(false);}
  }
  return <div className="final-pdf-download"><button type="button" className="secondary-button" disabled={busy} onClick={()=>void download()}>{busy?'Exporting PDF…':'Download saved plan PDF'}</button>{error&&<p className="error-box" role="alert">{error}</p>}</div>;
}
