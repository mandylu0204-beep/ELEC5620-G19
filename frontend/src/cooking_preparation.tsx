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
  return <section className="clarifications" aria-label="烹饪准备清单">
    <h3>自行烹饪：炉具和配套燃料一起核对</h3>
    {!stale&&preview?.applicable===false&&<p role="status">来源需求已不采用自行烹饪，请重新载入需求核对。这不表示正式装备检查通过。</p>}
    <p>这是准备提示／规则预检查，不是正式评估。燃料规则尚未触发，也不等于本次无需燃料；具体需求要在炉具安排明确后计算。</p>
    {onCheck&&<p className="muted">下列库存来自来源资料或最近一次预检查。本页编辑后，请点击预检查核对新值；不会保存个人资料或更新方案。</p>}
    <ul>{shown.items?.map(item=><li key={item.item_key}><strong>{equipmentLabel(item.item_key)}</strong>：{!item.recorded?'尚未登记，请一起核对':!item.unit_valid?'单位需要核对':item.entered_quantity===null?'数量未知':`填写数量 ${item.entered_quantity}；${item.confirmed_quantity===null?'尚未核实':`已核实 ${item.confirmed_quantity}`}`}
      {onFocus&&<button type="button" className="text-button" onClick={()=>onFocus(item.item_key)}>前往填写{equipmentLabel(item.item_key)} ↓</button>}</li>)}</ul>
    {stale&&<p role="status">炉具或燃料资料已修改，上次预检查已过期。请重新预检查；正式结果仍未更新。</p>}
    {!stale&&preview?.required_fuel_quantity!=null&&<p>按本页填写的炉具数量及当前规则，预估需要燃料罐 {preview.required_fuel_quantity} 个{preview.fuel_gap!=null?`；相对已核实库存，预估缺口 ${preview.fuel_gap} 个`:'；库存尚未核实，缺口仍待确认'}。这不是已保存的正式需求。</p>}
    {!stale&&preview?.calculation_status==='WAITING_FOR_STOVE'&&<p>先明确炉具安排，再核对燃料需求；填 0 也不表示自行烹饪安排已经落实。{preview.example&&`现行规则按登记炉具数量计算：若登记 ${preview.example.stove_quantity} 个炉具，则燃料需求为 ${preview.example.fuel_quantity} 个；这只是规则示例，不是你已拥有或必须使用的数量。`}</p>}
    {!stale&&preview?.calculation_status==='UNAVAILABLE'&&<p>当前规则暂不能提供单项预估，请保留未知值并按正式检查核对，不能据此认为无需燃料。</p>}
    {shown.fuel_price_status==='MISSING_REFERENCE'&&<p><strong>系统报价资料：</strong>当前未登记燃料罐补缺参考价。如还需补购或费用未确认，完整费用仍未知，这不等于已经超预算。填写个人资料不会补出单价；实际备齐后可据实登记，再进行正式检查。不要为通过检查虚填“已拥有”。</p>}
    {onCheck&&<button type="button" className="secondary-button" disabled={busy} onClick={onCheck}>{busy?'正在预检查…':'预检查炉具与燃料（不调用模型）'}</button>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </section>;
}
