import { equipmentLabel, type Profile } from './profile';
import { termLabel } from './user_terms';

export type ProfileChange={section:string;before:string[];after:string[]};
const units:Record<string,string>={item:'件',litre:'升',portion:'份',vehicle:'辆',plan:'份计划',set:'套'};
const modes:Record<string,string>={CAR:'汽车',PUBLIC_TRANSPORT:'公共交通',WALKING:'步行',OTHER:'其他'};
const levels:Record<string,string>={BEGINNER:'初次 / 初学者',INTERMEDIATE:'有一定经验',EXPERIENCED:'经验丰富',ADVANCED:'熟练 / 进阶'};
const known=(value:unknown)=>value===null||value===undefined||value===''?'未知':String(value);
const list=(values:string[])=>values.length?values:['未登记'];

// Display only. Preserve every row, including unknowns and custom names; labels
// are not record IDs and must not be used to match, merge or infer inventory.
function sections(profile:Profile){
  return {
    '同行人数':[`${known(profile.group_size)} 人`],
    '露营经验':[levels[(profile.experience_level??'').toUpperCase()]??known(profile.experience_level)],
    '儿童情况':[profile.has_children===null?'是否有儿童：未知':profile.has_children?'有儿童':'没有儿童',`登记儿童人数：${known(profile.children_count)}`],
    '装备与车辆':list(profile.equipment.map(item=>{
      const unit=item.item_key==='tent'&&item.unit==='item'?'顶':units[item.unit]??item.unit;
      return `${item.label}（类别：${equipmentLabel(item.item_key)}）：${known(item.quantity)} ${unit}；${item.item_key==='tent'?'每顶可住':item.item_key==='vehicle'?'每辆可乘':'每件人数容量'} ${known(item.capacity_persons)} 人；${item.confirmed?'已核实拥有':'未核实'}`;
    })),
    '交通安排':[
      `交通方式：${modes[profile.transport.transport_type??'']??known(profile.transport.transport_type)}`,
      `车辆总数：${known(profile.transport.vehicle_count)}`,
      `预计总路程：${known(profile.transport.estimated_km)} km`,
      ...profile.transport.assumptions,
    ],
    '同行特殊需求':list(profile.accessibility_requirements.map(item=>termLabel(item,'accessibility'))),
  };
}

export function profileChanges(before:Profile,after:Profile):ProfileChange[]{
  const old=sections(before),next=sections(after);
  const facts=(profile:Profile)=>({
    '同行人数':profile.group_size,'露营经验':profile.experience_level,
    '儿童情况':{present:profile.has_children,count:profile.children_count},
    '装备与车辆':profile.equipment,'交通安排':profile.transport,'同行特殊需求':profile.accessibility_requirements,
  });
  const stable=(value:unknown):unknown=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'
    ?Object.fromEntries(Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([key,item])=>[key,stable(item)])):value;
  const original=facts(before),adopted=facts(after);
  return (Object.keys(old) as (keyof typeof old)[])
    .filter(key=>JSON.stringify(stable(original[key]))!==JSON.stringify(stable(adopted[key])))
    .map(section=>({section,before:old[section],after:next[section]}));
}
