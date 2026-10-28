import type {Equipment} from './profile';

type QuantifiedEquipment={item_key:string;label:string;quantity:string;unit:string;capacity:string;confirmed:boolean};
const EXPLICIT_CONFIRMATION=new Set(['transport_itinerary','fire_free_meal_plan']);
const knownQuantity=(value:string)=>/^\d+$/.test(value)&&Number.isSafeInteger(Number(value));

// Only an explicit profile save asserts stock availability. Never mutate the
// loaded profile, old request snapshots, or historical plan records.
export function equipmentForSave<T extends QuantifiedEquipment>(rows:T[]):T[]{
  return rows.map(row=>EXPLICIT_CONFIRMATION.has(row.item_key)?{...row}
    :{...row,confirmed:knownQuantity(row.quantity)});
}

export function equipmentPayload(rows:QuantifiedEquipment[]):Equipment[]{
  const count=(value:string,minimum:number):number|null=>{
    if(value==='')return null;
    if(!knownQuantity(value)||Number(value)<minimum)throw new Error('装备数量与容量请填写有效整数，未知可留空。');
    return Number(value);
  };
  return equipmentForSave(rows).map(row=>({item_key:row.item_key,label:row.label.trim(),
    quantity:count(row.quantity,0),unit:row.unit.trim(),capacity_persons:count(row.capacity,1),confirmed:row.confirmed}));
}
