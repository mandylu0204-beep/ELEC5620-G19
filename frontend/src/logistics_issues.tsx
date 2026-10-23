import { Link } from 'react-router-dom';
import { equipmentLabel } from './profile';
import { logisticsDestinations } from './logistics_navigation';
import { tentSummary, type TentCapacity } from './display_facts';
import { CookingPreparationPanel,type CookingPreparation } from './cooking_preparation';

export type LogisticsIssue = {tent_capacity?:TentCapacity;cooking_preparation?:CookingPreparation|null;related_equipment?:string[];issue_id:string;code:string;category:string;field:string;item_key:string|null;current:unknown;required:unknown;target:string;action_url:string|null;alternate_action_url?:string;arrangement_action_url?:string;affects?:string[];cost_impacts?:{code:string;item_key:string;category:string;unit_price_cents:null}[];pending_checks?:{item_key:string;status:string}[]};
const COPY:Record<string,[string,string]>={
  OVER_BUDGET:['调整预算或降低费用','估算超过已确认预算。可选择更低成本方案；如修改预算，必须重新确认需求。'],
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

export function LogisticsIssues({items,onSafety,disabled=false,summary=false,onGear}:{items:LogisticsIssue[];onSafety:()=>void;disabled?:boolean;summary?:boolean;onGear?:()=>void}) {
  if(!items.length)return null;
  if(summary)return <section aria-label="装备问题摘要"><h3>装备与交通问题</h3><ul>{items.map(item=><li key={item.issue_id}>
    {item.item_key==='tent'&&item.tent_capacity?tentSummary(item.tent_capacity):(COPY[item.code]??COPY.UNCLASSIFIED)[0]} → 暂不能保存最终方案 → {(COPY[item.code]??COPY.UNCLASSIFIED)[1]}
  </li>)}</ul><button type="button" className="secondary-button" onClick={onGear}>查看装备问题与补充入口</button></section>;
  const destinations=logisticsDestinations(items);
  return <section className="panel logistics-todos" aria-label="具体待办事项"><div className="logistics-todos-heading"><h2>逐项处理这些问题</h2>
    {!disabled&&<div className="logistics-todos-actions">{destinations.profile&&<Link className="secondary-button" to={destinations.profile}>前往对应资料 ↗</Link>}{destinations.request&&<Link className="secondary-button" to={destinations.request}>调整露营需求 ↗</Link>}{destinations.safety&&<button className="secondary-button" onClick={onSafety}>查看安全信息</button>}</div>}</div>
    <p>先处理可确认的资料，再核对关联装备和费用。保存后请核对本次更新并明确启动检查；旧检查不会因填写表单而自动通过。</p>
    {disabled&&<p className="muted">当前为历史记录或检查尚未结束，这里只展示当时的缺项。</p>}
    {items.map(item=>{const [title,body]=COPY[item.code]??COPY.UNCLASSIFIED;return <article className="logistics-todo" key={item.issue_id}>
      <span className="tag">{item.category==='USER_INPUT'?'需要补充信息':item.category==='EQUIPMENT_GAP'?'需要调整安排':'系统资料问题'}</span>
      <h3>{item.item_key==='tent'?'帐篷总住宿容量需要核对':item.item_key&&equipmentLabel(item.item_key)!==item.item_key?equipmentLabel(item.item_key)+' · '+title:title}</h3>
      <p><strong>问题：</strong>{item.item_key==='tent'&&item.tent_capacity?tentSummary(item.tent_capacity):title}</p>
      <p><strong>影响：</strong>本次确认资料与检查仍有缺项，暂不能保存最终方案。</p><p><strong>处理：</strong>{body}</p>
      <CookingPreparationPanel value={item.cooking_preparation}/>
      {item.item_key!=='tent'&&(item.current!=null||['DISTANCE','VEHICLE_COUNT','TRANSPORT_MODE'].includes(item.code))&&<p className="muted">本次采用：{item.code==='OVER_BUDGET'?`AUD ${(Number(item.current)/100).toFixed(2)}`:factText(item.current)}</p>}
      {item.item_key!=='tent'&&item.required!=null&&<p className="muted">此行程需要：{item.code==='OVER_BUDGET'?`预算 AUD ${(Number(item.required)/100).toFixed(2)}`:factText(item.required)}</p>}
      {!!item.cost_impacts?.length&&<div className="clarifications" aria-label="关联费用"><strong>关联费用，不是另一项无关任务</strong>{item.cost_impacts.map((cost,index)=><p key={index}>{equipmentLabel(cost.item_key)}补缺费用暂无法估算：系统暂无适用单价，完整总费用仍未知。若实际已备齐，采用新资料重新检查后不再需要估算这项补缺费用；不能把未知费用当作零元。</p>)}</div>}
      {!!item.pending_checks?.length?<p className="muted">后续尚待明确：{item.pending_checks.map(check=>equipmentLabel(check.item_key)).join('、')}。这些项目依赖本项资料／选择，暂不能确定具体需求；补充后仍需正式检查。</p>:!!item.affects?.length&&<p className="muted">这个缺项同时影响：{item.affects.map(field=>field.startsWith('equipment.')?equipmentLabel(field.split('.')[1])+'的需求及费用':'相关费用').join('、')}。先补充此项后再检查。</p>}
      {!disabled&&<div className="plan-actions">
        {item.action_url&&<Link className="text-link" to={item.action_url}>{item.target==='PROFILE'?`核对${item.item_key?equipmentLabel(item.item_key):'对应'}资料`:item.code==='OVER_BUDGET'?'调整本次预算':'调整本次用餐方式'} ↗</Link>}
        {item.alternate_action_url&&<Link className="text-link" to={item.alternate_action_url}>{item.cooking_preparation?'一起核对炉具与燃料资料':'核对炉具资料'} ↗</Link>}
        {item.arrangement_action_url&&<Link className="text-link" to={item.arrangement_action_url}>调整本次用餐方式 ↗</Link>}
        {item.target==='SAFETY'&&<button className="text-button" onClick={onSafety}>查看资料覆盖与安全信息</button>}
      </div>}
    </article>;})}
  </section>;
}
