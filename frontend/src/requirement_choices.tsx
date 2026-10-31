import {termLabel} from './user_terms';
import {useEffect,useRef,useState} from 'react';
export type RequirementChoice={value:string;label:string;aliases:string[]};
export type RequirementCatalogue={version:string;fields:Record<string,RequirementChoice[]>};
export function requirementChoiceLabel(choice:RequirementChoice):string{
 if(!/[\u3400-\u9fff]/u.test(choice.label))return choice.label;
 for(const kind of ['preference','constraint','accessibility'] as const){
  const label=termLabel(choice.value,kind);if(label!==choice.value)return label;
 }
 return choice.label;
}
const lines=(value:string)=>value.split(/\r?\n/).map(item=>item.trim()).filter(Boolean);
const clean=(value:string)=>value.trim().toLowerCase().replace(/[\u3002.!\uff01]+$/,'').replace(/\s+/g,' ');
export function choiceMatch(value:string,choices:RequirementChoice[]){
  const normalized=clean(value);
  return choices.find(choice=>choice.aliases.some(alias=>normalized===clean(alias)))?.value??null;
}
export function toggleRequirement(value:string,choices:RequirementChoice[],key:string,checked:boolean){
  const remaining=lines(value).filter(item=>choiceMatch(item,choices)!==key);
  return [...remaining,...(checked?[key]:[])].join('\n');
}
export function replaceOtherRequirements(value:string,owned:string[],next:string){
  const retained=lines(value).filter(item=>!owned.includes(item));
  const added=lines(next);
  return {value:[...retained,...added].filter((item,index,all)=>all.indexOf(item)===index).join('\n'),owned:added.filter(item=>!retained.includes(item))};
}
export function RequirementChoices({id,title,value,choices,onChange,preserved=[],hint=''}:{
  id:string;title:string;value:string;choices:RequirementChoice[]|null;onChange:(value:string)=>void;preserved?:string[];hint?:string;
}){
  const unknown=(text:string)=>lines(text).filter(item=>!choiceMatch(item,choices??[])&&!preserved.includes(item)).join('\n');
  const [other,setOther]=useState(()=>unknown(value));const last=useRef(value);const previousChoices=useRef(choices);const owned=useRef(lines(unknown(value)));
  useEffect(()=>{if(value!==last.current||choices!==previousChoices.current){last.current=value;previousChoices.current=choices;setOther(unknown(value));owned.current=lines(unknown(value));}},[value,choices]);
  const publish=(next:string)=>{last.current=next;onChange(next);};
  const selected=new Set(lines(value).map(item=>choiceMatch(item,choices??[])));
  const unmatched=lines(other).filter(item=>!choiceMatch(item,choices??[]));
  return <fieldset id={id} tabIndex={-1} className="requirement-choice-group" aria-describedby={id+'-hint'}><legend>{title}</legend>
    <p id={id+'-hint'} className="field-hint">{hint||'Select any that apply. These are your requirements, not confirmation that a campsite meets them. The system still checks the data.'}</p>
    {choices===null?<p role="status">Loading available conditions…</p>:<div className="requirement-choice-grid">{choices.map(choice=><label className="checkbox-label" key={choice.value}>
      <input type="checkbox" checked={selected.has(choice.value)} onChange={event=>{const next=toggleRequirement(value,choices,choice.value,event.target.checked);setOther(unknown(next));owned.current=lines(unknown(next));publish(next);}}/>{requirementChoiceLabel(choice)}</label>)}</div>}
    <label htmlFor={id+'-other'}>Other requirements (optional; one per line)</label>
    <textarea id={id+'-other'} maxLength={8000} value={other} disabled={choices===null} placeholder="Describe requirements not listed above" onChange={event=>{
      const next=event.target.value;setOther(next);
      const updated=replaceOtherRequirements(value,owned.current,next);owned.current=updated.owned;publish(updated.value);
    }}/>
    {other&&<p className="field-hint" role="status">{unmatched.length?'Other requirements do not yet map to existing conditions. Human assistance is needed before generating a plan.':'Mapped to existing options. Summary generation will check again; duplicate wording alone does not require separate review.'}</p>}
  </fieldset>;
}
