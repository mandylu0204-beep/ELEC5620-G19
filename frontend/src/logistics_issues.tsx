import { Link } from 'react-router-dom';
import { equipmentLabel, fixedEquipmentUnit } from './profile';
import { logisticsDestinations } from './logistics_navigation';
import { tentSummary, type TentCapacity } from './display_facts';
import { CookingPreparationPanel,type CookingPreparation } from './cooking_preparation';

export type LogisticsIssue = {tent_capacity?:TentCapacity;cooking_preparation?:CookingPreparation|null;related_equipment?:string[];issue_id:string;code:string;category:string;field:string;item_key:string|null;current:unknown;required:unknown;target:string;action_url:string|null;alternate_action_url?:string;arrangement_action_url?:string;affects?:string[];cost_impacts?:{code:string;item_key:string;category:string;unit_price_cents:null}[];pending_checks?:{item_key:string;status:string}[]};
const COPY:Record<string,[string,string]>={
  TRANSPORT_CONNECTION:['公共交通往返及接驳安排待核对','请在交通说明中记录去程、返程和最后接驳安排，并核对交通连接计划的数量、单位及确认状态。系统不查询实际班次，费用是模拟往返参考，不能视为已订票。'],
  TRANSPORT_ACCESS_DATA:['营地公共交通可达资料不足','系统没有确认该营地的公共交通可达性。请调整营地安排，或由项目负责人维护来源资料；修改个人车辆数量不能解决这个问题。'],
  OVER_BUDGET:['调整预算或降低费用','估算超过已确认预算。可保持预算，尝试寻找营地费更低的方案，再重新计算完整费用；这不保证总费用已在预算内。如修改预算，必须重新确认需求。'],
  MEAL_CHOICE:['选择用餐方式','请选择即食餐食或自行烹饪。这会影响食物费用、炉具和燃料需求。'],
  COOKING_ARRANGEMENT:['确认烹饪安排','已选择自行烹饪，但没有核实可用的炉具。请登记真实可用的炉具和数量；如果不做饭，也可改选即食餐食。'],
  DISTANCE:['补充全程预计公里数','请填写所有车辆在整个行程中的行车总公里数，用于计算交通费用。'],
  VEHICLE_COUNT:['核对车辆数量','请在交通安排中填写实际可用车辆的数量并确认，系统会自动汇总，用于计算停车费用。'],
  TRANSPORT_MODE:['明确交通方式','请选择汽车或公共交通；目前无法根据备注推断可行的交通安排。'],
  VEHICLE_DETAILS:['核对车辆数量及载客容量','请在交通安排中填写车辆数量、每辆载客人数（含驾驶员），并确认车辆可用于本次出行。'],
  TRANSPORT_CAPACITY:['车辆座位不足','请补充真实可用的交通安排，或调整同行人数；不要只为了通过检查而增大容量。'],
  CHILDREN:['补充儿童情况','请选择是否有儿童；如有，请填写计入小组总人数的儿童人数。'],
  EXPERIENCE:['补充露营经验','部分装备需求取决于露营经验，请在同行资料中选择。'],
  EQUIPMENT_DETAILS:['核对装备资料','请核对数量、单位及已核实状态。帐篷和车辆还需要每件人数容量。'],
  EQUIPMENT_SHORTAGE:['必要装备数量不足','请根据真实安排补充装备。拟购买或借用还不等于已经拥有，也可以调整行程需求。'],
  WEATHER_DATA:['天气资料尚不适用','这是系统资料的覆盖问题，不需要你填写天气。请查看安全信息中的日期范围和建议检查时间。'],
  PRICE_DATA:['系统缺少适用报价','系统没有这项费用的适用单价，不能通过填写个人资料补出单价。若相关装备实际已备齐，采用新资料重新检查后可能不再需要这项补缺费用；否则需调整安排或由项目负责人维护报价。'],
  COST_QUANTITY:['费用计算依据不完整','系统尚未定位到可由你补充的具体字段，请联系项目负责人检查计算依据；不要反复修改无关资料。'],
  TRANSPORT_ACCESS:['当前交通安排不支持该营地','请调整交通安排或选择其他营地；资料更新后需重新确认需求和检查。'],
  SOURCE_DATA:['系统资料需要补充','这项检查缺少适用的来源或规则数据，需要项目负责人处理。修改个人资料不能代替数据修复。'],
  UNCLASSIFIED:['检查未完成，原因需要核对','系统尚未定位到具体缺项，暂不能要求你修改个人资料。请联系项目负责人检查该方案。'],
};

