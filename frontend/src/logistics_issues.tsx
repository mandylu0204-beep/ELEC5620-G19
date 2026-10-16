import { Link } from 'react-router-dom';
import { equipmentLabel } from './profile';
import { logisticsDestinations } from './logistics_navigation';

export type LogisticsIssue = {issue_id:string;code:string;category:string;field:string;item_key:string|null;current:unknown;required:unknown;target:string;action_url:string|null;alternate_action_url?:string;affects?:string[]};
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
  PRICE_DATA:['系统缺少适用报价','系统未提供这项必要费用的有效单价，修改个人资料无法补齐报价。可调整安排，或联系项目负责人补充资料。'],
  COST_QUANTITY:['费用计算依据不完整','系统尚未定位到可由你补充的具体字段，请联系项目负责人检查计算依据；不要反复修改无关资料。'],
  TRANSPORT_ACCESS:['当前交通安排不支持该营地','请调整交通安排或选择其他营地；资料更新后需重新确认需求和检查。'],
  SOURCE_DATA:['系统资料需要补充','这项检查缺少适用的来源或规则数据，需要项目负责人处理。修改个人资料不能代替数据修复。'],
  UNCLASSIFIED:['检查未完成，原因需要核对','系统尚未定位到具体缺项，暂不能要求你修改个人资料。请联系项目负责人检查该方案。'],
};

function factText(value:unknown):string {
  if(value==null)return '未知';
  if(typeof value!=='object')return typeof value==='boolean'?(value?'是':'否'):String(value);
  if(Array.isArray(value))return value.map(factText).join('；');
  const row=value as Record<string,unknown>;
  if('records' in row){
    const records=row.records as {quantity:number|null;capacity_persons:number|null;confirmed:boolean;unit:string}[];
    return records.length?records.map(item=>`数量 ${item.quantity??'未知'}，单位 ${({item:'件',vehicle:'辆',litre:'升',portion:'份',set:'套',plan:'份计划'} as Record<string,string>)[item.unit]??item.unit}，每件人数容量 ${item.capacity_persons??'未填写'}，${item.confirmed?'已核实':'未核实'}`).join('；'):'尚未登记此装备';
  }
  const names:Record<string,string>={quantity:'所需数量',missing_quantity:'缺口',capacity_persons:'所需人数容量',registered_vehicle_count:'已登记车辆数量',has_children:'有儿童',children_count:'儿童人数',experience_level:'露营经验',category:'费用类别',unit_price_cents:'单价'};
  return Object.entries(row).filter(([,v])=>v!=null).map(([key,v])=>`${names[key]??key}：${factText(v)}`).join('；')||'未知';
}

export function LogisticsIssues({items,onSafety,disabled=false}:{items:LogisticsIssue[];onSafety:()=>void;disabled?:boolean}) {
  if(!items.length)return null;
  const destinations=logisticsDestinations(items);
  return <section className="panel logistics-todos" aria-label="具体待办事项"><div className="logistics-todos-heading"><h2>逐项处理这些问题</h2>
    {!disabled&&<div className="logistics-todos-actions">{destinations.profile&&<Link className="secondary-button" to={destinations.profile}>前往对应资料 ↗</Link>}{destinations.request&&<Link className="secondary-button" to={destinations.request}>调整露营需求 ↗</Link>}{destinations.safety&&<button className="secondary-button" onClick={onSafety}>查看安全信息</button>}</div>}</div>
    <p>前往资料页后，需要补充的位置会标红。系统资料问题无需反复修改个人信息。</p>
    {disabled&&<p className="muted">当前为历史记录或检查尚未结束，这里只展示当时的缺项。</p>}
    {items.map(item=>{const [title,body]=COPY[item.code]??COPY.UNCLASSIFIED;return <article className="logistics-todo" key={item.issue_id}>
      <span className="tag">{item.category==='USER_INPUT'?'需要补充信息':item.category==='EQUIPMENT_GAP'?'需要调整安排':'系统资料问题'}</span>
      <h3>{item.item_key?equipmentLabel(item.item_key)+' · ':''}{title}</h3><p>{body}</p>
      {(item.current!=null||['DISTANCE','VEHICLE_COUNT','TRANSPORT_MODE'].includes(item.code))&&<p className="muted">本次采用：{item.code==='OVER_BUDGET'?`AUD ${(Number(item.current)/100).toFixed(2)}`:factText(item.current)}</p>}
      {item.required!=null&&<p className="muted">此行程需要：{item.code==='OVER_BUDGET'?`预算 AUD ${(Number(item.required)/100).toFixed(2)}`:factText(item.required)}</p>}
      {!!item.affects?.length&&<p className="muted">这个缺项同时影响：{item.affects.map(field=>field.startsWith('equipment.')?equipmentLabel(field.split('.')[1])+'的需求及费用':'相关费用').join('、')}。先补充此项后再检查。</p>}
    </article>;})}
  </section>;
}
