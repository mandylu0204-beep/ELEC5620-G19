import { Link } from 'react-router-dom';
import { equipmentLabel, fixedEquipmentUnit } from './profile';
import { logisticsDestinations } from './logistics_navigation';
import { tentSummary, type TentCapacity } from './display_facts';
import { CookingPreparationPanel,type CookingPreparation } from './cooking_preparation';

export type LogisticsIssue = {tent_capacity?:TentCapacity;cooking_preparation?:CookingPreparation|null;related_equipment?:string[];issue_id:string;code:string;category:string;field:string;item_key:string|null;current:unknown;required:unknown;target:string;action_url:string|null;alternate_action_url?:string;arrangement_action_url?:string;affects?:string[];cost_impacts?:{code:string;item_key:string;category:string;unit_price_cents:null}[];pending_checks?:{item_key:string;status:string}[]};
const COPY:Record<string,[string,string]>={
  TRANSPORT_CONNECTION:['Public transport return and connection arrangements need checking','Record outbound, return and final connections in transport notes. Verify the connection-plan quantity, unit and confirmation. The system does not query actual services. Costs are return estimates, not booked tickets.'],
  TRANSPORT_ACCESS_DATA:['Insufficient public-transport access information','Public-transport access to this campsite is unconfirmed. Change the campsite or ask the project maintainer to update sources. Changing personal vehicle quantities cannot resolve this issue.'],
  OVER_BUDGET:['Adjust budget or reduce costs','The estimate exceeds your confirmed budget. Keep the budget and try a campsite with lower fees, then recalculate the full cost. This does not guarantee the total fits the budget. Budget changes require request reconfirmation.'],
  MEAL_CHOICE:['Select meal arrangement','Select ready-to-eat meals or self-catering. This affects food costs, stove and fuel requirements.'],
  COOKING_ARRANGEMENT:['Confirm cooking arrangements','Self-catering is selected but no available stove is verified. Register actual available stoves and quantities. If you will not cook, select ready-to-eat meals instead.'],
  DISTANCE:['Add estimated total distance','Enter total kilometres for all vehicles over the whole trip to calculate transport costs.'],
  VEHICLE_COUNT:['Verify vehicle quantities','Enter and confirm available vehicle quantities in transport arrangements. The system totals them for parking costs.'],
  TRANSPORT_MODE:['Specify transport mode','Select car or public transport. Notes alone cannot establish a feasible transport arrangement.'],
  VEHICLE_DETAILS:['Verify vehicle quantities and seating','Enter vehicle quantities and seats per vehicle, including the driver, and confirm availability for this trip.'],
  TRANSPORT_CAPACITY:['Insufficient vehicle seats','Provide actual available transport or adjust group size. Do not increase capacity merely to pass checks.'],
  CHILDREN:['Add child details','Specify whether children are travelling and include their count within the total group size.'],
  EXPERIENCE:['Add camping experience','Some equipment requirements depend on experience. Select it in group details.'],
  EQUIPMENT_DETAILS:['Review equipment information','Check quantities, units and verification. Tents and vehicles also require capacity per item.'],
  EQUIPMENT_SHORTAGE:['Essential equipment quantity insufficient','Add equipment based on actual arrangements. Planned purchases or loans do not count as owned. You can also adjust trip requirements.'],
  WEATHER_DATA:['Weather information is not applicable yet','This is a source coverage issue. You do not need to enter weather. View date coverage and suggested recheck time under Safety.'],
  PRICE_DATA:['No applicable price reference','No applicable unit price is available. Editing your profile cannot supply a price. If the equipment is already available, a new check using the updated profile may remove the gap cost. Otherwise adjust arrangements or ask the maintainer to update prices.'],
  COST_QUANTITY:['Incomplete cost calculation basis','The system has not identified a specific field you can complete. Contact the maintainer to inspect the calculation. Do not repeatedly change unrelated details.'],
  TRANSPORT_ACCESS:['Current transport does not support this campsite','Change transport arrangements or choose another campsite. Reconfirm requirements and run checks after updating details.'],
  SOURCE_DATA:['System information needs completion','Applicable sources or rules are missing and require maintainer action. Editing your profile cannot replace a data repair.'],
  UNCLASSIFIED:['Check incomplete; cause needs investigation','No specific missing field has been identified. You should not be asked to change your profile yet. Contact the maintainer to inspect the plan.'],
};

