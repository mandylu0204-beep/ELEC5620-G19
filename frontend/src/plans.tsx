import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { FinalisePanel } from './finalise';
import { RetryPlanning, ChangePlanning } from './planning';
import { NextSteps } from './next_steps';
import { CheckFeedback } from './check_feedback';
import { NearMatches, type RecommendationGuidance } from './near_matches';
import { ModelTracePanel, type ModelTrace } from './model_trace';
import { LogisticsPlanPanel, LogisticsTracePanel, type LogisticsAudit } from './logistics_plan';
import { blockerText, checkNames, checkState, planRowState } from './plan_language';
import { SafetyInformation } from './safety_information';
import type { TripCoverage } from './trip_coverage';
import { ApiFailure, type ApiError, type Requirements } from './api';
import { ProfileSummary, equipmentLabel, type Profile } from './profile';
import { privateApi, useSession } from './session';

export type Source = { dataset_file:string; record_id:string; provenance:{source_name:string; source_type:string; source_date:string; demo_only:boolean}; valid_from:string|null; valid_to:string|null };
type Artifact = { execution_mode:string; source_refs:Source[]; assumptions:string[]; uncertainties:string[] };
type Blocker = { code:string; message:string; source_refs:Source[] };
type ErrorInfo = ApiError['error'];
type Run = {run_id:string;status:string;stage:string;revision:number;error:ErrorInfo|null;execution_mode:string;operation:string;is_active:boolean;created_at:string};
type Version = {version_number:number;status:string;revision:number;version_context:{plan_id:string;plan_version_id:string;run_id:string;input_fingerprint:string};content:Artifact & {selected_campsite_ids:string[];revision_reason:string;itinerary_entries:{entry_kind:string;start_at:string;end_at:string;campsite_id:string|null;description:string}[]}};
type Logistics = Artifact & {outcome:string;transport_feasible:boolean|null;gear_checklist:{item_key:string;required_quantity:string|null;available_quantity:string|null;missing_quantity:string|null;unit:string;capacity_requirement:number|null;arrangement_status:string;essential:boolean}[];cost_breakdown:{category:string;item_key:string;quantity:string|null;unit:string;unit_price_cents:number|null;subtotal_cents:number|null;source_ref:Source|null;assumption:string|null}[];total_cents:number|null;known_subtotal_cents:number;budget_difference_cents:number|null;mandatory_blockers:Blocker[];clarifications:{field:string;question:string;reason:string}[]};
export type Safety = Artifact & {outcome:string;risk_level:string;confidence:string;requires_human_review:boolean;data_quality:{[key:string]:string};evidence:{kind:string;summary:string|null;source_date:string|null;status:string;valid_from:string|null;valid_to:string|null;road_state:string|null;source_refs:Source[]}[];hazards:string[];recommended_actions:string[];unresolved_conflicts:string[];mandatory_blockers:Blocker[]};
type Assessment = {assessment_id:string;kind:string;version_context:Version['version_context'];result:Logistics|Safety};
type Eligibility = {eligible:boolean;blocking_reasons:Blocker[];review_required:boolean;valid_review_id:string|null};
export type FinalIndex = {final_id:string;plan_version_id:string;run_id:string;version_number:number;finalised_at:string;is_current:boolean};
export type PlanDetail = {trip_evidence_coverage?:TripCoverage|null;current_inputs_state?:'CHANGED'|'UNAVAILABLE'|null;check_feedback?:{status:'IN_PROGRESS'|'COMPLETED'|'FAILED'|'INCOMPLETE';started_at:string;completed_at:string|null;comparison:'NOT_COMPARABLE'|'UNCHANGED'|'CHANGED';compared_run_id:string|null;changed_sections:string[]}|null;model_assessment_audits?:Record<string,LogisticsAudit>;recommendation_guidance?:RecommendationGuidance|null;model_planning_trace?:ModelTrace|null;revision_available?:boolean;reassessment_available?:boolean;current_version_revision?:number|null;current_inputs_error?:string|null;planning_available?:boolean;retry_available?:boolean;retry_unavailable_reason?:string|null;finalisation_available:boolean;last_final:FinalIndex|null;selected_final:FinalIndex|null;final_history:FinalIndex[];reviews:{review_id:string;decision:string;reason:string;reviewer_user_id:string}[];review_available?:boolean;plan:{plan_id:string;request_id:string;active_run_id:string|null;current_version_id:string|null;final_version_id:string|null;created_at:string};run:Run|null;run_history:{run_id:string;status:string;stage:string;created_at:string;plan_version_id:string|null;version_number:number|null}[];confirmed_context:{request_id:string;requirements:Requirements;profile_snapshot:Profile;demo_context:{demo_today:string;mode:string};dataset_context:{dataset_version:string;rules_version:string}}|null;events:{id:number;stage:string;status:string;error:ErrorInfo|null;created_at:string}[];version:Version|null;assessments:Assessment[];recommendations:{recommendation_id:string;result:Artifact & {search_outcome:string;candidates:{campsite_id:string;rank:number;reasons:string[];material_uncertainties:string[]}[];excluded_candidates:{campsite_id:string;reasons:string[]}[]}}|null;route:{status:string;eligibility:Eligibility}|null;eligibility:Eligibility|null};
type PlanRow = {search_outcome?:string|null;start_date?:string|null;end_date?:string|null;last_final:FinalIndex|null;plan_id:string;request_id:string;destination:string|null;created_at:string;execution_mode:string|null;run_status:string|null;stage:string|null;version_status:string|null;version_number:number|null};
const LABEL:{[key:string]:string} = {PENDING:'等待执行',RUNNING:'执行中',SUCCEEDED:'检查已完成',FAILED:'执行失败',CANCELLED:'已取消',SUPERSEDED:'已被新运行取代',RECOMMENDING:'推荐营地',GENERATING:'生成行程',SAVING_VERSION:'保存版本',ASSESSING_LOGISTICS:'装备与物流',ASSESSING_SAFETY:'安全评估',ROUTING:'判断下一步',COMPLETED:'完成检查',DRAFT:'草稿',ASSESSING:'正在评估',REVISION_REQUIRED:'需要修订',ESCALATED:'等待审核员处理',BLOCKED:'方案有待完善',ELIGIBLE_FOR_FINALISATION:'可以保存方案',REJECTED:'审核未通过',FINALISED:'已保存',PASSED:'评估通过',REVISION:'需要修订',REVIEW:'需要审核',WEATHER:'天气',FIRE:'营火限制',ROAD:'道路',RESTRICTION:'营地限制',AVAILABLE:'可用',MISSING:'缺失',STALE:'过期',CONFLICTING:'冲突',LOW:'低',MEDIUM:'中',HIGH:'高',UNKNOWN:'未知',OPEN:'开放',CLOSED:'关闭',OWNED:'已自备',CONFIRMED_RENTAL:'已确认租借',UNCONFIRMED:'未确认',CAMPSITE:'营地',TRANSPORT:'交通',FOOD:'食物',WATER:'饮用水',ADDITIONAL_GEAR:'新增装备',PLAN:'初次规划',REASSESS:'重新评估',REVISE:'方案修订',TRAVEL:'交通',CAMP:'露营',ACTIVITY:'活动'};
const STAGES=['RECOMMENDING','GENERATING','SAVING_VERSION','ASSESSING_LOGISTICS','ASSESSING_SAFETY','ROUTING','COMPLETED'];
function label(value:string|null|undefined){return value?LABEL[value]??value:'未知';}
export function aud(cents:number|null|undefined){
  if(cents===null||cents===undefined)return '未知';
  if(!Number.isSafeInteger(cents))return '金额超出显示范围';
  const digits=(cents<0?-BigInt(cents):BigInt(cents)).toString().padStart(3,'0');
  return `AUD ${cents<0?'-':''}${digits.slice(0,-2)}.${digits.slice(-2)}`;
}
function time(value:string){const parsed=new Date(value);return Number.isNaN(parsed.getTime())?value:new Intl.DateTimeFormat('zh-CN',{timeZone:'Australia/Sydney',dateStyle:'short',timeStyle:'short'}).format(parsed);}
const runActive=(value:PlanDetail)=>value.run?.is_active===true&&(
  ['PENDING','RUNNING'].includes(value.run.status) ||
  (value.version?.status==='ESCALATED' && !value.current_inputs_error && !value.reviews.length &&
    value.eligibility?.blocking_reasons.every(item=>item.code==='REVIEW_REQUIRED')===true));