function factText(value:unknown):string {
  if(value==null)return '未知';
  if(typeof value!=='object')return typeof value==='boolean'?(value?'是':'否'):
    ({FOOD:'食物',WATER:'饮水',TRANSPORT:'交通',CAMPSITE:'营地',ADDITIONAL_GEAR:'新增装备',CAR:'汽车',PUBLIC_TRANSPORT:'公共交通',BEGINNER:'初学者',INTERMEDIATE:'有一定经验',EXPERIENCED:'经验丰富',ADVANCED:'熟练'} as Record<string,string>)[String(value)]??String(value);
  if(Array.isArray(value))return value.map(factText).join('；');
  const row=value as Record<string,unknown>;
  if('records' in row){
    const records=row.records as {quantity:number|null;capacity_persons:number|null;confirmed:boolean;unit:string}[];
    return records.length?records.map(item=>`数量 ${item.quantity??'未知'}，单位 ${({item:'件',vehicle:'辆',litre:'升',portion:'份',set:'套',plan:'份计划'} as Record<string,string>)[item.unit]??'待核对'}，每件人数容量 ${item.capacity_persons??'未填写'}，${item.confirmed?'已核实':'未核实'}`).join('；'):'尚未登记此装备';
  }
  const names:Record<string,string>={quantity:'所需数量',missing_quantity:'缺口',capacity_persons:'所需人数容量',registered_vehicle_count:'已登记车辆数量',has_children:'有儿童',children_count:'儿童人数',experience_level:'露营经验',category:'费用类别',unit_price_cents:'单价'};
  return Object.entries(row).filter(([key,v])=>v!=null&&names[key]).map(([key,v])=>`${names[key]}：${factText(v)}`).join('；')||'未知';
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
  const suffix=unit==='item'?({sleeping_mat:'张',sleeping_bag:'条',fuel_canister:'罐',first_aid_kit:'包',warm_layers:'件'} as Record<string,string>)[item.item_key!]??'件'
    :({litre:'升',portion:'份',vehicle:'辆',set:'套',plan:'份计划',person_space:'人容量'} as Record<string,string>)[unit??'']??'';
  const needed=quantity(required.quantity),available=quantity(current.available_quantity),missing=quantity(required.missing_quantity);
  const positive=(value:string|null)=>value!==null&&/[1-9]/.test(value);
  if(item.item_key==='tent'){
    const tent=item.tent_capacity;
    const gap=quantity(tent?.missing_person_spaces??(unit==='person_space'?required.missing_quantity:null));
    const capacity=quantity(tent?.required_person_spaces??required.capacity_persons);
    const assessed=quantity(tent?.assessed_capacity??current.available_quantity);
    return {title:positive(gap)?`帐篷还缺 ${gap} 人住宿容量`:'帐篷容量待确认',
      detail:`${capacity!==null?`本次需要 ${capacity} 人住宿容量`:'本次所需住宿容量待确认'}，${assessed!==null?`已确认可用 ${assessed} 人。`:'可用容量尚未确定。'}`,
      hint:'请填写帐篷数量、每顶可住人数，并确认本次可用。',action:'补充帐篷资料'};
  }
  if(item.item_key==='vehicle'||['VEHICLE_DETAILS','VEHICLE_COUNT','TRANSPORT_CAPACITY'].includes(item.code)){
    const people=quantity(required.capacity_persons);
    return {title:unit==='person_space'&&positive(missing)?`车辆还缺 ${missing} 个座位`:'车辆安排待确认',
      detail:`${people!==null?`本次需容纳 ${people} 人。`:''}请填写车辆数量和每辆载客人数（含驾驶员），并确认本次可用。`,hint:null,action:'补充交通安排'};
  }
  const unconfirmed=records.some(record=>record.confirmed!==true);
  return {title:positive(missing)?`${name}还缺 ${missing} ${suffix}`:needed===null?`${name}所需数量待确认`:`请补充${name}资料`,
    detail:`${needed!==null?`本次需要 ${needed} ${suffix}`:'本次所需数量尚未确定'}，${!records.length?'目前尚未登记。':available!==null?`已确认可用 ${available} ${suffix}。`:'可用数量尚未确定。'}`,
    hint:positive(missing)?unconfirmed?'请确认已登记的物品本次是否可用。':null:'请核对数量、单位，并确认本次可用。',action:`补充${name}`};
}

