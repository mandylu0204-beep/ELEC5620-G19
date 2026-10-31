import { equipmentLabel, type Profile } from './profile';
import { termLabel } from './user_terms';

export type ProfileChange={section:string;before:string[];after:string[]};
const units:Record<string,string>={item:'items',litre:'litres',portion:'portions',vehicle:'vehicles',plan:'plans',set:'sets'};
const modes:Record<string,string>={CAR:'Car',PUBLIC_TRANSPORT:'Public transport',WALKING:'Walking',OTHER:'Other'};
const levels:Record<string,string>={BEGINNER:'First time / Beginner',INTERMEDIATE:'Some experience',EXPERIENCED:'Experienced',ADVANCED:'Advanced / Advanced'};
const known=(value:unknown)=>value===null||value===undefined||value===''?'Unknown':String(value);
const list=(values:string[])=>values.length?values:['Not registered'];

// Display only. Preserve every row, including unknowns and custom names; labels
// are not record IDs and must not be used to match, merge or infer inventory.
function sections(profile:Profile){
  return {
    'Group size':[`${known(profile.group_size)} people`],
    'Camping experience':[levels[(profile.experience_level??'').toUpperCase()]??known(profile.experience_level)],
    'Children in the group':[profile.has_children===null?'Children in group: unknown':profile.has_children?'Children included':'No children',`Recorded child count: ${known(profile.children_count)}`],
    'Equipment and vehicles':list(profile.equipment.map(item=>{
      const unit=item.item_key==='tent'&&item.unit==='item'?'tents':units[item.unit]??item.unit;
      return `${item.label}(Category: ${equipmentLabel(item.item_key)}): ${known(item.quantity)} ${unit}; ${item.item_key==='tent'?'capacity per tent':item.item_key==='vehicle'?'Seats per vehicle: ':'People accommodated per item'} ${known(item.capacity_persons)} people; ${item.confirmed?'Ownership verified':'Unverified'}`;
    })),
    'Transport arrangements':[
      `Transport mode: ${modes[profile.transport.transport_type??'']??known(profile.transport.transport_type)}`,
      `Total vehicles: ${known(profile.transport.vehicle_count)}`,
      `Estimated total distance: ${known(profile.transport.estimated_km)} km`,
      ...profile.transport.assumptions,
    ],
    'Group accessibility and other needs':list(profile.accessibility_requirements.map(item=>termLabel(item,'accessibility'))),
  };
}

export function profileChanges(before:Profile,after:Profile):ProfileChange[]{
  const old=sections(before),next=sections(after);
  const facts=(profile:Profile)=>({
    'Group size':profile.group_size,'Camping experience':profile.experience_level,
    'Children in the group':{present:profile.has_children,count:profile.children_count},
    'Equipment and vehicles':profile.equipment,'Transport arrangements':profile.transport,'Group accessibility and other needs':profile.accessibility_requirements,
  });
  const stable=(value:unknown):unknown=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'
    ?Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,stable(item)])):value;
  const original=facts(before),adopted=facts(after);
  return (Object.keys(old) as (keyof typeof old)[])
    .filter(key=>JSON.stringify(stable(original[key]))!==JSON.stringify(stable(adopted[key])))
    .map(section=>({section,before:old[section],after:next[section]}));
}
