import {equipmentLabel,type Equipment} from './profile';

export type CookingPreparation={scope:'PREPARATION_ONLY';official_assessment:false;
  applicable?:boolean;items:{item_key:string;recorded:boolean;entered_quantity:number|null;confirmed_quantity:number|null;unit_valid:boolean}[];
  fuel_price_status:string;required_fuel_quantity?:string|null;fuel_gap?:string|null;
  calculation_status?:string;example?:{stove_quantity:number;fuel_quantity:string}|null};

export function cookingDraft(rows:{item_key:string;label:string;quantity:string;unit:string;confirmed:boolean}[]):Equipment[]{
  return rows.filter(row=>['camping_stove','fuel_canister'].includes(row.item_key)).map(row=>{
    if(row.quantity!==''&&(!/^\d+$/.test(row.quantity)||!Number.isSafeInteger(Number(row.quantity))))
      throw new Error('炉具和燃料数量请填写非负整数，未知可留空。');
    return {item_key:row.item_key,label:row.label,quantity:row.quantity===''?null:Number(row.quantity),unit:row.unit,confirmed:row.confirmed,capacity_persons:null};
  });
}

export function CookingPreparationPanel({value,preview=null,stale=false,onCheck,onFocus,busy=false,error=''}:{
  value:CookingPreparation|null|undefined;preview?:CookingPreparation|null;stale?:boolean;
  onCheck?:()=>void;onFocus?:(key:string)=>void;busy?:boolean;error?:string}){
  if(!value)return null;
  const shown=preview&&!stale?preview:value;
  const fuelCostPending=!stale&&shown.fuel_price_status==='MISSING_REFERENCE'
    &&shown.required_fuel_quantity!=null&&(shown.fuel_gap==null||Number(shown.fuel_gap)>0);
  return <section className="clarifications" aria-label="烹饪准备清单">
    <h3>烹饪装备准备</h3>
    {!stale&&shown.applicable===false?<p role="status">用餐方式已变更，请返回需求页面核对。</p>:<>
      <p>你选择了自行烹饪，请核对炉具和燃料的准备情况。</p>
      <ul>{shown.items?.map(item=><li key={item.item_key}><strong>{equipmentLabel(item.item_key)}</strong>：{!item.recorded?'尚未填写数量':!item.unit_valid?'请核对数量单位':item.entered_quantity===null?'尚未填写数量':`${stale?'上次登记':'已登记'} ${item.entered_quantity} 个${item.confirmed_quantity===null?'，待确认可用':''}`}
        {onFocus&&<button type="button" className="text-button" onClick={()=>onFocus(item.item_key)}>填写{equipmentLabel(item.item_key)}资料 ↓</button>}</li>)}</ul>
      {stale&&<p role="status">资料已修改，请更新准备情况。</p>}
      {!stale&&preview?.required_fuel_quantity!=null&&<p>预计需要燃料罐 {preview.required_fuel_quantity} 个{preview.fuel_gap!=null?`，还缺 ${preview.fuel_gap} 个`:'，可用数量待确认'}。</p>}
      {!stale&&preview?.calculation_status==='WAITING_FOR_STOVE'&&<p>请先填写可用炉具数量，再确认燃料需求。</p>}
      {!stale&&preview?.calculation_status==='UNAVAILABLE'&&<p>暂时无法估算燃料用量，请在方案生成后查看装备清单。</p>}
      {fuelCostPending&&<p>燃料费用待确认。</p>}
      {onCheck&&<button type="button" className="secondary-button" disabled={busy} onClick={onCheck}>{busy?'正在更新…':'更新准备情况'}</button>}
    </>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}
