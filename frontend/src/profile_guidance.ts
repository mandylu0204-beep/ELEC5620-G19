import type { LogisticsIssue } from './logistics_issues';

export type DraftEquipment={item_key:string;label:string;quantity:string;unit:string;capacity:string;confirmed:boolean};
type Catalog=readonly (readonly string[])[];
export type ProfileDraft={equipment:DraftEquipment[];transport:string;vehicles:string;km:string;
  children:string;childrenCount:string;experience:string};

function equipmentKey(field:string){return /^equipment\.([a-z_]+)(?:\.(quantity|capacity))?$/.exec(field)?.[1]??null;}

export function prepareMissingEquipment(items:DraftEquipment[],issues:LogisticsIssue[],focus:string,catalog:Catalog){
  const keys=new Set(issues.filter(issue=>issue.target==='PROFILE'&&issue.category!=='DATA_GAP')
    .map(issue=>equipmentKey(issue.field)).filter((key):key is string=>!!key));
  const focused=equipmentKey(focus);if(focused)keys.add(focused);
  const added:DraftEquipment[]=[];
  for(const key of keys){
    const type=catalog.find(([name])=>name===key);
    if(type&&!items.some(item=>item.item_key===key))added.push({item_key:key,label:type[1],
      quantity:'',unit:type[2],capacity:'',confirmed:false});
  }
  return added.length?[...items,...added]:items;
}

export function profileGuidance(draft:ProfileDraft,issues:LogisticsIssue[],focus=''){
  const hints:Record<string,string>={};
  const fields=new Set(issues.filter(issue=>issue.target==='PROFILE'&&issue.category!=='DATA_GAP').map(issue=>issue.field));
  if(focus)fields.add(focus);
  if(fields.has('transport.vehicle_count'))fields.add('equipment.vehicle');
  const positive=(value:string)=>/^\d+$/.test(value)&&Number(value)>0;
  for(const field of fields){
    const key=equipmentKey(field);
    if(key){
      const related=issues.find(issue=>equipmentKey(issue.field)===key);
      const required=related?.required as {quantity?:string|number;capacity_persons?:number}|null;
      const rows=draft.equipment.map((item,index)=>({item,index})).filter(({item})=>item.item_key===key);
      const total=rows.filter(({item})=>item.confirmed).reduce((sum,{item})=>sum+(Number(item.quantity)||0),0);
      for(const {item,index} of rows){
        const id=(part:string)=>`gear-${part}-${index}`;
        const vehicle=key==='vehicle';
        if(!item.quantity.trim())hints[id('quantity')]=vehicle?'填写本次实际可用的车辆数；还没有车辆可填 0。':'填写本次实际可用的数量；没有此装备可填 0，系统会保留缺口。';
        else if(related?.code==='EQUIPMENT_SHORTAGE'&&Number(required?.quantity)>total)
          hints[id('quantity')]=`此行程需要 ${required?.quantity}，目前已核实 ${total}。请按实际安排补充，尚未落实的物品不要记为已拥有。`;
        const expected=vehicle?'vehicle':key==='tent'?'item':null;
        if(expected&&item.unit!==expected)hints[id('unit')]=vehicle?'车辆请使用“辆”，不要使用“件”。':'帐篷请使用“件”，数量按帐篷件数填写。';
        const absent=item.quantity.trim()==='0';
        if(!absent&&['tent','vehicle'].includes(key)&&!positive(item.capacity))
          hints[id('capacity')]=vehicle?'填写每辆车可乘坐的总人数，包含驾驶员。例如 5 座车填写 5。':'填写每顶帐篷实际可容纳的人数。例如双人帐填写 2。';
        if(!absent&&!item.confirmed)hints[id('confirmed')]=vehicle?'落实车辆并核对座位后，勾选“已确认可用于本次出行”；借车或租车尚未确认时请保持未勾选。':'核实物品确实可用于本次出行后，再勾选“已核实拥有”；尚未落实请保持未勾选。';
        if(related?.code==='TRANSPORT_CAPACITY'&&positive(item.quantity)&&positive(item.capacity)){
          const capacity=rows.filter(({item})=>item.confirmed).reduce((sum,{item})=>sum+(Number(item.quantity)||0)*(Number(item.capacity)||0),0);
          const need=Number(related.required);
          if(need>capacity)hints[id('capacity')]=`已核实车辆共可乘坐 ${capacity} 人，本次需 ${need} 人。请落实足够座位，或调整同行人数。`;
        }
      }
      if(key==='vehicle'&&draft.transport==='CAR'){
        if(!positive(draft.vehicles))hints['vehicle-count']='请在下方填写本次可用车辆的数量，系统会自动汇总。';
        else if(total>0&&Number(draft.vehicles)!==total)hints['vehicle-count']=`下方已核实车辆共 ${total} 辆，请核对交通安排中的车辆数。`;
      }
    }else if(field==='transport.estimated_km'&&!/^\d+(\.\d+)?$/.test(draft.km.trim()))
      hints['estimated-km']='填写整个行程所有车辆的预计行车总公里数，包含往返；例如一辆车往返共 100 km，填写 100。';
    else if(field==='transport.vehicle_count'&&!positive(draft.vehicles))hints['vehicle-count']='请在下方填写本次可用车辆的数量与载客人数。';
    else if(field==='transport.transport_type'&&!draft.transport)hints.transport='请选择本次实际采用的交通方式。';
    else if(field==='profile.experience_level'&&!draft.experience)hints.experience='请选择露营经验，用于判断装备需求。';
    else if(field==='profile.has_children'||field==='profile.children_count'){
      if(draft.children==='unknown')hints['has-children']='请选择本次同行者中是否有儿童。';
      else if(draft.children==='yes'&&!/^\d+$/.test(draft.childrenCount))hints['children-count']='填写儿童人数，并计入小组总人数。';
    }
  }
  return hints;
}
