import type { DraftEquipment } from './profile_guidance';

export function vehicleCount(items:DraftEquipment[]):string {
  const rows=items.filter(item=>item.item_key==='vehicle');
  if(!rows.length||rows.some(item=>!/^\d+$/.test(item.quantity)||!Number.isSafeInteger(Number(item.quantity))))return '';
  const total=rows.reduce((sum,item)=>sum+Number(item.quantity),0);
  return Number.isSafeInteger(total)&&total>0?String(total):'';
}

export const PLAN_RECORD_KEYS=new Set(['transport_itinerary','fire_free_meal_plan']);

export function prepareProfileEquipment(items:DraftEquipment[],mode:string,count:string,systemPreparation=false):DraftEquipment[] {
  const result=items.filter(item=>item.item_key!=='charged_phone')
    .map(item=>item.item_key==='vehicle'?{...item,unit:'vehicle'}:item);
  if(mode==='CAR'&&!result.some(item=>item.item_key==='vehicle'))result.push({
    item_key:'vehicle',label:'Vehicles',quantity:/^\d+$/.test(count)?count:'',unit:'vehicle',capacity:'',confirmed:false,
  });
  if(!systemPreparation&&mode==='PUBLIC_TRANSPORT'&&!result.some(item=>item.item_key==='transport_itinerary'))result.push({
    item_key:'transport_itinerary',label:'Return journey and connection plan',quantity:'',unit:'plan',capacity:'',confirmed:false,
  });
  return result;
}