function EquipmentIssue({item,disabled}:{item:LogisticsIssue;disabled:boolean}){
  const copy=equipmentCopy(item);
  return <article className="logistics-todo">
    <h3>{copy.title}</h3><p>{copy.detail}</p>{copy.hint&&<p className="muted">{copy.hint}</p>}
    {!!item.cost_impacts?.length&&<p className="muted">{[...new Set(item.cost_impacts.map(cost=>equipmentLabel(cost.item_key)))].join('、')}费用待确认，完整总费用暂无法估算。</p>}
    {!!item.pending_checks?.length&&<p className="muted">补充后再核对：{[...new Set(item.pending_checks.map(check=>equipmentLabel(check.item_key)))].join('、')}，所需数量待确认。</p>}
    {!disabled&&<div className="plan-actions">
      {item.action_url&&<Link className="text-link" to={item.action_url}>{copy.action} ↗</Link>}
      {item.arrangement_action_url&&<Link className="text-link" to={item.arrangement_action_url}>调整用餐方式 ↗</Link>}
    </div>}
  </article>;
}

export function LogisticsIssues({items,onSafety,disabled=false,summary=false,onGear,onRevisionRequested}:{items:LogisticsIssue[];onSafety:()=>void;disabled?:boolean;summary?:boolean;onGear?:()=>void;onRevisionRequested?:(goal:'cheaper campsite')=>void}) {
  if(!items.length)return null;
  if(summary){
    const groups=new Map<string,LogisticsIssue[]>();
    items.forEach(item=>{const key=item.item_key??item.field??item.code;groups.set(key,[...(groups.get(key)??[]),item]);});
    return <section aria-label="装备问题摘要"><h3>还有 {groups.size} 项准备需要完善</h3>
      <ul>{[...groups].map(([key,issues])=>{const item=issues[0];return <li key={key}>
        <strong>{item.item_key?equipmentLabel(item.item_key):(COPY[item.code]??COPY.UNCLASSIFIED)[0]}</strong>
        {item.item_key==='tent'&&item.tent_capacity?`：${tentSummary(item.tent_capacity)}`:''}
      </li>;})}</ul>
      {onGear&&<button type="button" className="secondary-button" onClick={onGear}>查看并补充装备 ↗</button>}
    </section>;
  }
  const destinations=logisticsDestinations(items);
  return <section className="panel logistics-todos" aria-label="具体待办事项"><div className="logistics-todos-heading"><h2>逐项处理这些问题</h2>
    {!disabled&&<div className="logistics-todos-actions">{destinations.profile&&<Link className="secondary-button" to={destinations.profile}>前往对应资料 ↗</Link>}{destinations.request&&<Link className="secondary-button" to={destinations.request}>调整露营需求 ↗</Link>}{destinations.safety&&<button className="secondary-button" onClick={onSafety}>查看安全信息</button>}</div>}</div>
    <p>补充资料后，核对修改并更新方案。</p>
    {disabled&&<p className="muted">当前为历史记录或检查尚未结束，这里只展示当时的缺项。</p>}
    {items.map(item=>{if((item.item_key&&['EQUIPMENT_SHORTAGE','EQUIPMENT_DETAILS'].includes(item.code))||['VEHICLE_DETAILS','VEHICLE_COUNT','TRANSPORT_CAPACITY'].includes(item.code))return <EquipmentIssue key={item.issue_id} item={item} disabled={disabled}/>;
      const [title,body]=COPY[item.code]??COPY.UNCLASSIFIED;return <article className="logistics-todo" key={item.issue_id}>
      <span className="tag">{item.code==='OVER_BUDGET'?'需要调整安排':item.category==='USER_INPUT'?'需要补充信息':item.category==='EQUIPMENT_GAP'?'需要调整安排':'系统资料问题'}</span>
      <h3>{item.item_key==='tent'?'帐篷总住宿容量需要核对':item.item_key&&equipmentLabel(item.item_key)!==item.item_key?equipmentLabel(item.item_key)+' · '+title:title}</h3>
      <p><strong>问题：</strong>{item.item_key==='tent'&&item.tent_capacity?tentSummary(item.tent_capacity):title}</p>
      <p><strong>影响：</strong>本次确认资料与检查仍有缺项，暂不能保存最终方案。</p><p><strong>处理：</strong>{body}</p>
      <CookingPreparationPanel value={item.cooking_preparation}/>
      {item.item_key!=='tent'&&(item.current!=null||['DISTANCE','VEHICLE_COUNT','TRANSPORT_MODE'].includes(item.code))&&<p className="muted">本次采用：{item.code==='OVER_BUDGET'?`AUD ${(Number(item.current)/100).toFixed(2)}`:factText(item.current)}</p>}
      {item.item_key!=='tent'&&item.required!=null&&<p className="muted">此行程需要：{item.code==='OVER_BUDGET'?`预算 AUD ${(Number(item.required)/100).toFixed(2)}`:factText(item.required)}</p>}
      {!!item.cost_impacts?.length&&<div className="clarifications" aria-label="关联费用"><strong>关联费用，不是另一项无关任务</strong>{item.cost_impacts.map((cost,index)=><p key={index}>{equipmentLabel(cost.item_key)}补缺费用暂无法估算：系统暂无适用单价，完整总费用仍未知。若实际已备齐，采用新资料重新检查后不再需要估算这项补缺费用；不能把未知费用当作零元。</p>)}</div>}
      {!!item.pending_checks?.length?<p className="muted">后续尚待明确：{item.pending_checks.map(check=>equipmentLabel(check.item_key)).join('、')}。这些项目依赖本项资料／选择，暂不能确定具体需求；补充后仍需正式检查。</p>:!!item.affects?.length&&<p className="muted">这个缺项同时影响：{item.affects.map(field=>field.startsWith('equipment.')?equipmentLabel(field.split('.')[1])+'的需求及费用':'相关费用').join('、')}。先补充此项后再检查。</p>}
      {!disabled&&<div className="plan-actions">
        {item.code==='OVER_BUDGET'&&onRevisionRequested&&<button type="button" className="secondary-button" onClick={()=>onRevisionRequested('cheaper campsite')}>保持预算，寻找更低费用方案</button>}
        {item.action_url&&<Link className="text-link" to={item.action_url}>{item.target==='PROFILE'?`核对${item.item_key?equipmentLabel(item.item_key):'对应'}资料`:item.code==='OVER_BUDGET'?'调整本次预算':'调整本次用餐方式'} ↗</Link>}
        {item.alternate_action_url&&<Link className="text-link" to={item.alternate_action_url}>{item.cooking_preparation?'一起核对炉具与燃料资料':'核对炉具资料'} ↗</Link>}
        {item.arrangement_action_url&&<Link className="text-link" to={item.arrangement_action_url}>调整本次用餐方式 ↗</Link>}
        {item.target==='SAFETY'&&<button className="text-button" onClick={onSafety}>查看资料覆盖与安全信息</button>}
      </div>}
      {item.code==='OVER_BUDGET'&&!disabled&&<p className="muted">{onRevisionRequested?'降费入口会先打开修订设置；确认后才执行。费用优先级只改变预算分配，不会自动降价。':'当前不能启动营地修订。请先查看运行状态；不要仅为继续操作而提高预算。'}</p>}
    </article>;})}
  </section>;
}
