import type { DraftEquipment } from './profile_guidance';

export function vehicleCount(items:DraftEquipment[]):string {
  const rows=items.filter(item=>item.item_key==='vehicle');
  if(!rows.length||rows.some(item=>!/^\d+$/.test(item.quantity)||!Number.isSafeInteger(Number(item.quantity))))return '';
  const total=rows.reduce((sum,item)=>sum+Number(item.quantity),0);
  return Number.isSafeInteger(total)&&total>0?String(total):'';
}

export function prepareProfileEquipment(items:DraftEquipment[],mode:string,count:string):DraftEquipment[] {
  const result=items.filter(item=>item.item_key!=='charged_phone')
    .map(item=>item.item_key==='vehicle'?{...item,unit:'vehicle'}:item);
  if(mode==='CAR'&&!result.some(item=>item.item_key==='vehicle'))result.push({
    item_key:'vehicle',label:'车辆',quantity:/^\d+$/.test(count)?count:'',unit:'vehicle',capacity:'',confirmed:false,
  });
  return result;
}
