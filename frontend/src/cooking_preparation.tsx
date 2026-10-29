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

// Presentation only: complete registration is not a formal logistics/safety pass.
export function canHideCookingPreparation(value:CookingPreparation|null|undefined){
  if(!value||value.applicable===false||value.items.length!==2)return false;
  const recorded=['camping_stove','fuel_canister'].every(key=>{
    const rows=value.items.filter(item=>item.item_key===key);
    if(rows.length!==1)return false;
    const item=rows[0];
    return item.recorded&&item.unit_valid&&item.entered_quantity!==null
      &&Number.isSafeInteger(item.entered_quantity)&&item.entered_quantity>0
      &&item.confirmed_quantity===item.entered_quantity;
  });
  if(!recorded||value.calculation_status!==undefined&&value.calculation_status!=='DRAFT_ESTIMATE')return false;
  if(value.calculation_status==='DRAFT_ESTIMATE'||value.required_fuel_quantity!==undefined||value.fuel_gap!==undefined){
    if(value.required_fuel_quantity===undefined)return false;
    if(value.required_fuel_quantity===null||!Number.isFinite(Number(value.required_fuel_quantity)))return false;
    if(value.fuel_gap==null||!Number.isFinite(Number(value.fuel_gap))||Number(value.fuel_gap)!==0)return false;
  }
  return true;
}

export function CookingPreparationPanel({value,preview=null,stale=false,unsaved=false,attention=false,onCheck,onFocus,busy=false,error=''}:{
  value:CookingPreparation|null|undefined;preview?:CookingPreparation|null;stale?:boolean;unsaved?:boolean;attention?:boolean;
  onCheck?:()=>void;onFocus?:(key:string)=>void;busy?:boolean;error?:string}){
  if(!value)return null;
  const shown=preview&&!stale?preview:value;
  const fuelCostPending=!stale&&shown.fuel_price_status==='MISSING_REFERENCE'
    &&shown.required_fuel_quantity!=null&&(shown.fuel_gap==null||Number(shown.fuel_gap)>0);
  const hidden=canHideCookingPreparation(shown)&&!stale&&!unsaved&&!attention&&!busy&&!error&&!fuelCostPending;
  if(hidden)return null;
  const content=<>
    {!stale&&shown.applicable===false?<p role="status">用餐方式已变更，请返回需求页面核对。</p>:<>
      <p>你选择了自行烹饪，请核对炉具和燃料的准备情况。</p>
      <ul>{shown.items?.map(item=><li key={item.item_key}><strong>{equipmentLabel(item.item_key)}</strong>：{!item.recorded?'尚未填写数量':!item.unit_valid?'请核对数量单位':item.entered_quantity===null?'尚未填写数量':`${stale?'上次登记':unsaved?'本页填写':'已登记'} ${item.entered_quantity} 个${item.confirmed_quantity===null?'，待确认可用':''}`}
        {onFocus&&<button type="button" className="text-button" onClick={()=>onFocus(item.item_key)}>填写{equipmentLabel(item.item_key)}资料 ↓</button>}</li>)}</ul>
      {stale&&<p role="status">资料已修改，请更新准备情况。</p>}
      {unsaved&&!stale&&<p role="status">本页修改尚未保存，请核对炉具与燃料后保存资料；正式结果尚未更新。</p>}
      {attention&&<p role="status">本次保存的检查仍有烹饪相关待办，请按具体问题处理；登记数量不会自动清除正式缺口。</p>}
      {!stale&&preview?.required_fuel_quantity!=null&&<p>预计需要燃料罐 {preview.required_fuel_quantity} 个{preview.fuel_gap!=null?`，还缺 ${preview.fuel_gap} 个`:'，可用数量待确认'}。</p>}
      {!stale&&preview?.calculation_status==='WAITING_FOR_STOVE'&&<p>请先填写可用炉具数量，再确认燃料需求。</p>}
      {!stale&&preview?.calculation_status==='UNAVAILABLE'&&<p>暂时无法估算燃料用量，请在方案生成后查看装备清单。</p>}
      {fuelCostPending&&<p>燃料费用待确认。</p>}
      {onCheck&&<button type="button" className="secondary-button" disabled={busy} onClick={onCheck}>{busy?'正在更新…':'更新准备情况'}</button>}
    </>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </>;
  return <section className="clarifications" aria-label="烹饪准备清单"><h3>烹饪装备准备</h3>{content}</section>;
}
