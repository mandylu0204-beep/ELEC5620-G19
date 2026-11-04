import {visitorText} from './visitor_text.ts';
import {englishSavedActivity} from './legacy_activity_descriptions';
import { displayProse } from './display_facts';
import { campName } from './campsite_names';
import { itineraryText } from './user_terms';

export type SavedEntry={entry_kind:string;start_at:string;end_at:string;campsite_id:string|null;description:string};
const simulatedActivityMarker='(Simulated activity suggestion; subject to formal safety checks and on-site conditions.)';
const dayFormat=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit'});

// Only the saved itinerary is used, including history and final snapshots.
export function DailyItinerary({entries,time,label}:{entries:SavedEntry[];time:(value:string)=>string;label:(value:string)=>string}){
  const days=new Map<string,SavedEntry[]>();
  for(const entry of entries){const day=dayFormat.format(new Date(entry.start_at));days.set(day,[...(days.get(day)??[]),entry]);}
  return <div className="daily-itinerary">{[...days].map(([day,items],index)=><section key={day} aria-label={`Day ${index+1} · ${day}`}>
    <h3>Day {index+1} · {day}</h3>
    <ol className="plan-timeline">{items.map((entry,i)=>{const translated=englishSavedActivity(entry.description,entry.campsite_id,entry.entry_kind);
      const savedText=translated??itineraryText(entry.description);
      const text=displayProse(savedText);
      const separator=savedText.indexOf(': ');
      const namedActivity=entry.entry_kind==='ACTIVITY'&&!!text&&savedText.endsWith(simulatedActivityMarker)&&separator>0&&separator<=80;
      const activityTitle=namedActivity?savedText.slice(0,separator):null;
      // Keep the saved provenance untouched; avoid repeating its internal marker on cards.
      const description=namedActivity
        ?savedText.slice(separator+2,-simulatedActivityMarker.length)+'(Subject to formal safety checks and on-site conditions.)'
        :text;
      return <li key={i}>
      <div className="timeline-time"><span>{label(entry.entry_kind)}</span><time>{time(entry.start_at)}</time><small>Suggested time / to be confirmed</small></div>
      <div className="timeline-content"><h4>{activityTitle??(entry.campsite_id?campName(entry.campsite_id):label(entry.entry_kind))}</h4>
        {activityTitle&&entry.campsite_id&&<p className="muted">{campName(entry.campsite_id)}</p>}
        <p>{visitorText(description??'Suggested itinerary item; confirm activities and transport arrangements.')}</p>
        {translated&&<small>English display of a saved activity suggestion.</small>}
        {!text&&<details><summary>View the saved original itinerary description</summary><p>{visitorText(entry.description)}</p></details>}
        <small>to {time(entry.end_at)}</small>
      </div>
    </li>;})}</ol>
  </section>)}</div>;
}
