import {equipmentLabel,type Equipment} from './profile';

export type CookingPreparation={scope:'PREPARATION_ONLY';official_assessment:false;
  applicable?:boolean;items:{item_key:string;recorded:boolean;entered_quantity:number|null;confirmed_quantity:number|null;unit_valid:boolean}[];
  fuel_price_status:string;required_fuel_quantity?:string|null;fuel_gap?:string|null;
  calculation_status?:string;example?:{stove_quantity:number;fuel_quantity:string}|null};

export function cookingDraft(rows:{item_key:string;label:string;quantity:string;unit:string;confirmed:boolean}[]):Equipment[]{
  return rows.filter(row=>['camping_stove','fuel_canister'].includes(row.item_key)).map(row=>{
    if(row.quantity!==''&&(!/^\d+$/.test(row.quantity)||!Number.isSafeInteger(Number(row.quantity))))
      throw new Error('Enter nonnegative whole numbers for stove and fuel quantities. Leave unknown values blank.');
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
    {!stale&&shown.applicable===false?<p role="status">Meal arrangement changed. Return to the request page to review it.</p>:<>
      <p>You selected self-catering. Review your stove and fuel preparations.</p>
      <ul>{shown.items?.map(item=><li key={item.item_key}><strong>{equipmentLabel(item.item_key)}</strong>: {!item.recorded?'Quantity not entered':!item.unit_valid?'Check quantity units':item.entered_quantity===null?'Quantity not entered':`${stale?'Previously recorded':unsaved?'Entered on this page':'Recorded'} ${item.entered_quantity} items${item.confirmed_quantity===null?', Availability to confirm':''}`}
        {onFocus&&<button type="button" className="text-button" onClick={()=>onFocus(item.item_key)}>Enter{equipmentLabel(item.item_key)}Profile ↓</button>}</li>)}</ul>
      {stale&&<p role="status">Profile changed. Update the preparation details.</p>}
      {unsaved&&!stale&&<p role="status">Changes on this page are unsaved. Review the stove and fuel and save your profile. Formal results have not been updated.</p>}
      {attention&&<p role="status">The saved check still has cooking tasks. Address each issue. Entering quantities does not automatically clear formal gaps.</p>}
      {!stale&&preview?.required_fuel_quantity!=null&&<p>Estimated fuel canisters needed {preview.required_fuel_quantity} items{preview.fuel_gap!=null?`, Still missing ${preview.fuel_gap} items`:', Available quantity to confirm'}.</p>}
      {!stale&&preview?.calculation_status==='WAITING_FOR_STOVE'&&<p>Enter the available stove quantity before confirming fuel requirements.</p>}
      {!stale&&preview?.calculation_status==='UNAVAILABLE'&&<p>Fuel usage cannot yet be estimated. View the equipment list after generating a plan.</p>}
      {fuelCostPending&&<p>Fuel cost to confirm.</p>}
      {onCheck&&<button type="button" className="secondary-button" disabled={busy} onClick={onCheck}>{busy?'Updating…':'Update preparation details'}</button>}
    </>}
    {error&&<p className="error-box" role="alert">{error}</p>}
  </>;
  return <section className="clarifications" aria-label="Cooking preparation checklist"><h3>Cooking equipment preparation</h3>{content}</section>;
}