const plansActive=(value:{plans:PlanRow[]})=>value.plans.some(row=>['PENDING','RUNNING'].includes(row.run_status??''));

export function useSavedRead<T>(path:string,poll:(value:T)=>boolean){
  const {reload}=useSession();const [data,setData]=useState<T|null>(null);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
  useEffect(()=>{const controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;setData(null);setError('');
    async function read(){try{const value=await privateApi<T>(path,{signal:controller.signal});if(controller.signal.aborted)return;setData(value);setError('');if(poll(value))timer=setTimeout(read,2500);}catch(reason){if(controller.signal.aborted)return;setError(reason instanceof ApiFailure?`${reason.message}（追踪号 ${reason.envelope.trace_id}）`:'连接失败；已显示的内容来自最近一次成功读取。');if(reason instanceof ApiFailure&&reason.envelope.error.code==='UNAUTHENTICATED')reload();}}
    void read();return()=>{controller.abort();clearTimeout(timer);};
  },[path,retry,poll,reload]);
  return {data,error,refresh:()=>setRetry(value=>value+1)};
}

function Sources({refs}:{refs:Source[]}){return refs.length?<details className="source-details"><summary>来源记录（{refs.length}）</summary><ul>{refs.map((ref,index)=><li key={index}><strong>{ref.dataset_file} · {ref.record_id}</strong><span>{ref.provenance.source_type} · {ref.provenance.source_name} · 来源日期 {ref.provenance.source_date}</span>{(ref.valid_from||ref.valid_to)&&<span>适用范围：{ref.valid_from??'未知'} 至 {ref.valid_to??'未知'}</span>}</li>)}</ul></details>:<p className="muted">没有提供来源记录。</p>;}
function Notes({artifact}:{artifact:Artifact}){return <details className="artifact-notes"><summary>查看说明与来源</summary>{artifact.assumptions.length>0&&<><h3>采用的假设</h3><ul>{artifact.assumptions.map((item,index)=><li key={index}>{item}</li>)}</ul></>}{artifact.uncertainties.length>0&&<><h3>尚不确定</h3><ul>{artifact.uncertainties.map((item,index)=><li key={index}>{item}</li>)}</ul></>}<Sources refs={artifact.source_refs}/></details>;}
function Blockers({items}:{items:Blocker[]}){return items.length?<div className="clarifications"><h3>需要处理的条件</h3><ul>{[...new Set(items.map(item=>blockerText(item.code)))].map(text=><li key={text}>{text}</li>)}</ul><details><summary>查看检查详情</summary>{items.map((item,index)=><div key={index}><p><strong>{item.code}</strong> · {item.message}</p>{item.source_refs.length>0&&<Sources refs={item.source_refs}/>}</div>)}</details></div>:null;}

