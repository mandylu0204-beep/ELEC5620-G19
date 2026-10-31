import type { LogisticsIssue } from './logistics_issues';

export type DraftEquipment={item_key:string;label:string;quantity:string;unit:string;capacity:string;confirmed:boolean};
type Catalog=readonly (readonly string[])[];
export type ProfileDraft={equipment:DraftEquipment[];transport:string;vehicles:string;km:string;
 children:string;childrenCount:string;experience:string;group?:string;assumptions?:string;systemPreparation?:boolean;quantityConfirmsEquipment?:boolean};

function equipmentKey(field:string){return /^equipment\.([a-z_]+)(?:\.(quantity|capacity))?$/.exec(field)?.[1]??null;}

// This only selects editable form hints. Saved formal assessments remain unchanged.
export function profileFieldApplies(field:string,transport:string,systemPreparation=false){
 if(systemPreparation&&(field==='transport.estimated_km'||field==='transport.assumptions'||['transport_itinerary','fire_free_meal_plan'].includes(equipmentKey(field)??'')))return false;
 return transport==='CAR'||!(field==='transport.vehicle_count'||field==='transport.estimated_km'||equipmentKey(field)==='vehicle');
}

export function prepareMissingEquipment(items:DraftEquipment[],issues:LogisticsIssue[],focus:string,catalog:Catalog,preparationKeys:string[]=[],transport?:string){
 const keys=new Set(issues.filter(issue=>issue.target==='PROFILE'&&issue.category!=='DATA_GAP')
 .map(issue=>equipmentKey(issue.field)).filter((key):key is string=>!!key));
 const focused=equipmentKey(focus);if(focused)keys.add(focused);
 for(const key of preparationKeys)keys.add(key);
 for(const issue of issues.filter(item=>item.code==='COOKING_ARRANGEMENT'))for(const key of issue.related_equipment??[])keys.add(key);
 const added:DraftEquipment[]=[];
 for(const key of keys){
 if(transport!==undefined&&!profileFieldApplies(`equipment.${key}`,transport))continue;
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
 if(!profileFieldApplies(field,draft.transport,draft.systemPreparation))continue;
 const key=equipmentKey(field);
 if(key){
 const related=issues.find(issue=>equipmentKey(issue.field)===key);
 const required=related?.required as {quantity?:string|number;capacity_persons?:number}|null;
 const rows=draft.equipment.map((item,index)=>({item,index})).filter(({item})=>item.item_key===key);
 const total=rows.filter(({item})=>item.confirmed).reduce((sum,{item})=>sum+(Number(item.quantity)||0),0);
 for(const {item,index} of rows){
 const id=(part:string)=>`gear-${part}-${index}`;
 const vehicle=key==='vehicle';
 if(!item.quantity.trim())hints[id('quantity')]=vehicle?'Enter the vehicles available for this trip. Enter 0.':'Enter the quantity available for this trip. Enter 0, if unavailable; the gap will remain.';
 else if(key==='tent'&&Number(draft.group??required?.capacity_persons)>0){
 const need=Number(draft.group??required?.capacity_persons);
 const capacity=rows.filter(({item})=>item.confirmed&&item.unit==='item'&&positive(item.quantity)&&positive(item.capacity))
 .reduce((sum,{item})=>sum+Number(item.quantity)*Number(item.capacity),0);
 if(capacity<need)hints[id('quantity')]=`Verified total tent capacity: ${capacity} people; required for this trip ${need} people. Check quantities and capacity per tent. Do not record unconfirmed tents as owned.`;
 }
 else if(related?.code==='EQUIPMENT_SHORTAGE'&&Number(required?.quantity)>total)
 hints[id('quantity')]=`Previous check requirement: ${required?.quantity}, Currently verified ${total}.Enter actual available equipment. Replanning after saving recalculates requirements using the latest profile.`;
 const expected=vehicle?'vehicle':key==='tent'?'item':key==='transport_itinerary'?'plan':null;
 if(expected&&item.unit!==expected)hints[id('unit')]=vehicle?'Use vehicles as the vehicle unit, not items.':key==='transport_itinerary'?'Use plans as the connection-plan unit. Correct the unit after checking the category.':'Use items for tents and enter the number of tents.';
 const absent=item.quantity.trim()==='0';
 if(!absent&&['tent','vehicle'].includes(key)&&!positive(item.capacity))
 hints[id('capacity')]=vehicle?'Enter total seats per vehicle including the driver. For example, a 5 -seat vehicle: enter 5.':'Enter actual capacity per tent. For a two-person tent, enter 2.';
 if(!absent&&!item.confirmed&&(!draft.quantityConfirmsEquipment||['transport_itinerary','fire_free_meal_plan'].includes(key)))hints[id('confirmed')]=vehicle?'After securing vehicles and checking seats, select Confirmed available for this trip. Leave unconfirmed loans or rentals unchecked.':key==='transport_itinerary'?'Verify outbound, return and final connections before confirming the plan. Leave unverified arrangements unconfirmed.':'Verify the item is available for this trip before selecting Verified owned. Leave unsecured equipment unchecked.';
 if(related?.code==='TRANSPORT_CAPACITY'&&positive(item.quantity)&&positive(item.capacity)){
 const capacity=rows.filter(({item})=>item.confirmed).reduce((sum,{item})=>sum+(Number(item.quantity)||0)*(Number(item.capacity)||0),0);
 const need=Number(related.required);
 if(need>capacity)hints[id('capacity')]=`Verified total vehicle seating: ${capacity} people; required for this trip ${need} people. Secure enough seats or adjust group size.`;
 }
 }
 if(key==='vehicle'&&draft.transport==='CAR'){
 if(!positive(draft.vehicles))hints['vehicle-count']='Enter available vehicle quantities below. The system calculates the total.';
 else if(total>0&&Number(draft.vehicles)!==total)hints['vehicle-count']=`Verified vehicles below total ${total} . Check the vehicle count in transport arrangements.`;
 }
 }else if(field==='transport.assumptions'&&draft.transport==='PUBLIC_TRANSPORT'&&!draft.assumptions?.trim())
 hints['transport-assumptions']='Record verified outbound, return and final connections to the campsite. Mark uncertain details as pending confirmation.';
 else if(field==='transport.estimated_km'&&!/^\d+(\.\d+)?$/.test(draft.km.trim()))
 hints['estimated-km']='Enter the combined distance for all vehicles over the entire trip, including return travel. For example, one vehicle travelling a total of 100 km, Enter 100.';
 else if(field==='transport.vehicle_count'&&!positive(draft.vehicles))hints['vehicle-count']='Enter available vehicle quantities and seating capacities below.';
 else if(field==='transport.transport_type'&&!draft.transport)hints.transport='Select the transport mode for this trip.';
 else if(field==='profile.experience_level'&&!draft.experience)hints.experience='Select camping experience to determine equipment requirements.';
 else if(field==='profile.has_children'||field==='profile.children_count'){
 if(draft.children==='unknown')hints['has-children']='Specify whether children are travelling.';
 else if(draft.children==='yes'&&!/^\d+$/.test(draft.childrenCount))hints['children-count']='Enter the child count, included in the total group size.';
 }
 }
 return hints;
}
