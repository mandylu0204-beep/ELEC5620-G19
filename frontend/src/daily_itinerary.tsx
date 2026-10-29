import { chineseProse } from './display_facts';
import { campName } from './campsite_names';
import { itineraryText } from './user_terms';

export type SavedEntry={entry_kind:string;start_at:string;end_at:string;campsite_id:string|null;description:string};
const simulatedActivityMarker='（模拟活动建议；须以正式安全检查和现场条件为准。）';
const dayFormat=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'});

// Only the saved itinerary is used, including history and final snapshots.
export function DailyItinerary({entries,time,label}:{entries:SavedEntry[];time:(value:string)=>string;label:(value:string)=>string}){
  const days=new Map<string,SavedEntry[]>();
  for(const entry of entries){const day=dayFormat.format(new Date(entry.start_at));days.set(day,[...(days.get(day)??[]),entry]);}
  return <div className="daily-itinerary">{[...days].map(([day,items],index)=><section key={day} aria-label={`第 ${index+1} 天 · ${day}`}>
    <h3>第 {index+1} 天 · {day}</h3>
    <ol className="plan-timeline">{items.map((entry,i)=>{const text=chineseProse(itineraryText(entry.description));
      const separator=text?.indexOf('：')??-1;
      const namedActivity=entry.entry_kind==='ACTIVITY'&&!!text?.endsWith(simulatedActivityMarker)&&separator>0&&separator<=80;
      const activityTitle=namedActivity?text!.slice(0,separator):null;
      // Keep the saved provenance untouched; avoid repeating its internal marker on cards.
      const description=namedActivity
        ?text!.slice(separator+1,-simulatedActivityMarker.length)+'（须以正式安全检查和现场条件为准。）'
        :text;
      return <li key={i}>
      <div className="timeline-time"><span>{label(entry.entry_kind)}</span><time>{time(entry.start_at)}</time><small>建议时间／待确认</small></div>
      <div className="timeline-content"><h4>{activityTitle??(entry.campsite_id?campName(entry.campsite_id):label(entry.entry_kind))}</h4>
        {activityTitle&&entry.campsite_id&&<p className="muted">{campName(entry.campsite_id)}</p>}
        <p>{description??'此项为建议行程，具体活动与安排待确认。'}</p>
        {!text&&<details><summary>查看保存的行程描述原文</summary><p>{entry.description}</p></details>}
        <small>至 {time(entry.end_at)}</small>
      </div>
    </li>;})}</ol>
  </section>)}</div>;
}
