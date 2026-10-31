import {savedTermLabel} from './campsite_selection';
import type {SelectedRequirements} from './campsite_selection';

export function ConfirmedRequirementsList({requirements,accessibility=[]}:{requirements:SelectedRequirements;accessibility?:string[]}){
  const groups=[{title:'Confirmed preferences and meal arrangement',values:requirements.preferences,kind:'preference' as const},
    {title:'Required conditions for this trip',values:requirements.mandatory_constraints,kind:'constraint' as const},
    {title:'Accessibility and other group needs for this trip',values:accessibility,kind:'accessibility' as const}];
  return <div className="confirmed-requirements" aria-label="Complete confirmed requirements for this plan">{groups.map(group=><div key={group.title}><h3>{group.title}</h3>
    {group.values?.length?<ul>{group.values.map((text,index)=><li key={index}>{savedTermLabel(text,group.kind)}</li>)}</ul>:<p className="muted">{group.values?'No additional requirements specified.':'The original record did not save this list.'}</p>}</div>)}
    <p className="muted">This is the confirmation snapshot used by this plan. Editing a form does not automatically update this record or formal check results.</p></div>;
}
