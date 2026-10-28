type FocusEquipment={item_key:string;quantity:string;capacity:string;confirmed:boolean;unit:string};
export function profileFocusId(field:string,items:FocusEquipment[],transport?:string,systemPreparation=false,quantityConfirmsEquipment=false):string|null {
  if(systemPreparation&&(field==='transport.estimated_km'||field==='transport.assumptions'||/^equipment\.(transport_itinerary|fire_free_meal_plan)(?:\.(quantity|capacity))?$/.test(field)))return null;
  if(transport!==undefined&&transport!=='CAR'&&(field==='transport.vehicle_count'||field==='transport.estimated_km'||/^equipment\.vehicle(?:\.(quantity|capacity))?$/.test(field)))return null;
  const ids:Record<string,string>={'transport.estimated_km':'estimated-km','transport.vehicle_count':'vehicle-count',
    'transport.assumptions':'transport-assumptions',
    'transport.transport_type':'transport','profile.children_count':'children-count','profile.has_children':'has-children','profile.experience_level':'experience'};
  if(field==='transport.vehicle_count')return profileFocusId('equipment.vehicle.quantity',items,transport,systemPreparation,quantityConfirmsEquipment);
  if(ids[field])return ids[field];
  const match=field.match(/^equipment\.([a-z_]+)(?:\.(quantity|capacity))?$/);
  if(!match)return null;
  const expected=match[1]==='vehicle'?'vehicle':match[1]==='tent'?'item':null;
  const incomplete=items.findIndex(item=>item.item_key===match[1]&&(!item.confirmed||!item.quantity||
    (['tent','vehicle'].includes(item.item_key)&&!item.capacity)||(expected&&item.unit!==expected)));
  const index=incomplete>=0?incomplete:items.findIndex(item=>item.item_key===match[1]);
  if(index<0)return match[1]==='vehicle'?'add-vehicle':'add-equipment';
  const item=items[index];
  const expectedUnit=item.item_key==='vehicle'?'vehicle':item.item_key==='tent'?'item':null;
  const part=expectedUnit&&item.unit!==expectedUnit&&item.item_key!=='vehicle'?'unit':!item.quantity?'quantity':(['tent','vehicle'].includes(item.item_key)&&!item.capacity)?'capacity':!item.confirmed&&(!quantityConfirmsEquipment||['transport_itinerary','fire_free_meal_plan'].includes(item.item_key))?'confirmed':match[2]??'quantity';
  return `gear-${part}-${index}`;
}

export function profileCorrectionTargets(hints:Record<string,string>,items:FocusEquipment[]){
  return [...new Set(Object.keys(hints).map(id=>id==='vehicle-count'
    ?(items.some(item=>item.item_key==='vehicle')?`gear-quantity-${items.findIndex(item=>item.item_key==='vehicle')}`:'add-vehicle')
    :/^gear-unit-\d+$/.test(id)&&items[Number(id.split('-').at(-1))]?.item_key==='vehicle'
      ?`gear-quantity-${id.split('-').at(-1)}`:id).filter((id):id is string=>!!id))];
}

type FocusTarget={disabled?:boolean;focus:()=>void;scrollIntoView:(options:{block:'center'})=>void};
export function focusProfileTargets(ids:string[],find:(id:string)=>FocusTarget|null=id=>document.getElementById(id)){
  for(const id of ids){
    const node=find(id);
    if(!node||node.disabled)continue;
    node.focus();node.scrollIntoView({block:'center'});return true;
  }
  return false;
}
