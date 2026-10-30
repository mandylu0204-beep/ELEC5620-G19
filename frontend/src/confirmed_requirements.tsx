import {savedTermLabel} from './campsite_selection';
import type {SelectedRequirements} from './campsite_selection';

export function ConfirmedRequirementsList({requirements,accessibility=[]}:{requirements:SelectedRequirements;accessibility?:string[]}){
  const groups=[{title:'本次已确认的偏好与用餐方式',values:requirements.preferences,kind:'preference' as const},
    {title:'本次必须满足的条件',values:requirements.mandatory_constraints,kind:'constraint' as const},
    {title:'本次同行特殊需求',values:accessibility,kind:'accessibility' as const}];
  return <div className="confirmed-requirements" aria-label="本方案已确认的完整要求">{groups.map(group=><div key={group.title}><h3>{group.title}</h3>
    {group.values?.length?<ul>{group.values.map((text,index)=><li key={index}>{savedTermLabel(text,group.kind)}</li>)}</ul>:<p className="muted">{group.values?'未提出额外要求。':'原记录未保存此项清单。'}</p>}</div>)}
    <p className="muted">以上是本方案采用的确认快照；修改表单不会自动更新此记录或正式检查结果。</p></div>;
}