export function PlansPage(){
  const {data,error,refresh}=useSavedRead<{plans:PlanRow[]}>('/plans',plansActive);
  return <><div className="page-heading"><span className="eyebrow">YOUR PLANS</span><h1>我的露营方案</h1><p>查看安排、处理待确认事项，保存你的最终方案。</p></div>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>刷新方案</button>
    {!data?<section className="panel"><p>正在读取…</p></section>:!data.plans.length?<section className="panel"><h2>还没有露营方案</h2><p>填写资料并确认需求后，即可开始规划。</p><Link className="text-link" to="/request">开始规划 ↗</Link></section>:<div className="plan-cards">{data.plans.map(row=><Link className="panel plan-card" key={row.plan_id} to={'/plans/'+row.plan_id}><h2>{row.destination??'露营方案'}</h2><p className="tag">{planRowState(row)}</p>
      {row.start_date&&row.end_date&&<p>{row.start_date} — {row.end_date}</p>}{row.version_number?<p>版本 {row.version_number}</p>:row.search_outcome==='NO_MATCH'?<p>比较最接近的营地，再调整你的条件。</p>:<p>完成规划后可查看行程。</p>}
      {row.run_status==='RUNNING'&&<p>正在{label(row.stage)}</p>}{row.last_final&&!row.last_final.is_current&&<p className="muted">已保留此前保存的最终方案</p>}<small>创建于 {time(row.created_at)}（悉尼时间）</small><span className="text-link">{row.search_outcome==='NO_MATCH'?'查看营地比较':'查看方案'} ↗</span></Link>)}</div>}
  </>;
}

export function PlanPage(){const {planId}=useParams();const [search,setSearch]=useSearchParams();const runId=search.get('run_id');const {data,error,refresh}=useSavedRead<PlanDetail>('/plans/'+planId+(runId?'?run_id='+encodeURIComponent(runId):''),runActive);
  if(!data)return <><div className="page-heading"><h1>读取规划记录</h1></div>{error&&<p className="error-box" role="alert">{error}</p>}<button className="secondary-button" onClick={refresh}>重新读取</button><Link className="text-link" to="/plans">返回方案列表 ↗</Link></>;
  return <PlanView data={data} error={error} refresh={refresh} current={()=>setSearch({})}/>;
}
const CAMPSITE_NAMES: Record<string, string> = {
  'demo-pine-camp':'Demo Pine Camp', 'demo-river-flat':'Demo River Flat', 'demo-ridge-lookout':'Demo Ridge Lookout',
  'demo-fern-walk':'Demo Fern Walk', 'demo-lake-meadow':'Demo Lake Meadow', 'demo-sandstone-grove':'Demo Sandstone Grove',
  'demo-cloud-gully':'Demo Cloud Gully', 'demo-wattle-rest':'Demo Wattle Rest', 'demo-granite-ledge':'Demo Granite Ledge',
  'demo-moonlit-field':'Demo Moonlit Field',
};
export const campName = (id: string) => CAMPSITE_NAMES[id] ?? id;
const unitName = (unit: string) => ({item:'件',person_space:'人位',litre:'升',portion:'份',vehicle:'辆',plan:'份计划',per_night:'晚',per_kilometre:'公里',per_vehicle:'辆',per_person_per_day:'人天',one_time:'次',not_procured:'暂不采购'} as Record<string,string>)[unit] ?? unit;
type PlanSection = 'itinerary' | 'gear' | 'cost' | 'safety' | 'history';
const PLAN_SECTIONS: {id:PlanSection; title:string}[] = [
  {id:'itinerary',title:'行程'},{id:'gear',title:'装备'},{id:'cost',title:'费用'},
  {id:'safety',title:'安全'},{id:'history',title:'记录'},
];