function factText(value:unknown):string {
  if(value==null)return 'Unknown';
  if(typeof value!=='object')return typeof value==='boolean'?(value?'Yes':'No'):
    ({FOOD:'Food',WATER:'Drinking water',TRANSPORT:'Transport',CAMPSITE:'Campsite',ADDITIONAL_GEAR:'Additional equipment',CAR:'Car',PUBLIC_TRANSPORT:'Public transport',BEGINNER:'Beginner',INTERMEDIATE:'Some experience',EXPERIENCED:'Experienced',ADVANCED:'Advanced'} as Record<string,string>)[String(value)]??String(value);
  if(Array.isArray(value))return value.map(factText).join('; ');
  const row=value as Record<string,unknown>;
  if('records' in row){
    const records=row.records as {quantity:number|null;capacity_persons:number|null;confirmed:boolean;unit:string}[];
    return records.length?records.map(item=>`Quantity ${item.quantity??'Unknown'}, Unit ${({item:'items',vehicle:'vehicles',litre:'litres',portion:'portions',set:'sets',plan:'plans'} as Record<string,string>)[item.unit]??'To review'}, People accommodated per item ${item.capacity_persons??'Not entered'}, ${item.confirmed?'Verified':'Unverified'}`).join('; '):'Equipment not registered yet';
  }
  const names:Record<string,string>={quantity:'Required quantity',missing_quantity:'Shortfall',capacity_persons:'Required person capacity',registered_vehicle_count:'Recorded vehicle quantity',has_children:'Children included',children_count:'Number of children',experience_level:'Camping experience',category:'Cost category',unit_price_cents:'Unit price'};
  return Object.entries(row).filter(([key,v])=>v!=null&&names[key]).map(([key,v])=>`${names[key]}: ${factText(v)}`).join('; ')||'Unknown';
}

type EquipmentRecord={quantity?:unknown;unit?:string;capacity_persons?:unknown;confirmed?:boolean};
function quantity(value:unknown):string|null {
  const text=typeof value==='number'&&Number.isFinite(value)?String(value):typeof value==='string'?value:'';
  return /^\d+(?:\.\d+)?$/.test(text)?text.replace(/\.0+$/,''):null;
}
function equipmentCopy(item:LogisticsIssue){
  const name=equipmentLabel(item.item_key!);
  const current=(item.current??{}) as {records?:EquipmentRecord[];available_quantity?:unknown;unit?:string};
  const required=(item.required??{}) as {quantity?:unknown;missing_quantity?:unknown;capacity_persons?:unknown};
  const records=Array.isArray(current.records)?current.records:[];
  const unit=current.unit??fixedEquipmentUnit(item.item_key!);
  const suffix=unit==='item'?({sleeping_mat:'mats',sleeping_bag:'bags',fuel_canister:'canisters',first_aid_kit:'packs',warm_layers:'items'} as Record<string,string>)[item.item_key!]??'items'
    :({litre:'litres',portion:'portions',vehicle:'vehicles',set:'sets',plan:'plans',person_space:'people capacity'} as Record<string,string>)[unit??'']??'';
  const needed=quantity(required.quantity),available=quantity(current.available_quantity),missing=quantity(required.missing_quantity);
  const positive=(value:string|null)=>value!==null&&/[1-9]/.test(value);
  if(item.item_key==='tent'){
    const tent=item.tent_capacity;
    const gap=quantity(tent?.missing_person_spaces??(unit==='person_space'?required.missing_quantity:null));
    const capacity=quantity(tent?.required_person_spaces??required.capacity_persons);
    const assessed=quantity(tent?.assessed_capacity??current.available_quantity);
    return {title:positive(gap)?`Tent shortfall: ${gap} sleeping places`:'Tent capacity to confirm',
      detail:`${capacity!==null?`Needed for this trip ${capacity} sleeping places`:'Required sleeping capacity to confirm'}, ${assessed!==null?`Confirmed available ${assessed} people.`:'Available capacity is unknown.'}`,
      hint:'Enter tent quantities and capacity per tent, and confirm availability for this trip.',action:'Complete tent details'};
  }
  if(item.item_key==='vehicle'||['VEHICLE_DETAILS','VEHICLE_COUNT','TRANSPORT_CAPACITY'].includes(item.code)){
    const people=quantity(required.capacity_persons);
    return {title:unit==='person_space'&&positive(missing)?`Vehicle shortfall: ${missing} seats`:'Vehicle arrangements to confirm',
      detail:`${people!==null?`Capacity needed this trip: ${people} people.`:''}Enter vehicle quantities and seats per vehicle including the driver, and confirm availability for this trip.`,hint:null,action:'Provide transport arrangements'};
  }
  const unconfirmed=records.some(record=>record.confirmed!==true);
  return {title:positive(missing)?`${name} shortage: ${missing} ${suffix}`:needed===null?`${name}: required quantity to confirm`:`Complete ${name} details`,
    detail:`${needed!==null?`Needed for this trip ${needed} ${suffix}`:'Required quantity is unknown'}, ${!records.length?'Not registered yet.':available!==null?`Confirmed available ${available} ${suffix}.`:'Available quantity is unknown.'}`,
    hint:positive(missing)?unconfirmed?'Confirm whether registered items are available for this trip.':null:'Check quantities and units, and confirm availability for this trip.',action:`Complete ${name}`};
}

