// ISO date-only arithmetic uses UTC; "today" is always evaluated in Sydney.
export function validIsoDate(value:string):boolean{
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
 const date=new Date(value+'T00:00:00Z');
 return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value;
}
export function addDays(value:string,days:number):string{
 if(!validIsoDate(value))throw new Error('Invalid ISO date.');
 const date=new Date(value+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+days);
 return date.toISOString().slice(0,10);
}
export function sydneyToday(now=new Date()):string{
 const parts=new Intl.DateTimeFormat('en-AU',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 return ['year','month','day'].map(type=>parts.find(part=>part.type===type)!.value).join('-');
}
export function firstFutureDate(checkDate?:string,now=new Date()):string{
 const today=sydneyToday(now);return addDays(checkDate&&validIsoDate(checkDate)&&checkDate>today?checkDate:today,1);
}
export function dateFieldError(value:string,minimum:string):string{
 if(!value)return '';
 if(!validIsoDate(value))return 'Enter a valid date in YYYY-MM-DD format.';
 return value<minimum?'Choose a date on or after '+minimum+'.':'';
}
export function endDateMinimum(start:string,minimum:string):string{
 const end=validIsoDate(start)?addDays(start,1):minimum;return end>minimum?end:minimum;
}