export function PlanView({data,error,refresh,current,review=false,snapshot=false,reviewActions}:{data:PlanDetail;error:string;refresh:()=>void;current?:()=>void;review?:boolean;snapshot?:boolean;reviewActions?:ReactNode}) {
  const [section,setSection] = useState<PlanSection>(review?'safety':'itinerary');
  const [adjustOpen,setAdjustOpen] = useState(false);
  const tabRefs = useRef<(HTMLButtonElement|null)[]>([]);
  const prefix = useId().replaceAll(':','');
  const logistics = data.assessments.find(item=>item.kind==='LOGISTICS')?.result as Logistics|undefined;
  const safety = data.assessments.find(item=>item.kind==='SAFETY')?.result as Safety|undefined;
  const recommendation = data.recommendations?.result;
  const logisticsAudit = data.model_assessment_audits?.LOGISTICS;
  const noMatch = recommendation?.search_outcome==='NO_MATCH';
  const {version,run,confirmed_context:confirmed} = data;
  const validApproval = !data.current_inputs_error&&data.reviews.some(item=>item.decision==='APPROVE'&&(
    item.review_id===data.eligibility?.valid_review_id||(snapshot&&version?.status==='FINALISED')));
  const requirements = confirmed?.requirements;
  const title = version?.content.selected_campsite_ids.map(campName).join(' / ') || requirements?.destination || '我的露营方案';
  const stepSaved = [!!recommendation,!!version,!!version,!!logistics,!!safety,!!data.route,run?.status==='SUCCEEDED'];
  const qualityIssues = safety ? Object.entries(safety.data_quality).filter(([,value])=>value!=='AVAILABLE') : [];
  const qualityGroups = new Map<string,string[]>();
  qualityIssues.forEach(([kind,status])=>{const text=checkState(kind,status,safety?.evidence??[],requirements).detail;qualityGroups.set(text,[...(qualityGroups.get(text)??[]),checkNames[kind]??'安全信息']);});
  const safetyText = !safety ? '尚未检查' : qualityIssues.length ? qualityIssues.some(([,status])=>status==='CONFLICTING')?'安全资料存在冲突':qualityIssues.some(([,status])=>status==='STALE')?'安全资料需要更新':'缺少适用的安全资料' : safety.outcome==='BLOCKED'?'安全条件未满足':validApproval&&safety.outcome==='REVIEW' ? '审核已批准' : safety.requires_human_review ? '需要人工审核' : label(safety.outcome);
  const rawWarnings = data.eligibility?.blocking_reasons??[];
  const hiddenCodes = new Set(['VERSION_STATE','ASSESSMENT_BLOCKED','RUN_NOT_SUCCEEDED','REVISION_REQUIRED','REVIEW_REQUIRED',
    ...(qualityIssues.length?['EVIDENCE_COVERAGE','EVIDENCE_UNAVAILABLE','ROAD_UNAVAILABLE']:[]),
    ...(rawWarnings.some(item=>item.code==='ROAD_CLOSED')?['ROAD_UNAVAILABLE']:[])]);
  const weatherFields:Record<string,string>={'gear_rule_input.forecast_rain_mm':'降雨','gear_rule_input.temperature_max_c':'最高气温',
    'gear_rule_input.temperature_min_c':'最低气温','gear_rule_input.wind_kph':'风速',
    'evidence.weather.forecast_rain_mm':'降雨','evidence.weather.temperature_max_c':'最高气温',
    'evidence.weather.temperature_min_c':'最低气温','evidence.weather.wind_kph':'风速'};
  const missingWeather=[...new Set((logistics?.clarifications??[]).flatMap(item=>weatherFields[item.field]?[weatherFields[item.field]]:[]))];
  const weatherOnlyLogistics = missingWeather.length>0 && logistics?.transport_feasible===true && !logistics.mandatory_blockers.length && logistics.clarifications.every(item=>!!weatherFields[item.field]);
  const warnings = [...new Set(rawWarnings.filter(item=>!hiddenCodes.has(item.code)).map(item=>item.code==='LOGISTICS_INCOMPLETE'&&weatherOnlyLogistics?'缺少适用的天气资料，装备检查仍有待确认。':blockerText(item.code)))];
  const overBudget = logistics?.budget_difference_cents != null && logistics.budget_difference_cents > 0;
  const hasSafetyIssue = !!safety && (qualityIssues.length>0 || (!validApproval&&(safety.outcome!=='PASSED' || safety.requires_human_review)));
  const tone = data.current_inputs_error ? 'warning' : run?.status==='FAILED' || ['BLOCKED','REJECTED'].includes(version?.status??'') ? 'danger'
    : ['REVISION_REQUIRED','ESCALATED'].includes(version?.status??'') || noMatch ? 'warning'
    : ['FINALISED','ELIGIBLE_FOR_FINALISATION'].includes(version?.status??'') ? 'success' : 'neutral';
  const stateText = data.current_inputs_error ? data.current_inputs_state==='UNAVAILABLE'?'检查服务暂不可用':'检查结果待更新' : run&&['PENDING','RUNNING'].includes(run.status) ? run.operation==='REASSESS'?'正在重新检查':label(run.status)
    : run?.status==='FAILED' ? '执行未完成' : noMatch ? '需要调整需求' : version ? label(version.status) : label(run?.status);
  useEffect(()=>{setSection(review?'safety':'itinerary');setAdjustOpen(false);},[run?.run_id,version?.version_context.plan_version_id,review]);
  function keyboardTabs(event:KeyboardEvent<HTMLButtonElement>,index:number) {
    let target=index;
    if(event.key==='ArrowRight')target=(index+1)%PLAN_SECTIONS.length;
    else if(event.key==='ArrowLeft')target=(index+PLAN_SECTIONS.length-1)%PLAN_SECTIONS.length;
    else if(event.key==='Home')target=0;
    else if(event.key==='End')target=PLAN_SECTIONS.length-1;
    else return;
    event.preventDefault();setSection(PLAN_SECTIONS[target].id);tabRefs.current[target]?.focus();
  }
  const pane = (id:PlanSection) => ({id:prefix+'-'+id,role:'tabpanel' as const,'aria-labelledby':prefix+'-tab-'+id,hidden:section!==id,className:'plan-tab-panel',tabIndex:0});
  return <div className="plan-result">
    <div className="plan-toolbar"><Link className="text-link" to={review?'/review':'/plans'}>← {review?'审核队列':'我的方案'}</Link><div>
      {!review&&!snapshot&&<Link className="text-link" to={'/request/'+(confirmed?.request_id??data.plan.request_id)}>查看需求 ↗</Link>}
      <button className="secondary-button" onClick={refresh}>刷新</button>
    </div></div>
    <header className="plan-overview">
      <div className="plan-overview-title"><span className="eyebrow">{snapshot?'YOUR SAVED PLAN':'YOUR CAMPING PLAN'}</span>
        <h1>{title}</h1><p>{requirements?.destination??'目的地待确认'}{version&&' · 版本 '+version.version_number}</p>
      </div>
      <span className={'plan-status plan-status-'+tone}><i aria-hidden="true"/>{stateText}</span>
      <dl className="plan-facts">
        <div><dt>出行日期</dt><dd>{requirements?.start_date??'待确认'} <span>—</span> {requirements?.end_date??'待确认'}</dd><small>{requirements?.duration_nights??'—'} 晚 · {requirements?.duration_days??'—'} 天 · {confirmed?.profile_snapshot.group_size??'—'} 人</small></div>
        <div className={overBudget?'fact-attention':''}><dt>{data.current_inputs_error?'此前费用估算':'行程费用估算'}</dt><dd>{aud(logistics?.total_cents)}</dd><small>预算 {aud(requirements?.budget_cents)}{logistics?.budget_difference_cents!=null&&' · '+(overBudget?'超出 ':'剩余 ')+aud(Math.abs(logistics.budget_difference_cents))}</small></div>
        <div className={hasSafetyIssue||safety?.risk_level==='HIGH'?'fact-attention':''}><dt>{data.current_inputs_error?'此前安全检查':'安全检查'}</dt><dd>{safetyText}</dd><small>{!safety?'规划完成后查看检查结果':safety.risk_level==='UNKNOWN'?'信息不足，暂时无法判断风险。':'风险 '+label(safety.risk_level)+(review?' · 判断依据完整度 '+label(safety.confidence):'')}</small></div>
      </dl>
    </header>
    {error&&<p className="error-box" role="alert">读取更新失败：{error}</p>}
    {!review&&!snapshot&&<CheckFeedback data={data}/>}
    {!snapshot&&run&&!run.is_active&&<div className="mode-notice"><span>正在查看历史方案，评估属于当时的证据。</span>{current&&<button className="secondary-button" onClick={current}>查看当前方案</button>}</div>}
    {run?.error&&<div className="error-box" role="alert"><strong>本次执行未完成</strong><p>{run.error.message}</p>{!review&&!snapshot&&<RetryPlanning data={data} refresh={refresh}/>}</div>}
    {!['PENDING','RUNNING'].includes(run?.status??'')&&(warnings.length>0 || overBudget || hasSafetyIssue)&&<section className="plan-attention" role="alert" aria-label="需要处理的问题">
      <div><span className="attention-mark" aria-hidden="true">!</span><div><h2>{data.current_inputs_error?'此前检查发现的问题':'确认方案前需要处理'}</h2><ul>
        {overBudget&&<li>行程估算超出预算 {aud(logistics?.budget_difference_cents)}。</li>}
        {[...qualityGroups.entries()].map(([text,names])=><li key={text}>{names.join('、')}：{text}</li>)}
        {warnings.map(message=><li key={message}>{message}</li>)}
        {hasSafetyIssue&&!qualityIssues.length&&!warnings.length&&<li>安全评估{label(safety?.outcome)}，请查看风险与建议。</li>}
      </ul></div></div>
      {hasSafetyIssue&&<button className="secondary-button" onClick={()=>{setSection('safety');tabRefs.current[3]?.focus();}}>查看安全信息</button>}
    </section>}
    {review&&data.current_inputs_error&&<div className="mode-notice"><strong>检查结果待更新</strong><p>这份方案的检查依据暂时无法与当前资料核对，更新检查后才能继续审核。</p><details><summary>查看系统详情</summary><p>{data.current_inputs_error}</p></details></div>}
    {!review&&!snapshot&&<NextSteps data={data} onRecheck={()=>{setAdjustOpen(true);document.getElementById(prefix+'-adjust')?.scrollIntoView({block:'start'});}}/>}
    {!snapshot&&!review&&data.last_final&&<div className="saved-plan-notice"><span>{data.last_final.is_current?'当前最终方案已保存':'保留了一份历史最终方案'}</span><Link className="text-link" to={'/plans/'+data.plan.plan_id+'/finals/'+data.last_final.final_id}>查看保存的方案 ↗</Link></div>}
    {!review&&!snapshot&&(data.revision_available||data.reassessment_available)&&<details className="plan-adjust" id={prefix+'-adjust'} key={run?.run_id} open={adjustOpen} onToggle={event=>setAdjustOpen(event.currentTarget.open)}>
      <summary>修改行程或更新检查 <span aria-hidden="true">↗</span></summary><ChangePlanning data={data} refresh={refresh}/>
    </details>}
    {run&&run.operation!=='REASSESS'&&['PENDING','RUNNING'].includes(run.status)&&<div className="plan-live-progress" role="status"><span className="progress-pulse" aria-hidden="true"/><span>正在{label(run.stage)}，完成后会自动更新。</span></div>}
    <div className="plan-tabs" role="tablist" aria-label="方案内容">
      {PLAN_SECTIONS.map((tab,index)=><button key={tab.id} ref={node=>{tabRefs.current[index]=node;}} id={prefix+'-tab-'+tab.id} type="button" role="tab" aria-selected={section===tab.id} aria-controls={prefix+'-'+tab.id} tabIndex={section===tab.id?0:-1} onClick={()=>setSection(tab.id)} onKeyDown={event=>keyboardTabs(event,index)}>
        {noMatch&&tab.id==='itinerary'?'营地对照':tab.title}{((tab.id==='safety'&&hasSafetyIssue)||(tab.id==='cost'&&overBudget))&&<i className="tab-alert" aria-label="有待处理的问题"/>}
      </button>)}
    </div>
    <div {...pane('itinerary')}>
      {noMatch?data.recommendation_guidance?<NearMatches value={data.recommendation_guidance} requestId={data.plan.request_id}/>:<section className="panel"><h2>没有满足需求的营地</h2><p>请在“记录”中查看被排除营地的理由，调整条件并重新确认需求。</p></section>:<section className="panel itinerary-panel"><div className="section-title"><span className="eyebrow">YOUR ITINERARY</span><h2>行程安排</h2></div>
        {version?<><div className="itinerary-camps">{version.content.selected_campsite_ids.map(id=><span key={id}>{campName(id)}</span>)}</div>
          {run?.operation==='REASSESS'&&<p className="muted">行程保持不变。{!snapshot&&!review&&'本轮检查进度和结果见上方。'}{logisticsAudit&&'装备与预算建议可在对应页面查看。'}</p>}
          {version.content.itinerary_entries.length?<ol className="plan-timeline">{version.content.itinerary_entries.map((entry,index)=><li key={index}>
            <div className="timeline-time"><span>{label(entry.entry_kind)}</span><time>{time(entry.start_at)}</time></div>
            <div className="timeline-content"><h3>{entry.campsite_id?campName(entry.campsite_id):label(entry.entry_kind)}</h3><p>{entry.description}</p><small>至 {time(entry.end_at)}</small></div>
          </li>)}</ol>:<p className="muted">没有提供行程条目。</p>}
          <details className="source-details"><summary>查看本次规划说明</summary><p>{version.content.revision_reason}</p></details><Notes artifact={version.content}/>
        </>:<div className="plan-empty"><span aria-hidden="true">⌁</span><h3>行程正在准备中</h3><p>{run?.status==='FAILED'?'先处理上方的执行问题，再继续规划。':'规划完成后，可在这里查看露营安排。'}</p></div>}
      </section>}
      {recommendation&&!noMatch&&<details className="panel recommendation-panel"><summary>比较其他推荐营地 <span>{recommendation.candidates.length} 个</span></summary>
        <ol className="candidate-list">{recommendation.candidates.map(item=><li key={item.campsite_id}><h3>#{item.rank} · {campName(item.campsite_id)}</h3><ul>{item.reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul>{item.material_uncertainties.map((uncertainty,index)=><p className="muted" key={index}>尚不确定：{uncertainty}</p>)}</li>)}</ol><Notes artifact={recommendation}/>
      </details>}
    </div>
    <div {...pane('gear')}><section className="panel"><div className="section-title"><span className="eyebrow">PACK & PREPARE</span><h2>装备与物流</h2></div>
      {logistics?<><p>评估：{label(logistics.outcome)} · 交通：{logistics.transport_feasible===null?'待核实':logistics.transport_feasible?'可行':'不可行'}</p>
        <div className="table-scroll"><table><caption>装备数量与缺口</caption><thead><tr>{['装备','所需','已具备','缺口','单位','容量要求','安排','必要'].map(title=><th key={title}>{title}</th>)}</tr></thead><tbody>{logistics.gear_checklist.map((item,index)=><tr key={index} className={item.essential&&(item.missing_quantity==null||Number(item.missing_quantity)>0)?'gear-gap':''}>
          <td>{equipmentLabel(item.item_key)}</td><td>{item.required_quantity??'未知'}</td><td>{item.available_quantity??'未知'}</td><td>{item.missing_quantity??'未知'}</td><td>{unitName(item.unit)}</td><td>{item.capacity_requirement===null?'未知':`${item.capacity_requirement} 人`}</td><td>{label(item.arrangement_status)}</td><td>{item.essential?'是':'否'}</td>
        </tr>)}</tbody></table></div>{!logistics.gear_checklist.length&&<p className="muted">没有提供装备清单。</p>}
        <Blockers items={logistics.mandatory_blockers}/>{missingWeather.length>0&&<div className="clarifications"><p>缺少适用于此次行程的{missingWeather.join('、')}资料，暂时无法完整计算装备需求。</p><button className="secondary-button" onClick={()=>{setSection('safety');tabRefs.current[3]?.focus();}}>查看安全信息</button></div>}{logistics.clarifications.filter(item=>!weatherFields[item.field]).map((item,index)=><p className="clarifications" key={index}>{item.question} · {item.reason}</p>)}<Notes artifact={logistics}/>
      </>:<p className="plan-empty-text">尚未保存装备与物流评估。</p>}
    </section><LogisticsPlanPanel value={logisticsAudit} section="gear" money={aud} itemName={equipmentLabel} unitName={unitName}/></div>
    <div {...pane('cost')}><section className="panel"><div className="section-title"><span className="eyebrow">YOUR BUDGET</span><h2>费用与预算</h2></div>
      {logistics?<><div className="cost-summary"><div><span>费用估算</span><strong>{aud(logistics.total_cents)}</strong></div><div><span>已知部分小计</span><strong>{aud(logistics.known_subtotal_cents)}</strong></div><div><span>小组预算</span><strong>{aud(requirements?.budget_cents)}</strong></div><div className={overBudget?'cost-over-budget':''}><span>{logistics.budget_difference_cents===null?'预算差额':overBudget?'超出预算':'预算剩余'}</span><strong>{aud(logistics.budget_difference_cents===null?null:Math.abs(logistics.budget_difference_cents))}</strong></div></div>
        {logistics.total_cents===null&&<p className="clarifications">费用尚不完整，已知小计不能作为最终总费用。</p>}
        <div className="table-scroll"><table><caption>费用明细（AUD）</caption><thead><tr>{['项目','数量 / 单位','单价','小计','依据'].map(title=><th key={title}>{title}</th>)}</tr></thead><tbody>{logistics.cost_breakdown.map((line,index)=><tr key={index}>
          <td>{label(line.category)}{line.category==='CAMPSITE'&&<small className="cost-site">{campName(line.item_key)}</small>}</td><td>{line.quantity??'未知'} {unitName(line.unit)}</td><td>{aud(line.unit_price_cents)}</td><td>{aud(line.subtotal_cents)}</td><td>{line.assumption&&<details><summary>计算说明</summary><p>{line.assumption}</p></details>}{line.source_ref?<Sources refs={[line.source_ref]}/>:<span>来源未提供</span>}</td>
        </tr>)}</tbody></table></div><Notes artifact={logistics}/>
      </>:<p className="plan-empty-text">尚未保存费用，金额未知。</p>}
    </section><LogisticsPlanPanel value={logisticsAudit} section="cost" money={aud} itemName={equipmentLabel} unitName={unitName}/></div>
    <div {...pane('safety')}><SafetyInformation coverage={data.trip_evidence_coverage} requestId={data.plan.request_id} value={safety} requirements={requirements} summary={safetyText} approved={validApproval} review={review} outdated={!!data.current_inputs_error} blockers={<Blockers items={safety?.mandatory_blockers??[]}/>} notes={safety&&<Notes artifact={safety}/>} rawWarnings={rawWarnings} sources={refs=><Sources refs={refs}/>} label={label}/></div>
    <div {...pane('history')}>
      <section className="panel progress-panel"><div className="section-title"><span className="eyebrow">PLAN HISTORY</span><h2>规划记录</h2></div>
        {run?<><p>{label(run.operation)} · {label(run.status)}</p><ol className="progress-stages">{STAGES.map((stage,index)=>{const skipped=(noMatch&&run.status==='SUCCEEDED'&&index>0&&index<6)||(run.operation==='REASSESS'&&index===0);const currentStage=run.stage===stage&&!stepSaved[index]&&!skipped;return <li key={stage} className={stepSaved[index]?'stage-saved':currentStage?'stage-current':''}><span>{index+1}</span><strong>{label(stage)}</strong><small>{skipped?'无需执行':stepSaved[index]?run.operation==='REASSESS'&&(index===1||index===2)?'复用已保存':'已保存':currentStage?run.status==='FAILED'?'在此停止':'当前阶段':'尚无产物'}</small></li>;})}</ol>
          <details><summary>查看执行记录（{data.events.length}）</summary>{data.events.length?<ol className="event-list">{data.events.map(event=><li key={event.id}>{time(event.created_at)} · {label(event.stage)} · {label(event.status)}{event.error&&<p>{event.error.message}</p>}</li>)}</ol>:<p className="muted">尚无执行记录。</p>}</details>
        </>:<p className="muted">尚未登记规划。</p>}
      </section>
      <ModelTracePanel value={data.model_planning_trace} currentRunId={run?.run_id} logisticsModel={!!logisticsAudit}/>
      <LogisticsTracePanel value={logisticsAudit}/>
      <section className="panel"><h2>审核记录</h2>{data.reviews.length?data.reviews.map(item=><article key={item.review_id}><h3>{item.decision==='APPROVE'?'已批准':item.decision==='REJECT'?'已拒绝':'要求修订'}</h3><p>{item.reason}</p><small>审核人：{item.reviewer_user_id}</small></article>):<p className="muted">尚无审核决定。</p>}</section>
      <section className="panel"><h2>本次需求</h2>{confirmed&&<><p>{requirements?.start_date} → {requirements?.end_date} · {requirements?.duration_nights} 晚 / {requirements?.duration_days} 天 · {aud(requirements?.budget_cents)}</p><details><summary>本次采用的资料</summary><ProfileSummary profile={confirmed.profile_snapshot}/></details></>}
        <details className="source-details"><summary>记录编号与输入指纹</summary><p className="identifier">{run?.run_id??'未登记'}</p><p className="identifier">{version?.version_context.input_fingerprint??'尚未保存版本指纹'}</p></details>
        {recommendation&&recommendation.excluded_candidates.length>0&&<details className="source-details"><summary>被排除营地的原始理由</summary>{recommendation.excluded_candidates.map(item=><article key={item.campsite_id}><h3>{campName(item.campsite_id)}</h3><ul>{item.reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul></article>)}</details>}
        {!review&&!snapshot&&<><h3>保存的方案</h3>{data.final_history.length?<ul className="plan-history-list">{data.final_history.map(item=><li key={item.final_id}><Link to={'/plans/'+data.plan.plan_id+'/finals/'+item.final_id}>版本 {item.version_number} · {item.is_current?'当前方案':'历史方案'}<small>{time(item.finalised_at)}</small></Link></li>)}</ul>:<p className="muted">尚未保存最终方案。</p>}
          <h3>版本与评估历史</h3><ul className="plan-history-list">{data.run_history.map(item=><li key={item.run_id}><Link to={'/plans/'+data.plan.plan_id+'?run_id='+encodeURIComponent(item.run_id)}>{item.version_number?`版本 ${item.version_number}`:'尚无版本'} · {label(item.status)}<small>{time(item.created_at)}</small></Link>{item.run_id===data.plan.active_run_id&&<span className="tag">当前</span>}</li>)}</ul>
        </>}
      </section>
    </div>
    {review&&reviewActions}
    {!review&&!snapshot&&<section className="panel plan-save" id={prefix+'-save'}><div><span className="eyebrow">SAVE YOUR PLAN</span><h2>{version?.status==='FINALISED'?'方案已保存':'保存露营方案'}</h2>{!data.finalisation_available&&version?.status!=='FINALISED'&&<p className="muted">完成必要的评估和审核后，即可保存。</p>}</div><FinalisePanel key={version?.version_context.input_fingerprint??run?.run_id} data={data}/></section>}
  </div>;
}