function EquipmentIssue({item,disabled}:{item:LogisticsIssue;disabled:boolean}){
  const copy=equipmentCopy(item);
  return <article className="logistics-todo">
    <h3>{copy.title}</h3><p>{copy.detail}</p>{copy.hint&&<p className="muted">{copy.hint}</p>}
    {!!item.cost_impacts?.length&&<p className="muted">{[...new Set(item.cost_impacts.map(cost=>equipmentLabel(cost.item_key)))].join(', ')} cost is unknown; the full total cannot yet be estimated.</p>}
    {!!item.pending_checks?.length&&<p className="muted">Complete, then review: {[...new Set(item.pending_checks.map(check=>equipmentLabel(check.item_key)))].join(', ')}, Required quantity is unknown.</p>}
    {!disabled&&<div className="plan-actions">
      {item.action_url&&<Link className="text-link" to={item.action_url}>{copy.action} ↗</Link>}
      {item.arrangement_action_url&&<Link className="text-link" to={item.arrangement_action_url}>Adjust meal arrangement ↗</Link>}
    </div>}
  </article>;
}

export function LogisticsIssues({items,onSafety,disabled=false,summary=false,onGear,onRevisionRequested}:{items:LogisticsIssue[];onSafety:()=>void;disabled?:boolean;summary?:boolean;onGear?:()=>void;onRevisionRequested?:(goal:'cheaper campsite')=>void}) {
  if(!items.length)return null;
  if(summary){
    const groups=new Map<string,LogisticsIssue[]>();
    items.forEach(item=>{const key=item.item_key??item.field??item.code;groups.set(key,[...(groups.get(key)??[]),item]);});
    return <section aria-label="Equipment issue summary"><h3>There are also {groups.size} preparation items need attention</h3>
      <ul>{[...groups].map(([key,issues])=>{const item=issues[0];return <li key={key}>
        <strong>{item.item_key?equipmentLabel(item.item_key):(COPY[item.code]??COPY.UNCLASSIFIED)[0]}</strong>
        {item.item_key==='tent'&&item.tent_capacity?`: ${tentSummary(item.tent_capacity)}`:''}
      </li>;})}</ul>
      {onGear&&<button type="button" className="secondary-button" onClick={onGear}>View and update equipment ↗</button>}
    </section>;
  }
  const destinations=logisticsDestinations(items);
  return <section className="panel logistics-todos" aria-label="Specific tasks"><div className="logistics-todos-heading"><h2>Address these issues</h2>
    {!disabled&&<div className="logistics-todos-actions">{destinations.profile&&<Link className="secondary-button" to={destinations.profile}>Go to relevant profile details ↗</Link>}{destinations.request&&<Link className="secondary-button" to={destinations.request}>Adjust camping requirements ↗</Link>}{destinations.safety&&<button className="secondary-button" onClick={onSafety}>View safety information</button>}</div>}</div>
    <p>Complete the details, review changes and update the plan.</p>
    {disabled&&<p className="muted">This is historical or checks are still running. Only gaps recorded at that time are shown.</p>}
    {items.map(item=>{if((item.item_key&&['EQUIPMENT_SHORTAGE','EQUIPMENT_DETAILS'].includes(item.code))||['VEHICLE_DETAILS','VEHICLE_COUNT','TRANSPORT_CAPACITY'].includes(item.code))return <EquipmentIssue key={item.issue_id} item={item} disabled={disabled}/>;
      const [title,body]=COPY[item.code]??COPY.UNCLASSIFIED;return <article className="logistics-todo" key={item.issue_id}>
      <span className="tag">{item.code==='OVER_BUDGET'?'Arrangements need changes':item.category==='USER_INPUT'?'Information needed':item.category==='EQUIPMENT_GAP'?'Arrangements need changes':'System data issue'}</span>
      <h3>{item.item_key==='tent'?'Total tent sleeping capacity needs review':item.item_key&&equipmentLabel(item.item_key)!==item.item_key?equipmentLabel(item.item_key)+' · '+title:title}</h3>
      <p><strong>Issue:</strong>{item.item_key==='tent'&&item.tent_capacity?tentSummary(item.tent_capacity):title}</p>
      <p><strong>Impact:</strong>Confirmed information and checks still have gaps. The final plan cannot be saved yet.</p><p><strong>Action:</strong>{body}</p>
      <CookingPreparationPanel value={item.cooking_preparation} attention/>
      {item.item_key!=='tent'&&(item.current!=null||['DISTANCE','VEHICLE_COUNT','TRANSPORT_MODE'].includes(item.code))&&<p className="muted">Used for this check: {item.code==='OVER_BUDGET'?`AUD ${(Number(item.current)/100).toFixed(2)}`:factText(item.current)}</p>}
      {item.item_key!=='tent'&&item.required!=null&&<p className="muted">Trip requirement: {item.code==='OVER_BUDGET'?`Budget AUD ${(Number(item.required)/100).toFixed(2)}`:factText(item.required)}</p>}
      {!!item.cost_impacts?.length&&<div className="clarifications" aria-label="Related cost"><strong>Related cost, not a separate unrelated task</strong>{item.cost_impacts.map((cost,index)=><p key={index}>{equipmentLabel(cost.item_key)}The gap cost cannot be estimated because no applicable unit price exists. The full total is unknown. If the equipment is available, a new check using updated details can remove this gap cost. Unknown costs must not be treated as zero.</p>)}</div>}
      {!!item.pending_checks?.length?<p className="muted">Still to clarify: {item.pending_checks.map(check=>equipmentLabel(check.item_key)).join(', ')}.These items depend on this information or choice. Specific requirements remain unknown and still require formal checks after completion.</p>:!!item.affects?.length&&<p className="muted">This gap also affects: {item.affects.map(field=>field.startsWith('equipment.')?equipmentLabel(field.split('.')[1])+' requirements and costs':'Related costs').join(', ')}.Complete this item first, then check again.</p>}
      {!disabled&&<div className="plan-actions">
        {item.code==='OVER_BUDGET'&&onRevisionRequested&&<button type="button" className="secondary-button" onClick={()=>onRevisionRequested('cheaper campsite')}>Keep budget and look for a lower-cost plan</button>}
        {item.action_url&&<Link className="text-link" to={item.action_url}>{item.target==='PROFILE'?`Review ${item.item_key?equipmentLabel(item.item_key):'profile'} details`:item.code==='OVER_BUDGET'?'Adjust this trip budget':'Adjust meals for this trip'} ↗</Link>}
        {item.alternate_action_url&&<Link className="text-link" to={item.alternate_action_url}>{item.cooking_preparation?'Check stove and fuel details together':'Review stove details'} ↗</Link>}
        {item.arrangement_action_url&&<Link className="text-link" to={item.arrangement_action_url}>Adjust meals for this trip ↗</Link>}
        {item.target==='SAFETY'&&<button className="text-button" onClick={onSafety}>View source coverage and safety information</button>}
      </div>}
      {item.code==='OVER_BUDGET'&&!disabled&&<p className="muted">{onRevisionRequested?'The cost-reduction option opens revision settings first. Execution starts only after confirmation. Cost priorities change budget allocation, not prices.':'Campsite revision cannot start now. Check run status first; do not increase the budget merely to continue.'}</p>}
    </article>;})}
  </section>;
}
