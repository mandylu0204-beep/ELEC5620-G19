import type { ReactNode } from 'react';

export function TripFlow({step}:{step:1|2|3}) {
  return <ol className="trip-flow" aria-label="露营规划步骤">{['完善资料','确认需求','开始规划'].map((title,index)=><li key={title} className={step===index+1?'flow-current':''} aria-current={step===index+1?'step':undefined}><span>{String(index+1).padStart(2,'0')}</span><strong>{title}</strong></li>)}</ol>;
}

export function FieldHint({id,error,children}:{id:string;error?:string;children?:ReactNode}) {
  return <p id={id} className={error?'field-hint field-error':'field-hint'}>{error??children}</p>;
}
