export function profileFocusId(field:string,items:{item_key:string;quantity:string;capacity:string;confirmed:boolean;unit:string}[]) {
  const ids:Record<string,string>={'transport.estimated_km':'estimated-km','transport.vehicle_count':'vehicle-count',
    'transport.transport_type':'transport','profile.children_count':'children-count','profile.has_children':'has-children','profile.experience_level':'experience'};
  if(field==='transport.vehicle_count')return profileFocusId('equipment.vehicle.quantity',items);
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
  const part=expectedUnit&&item.unit!==expectedUnit?'unit':!item.quantity?'quantity':(['tent','vehicle'].includes(item.item_key)&&!item.capacity)?'capacity':!item.confirmed?'confirmed':match[2]??'quantity';
  return `gear-${part}-${index}`;
}
