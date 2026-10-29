import {RequirementChoices,type RequirementCatalogue} from './requirement_choices';
import { DiscardChanges } from './display_panels';
import { changedSections, PROFILE_SAVED_NOTICE } from './display_facts';
import { prepareMissingEquipment, profileGuidance } from './profile_guidance';
import { CookingPreparationPanel, cookingDraft, type CookingPreparation } from './cooking_preparation';
import { prepareProfileEquipment, vehicleCount, PLAN_RECORD_KEYS } from './vehicle_profile';
import { VehicleFields } from './vehicle_fields';
import type { LogisticsIssue } from './logistics_issues';
import { profileFocusId, profileCorrectionTargets, focusProfileTargets } from './profile_focus';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi, useSession } from './session';
import { equipmentForSave, equipmentPayload } from './equipment_confirmation';
import { TripFlow, FieldHint } from './trip_flow';
import { canonicalTerms, termLabel } from './user_terms';

export type Equipment = { item_key: string; label: string; quantity: number | null; unit: string; capacity_persons: number | null; confirmed: boolean };
export type Profile = { profile_id?: string | null; group_size: number | null; experience_level: string | null; has_children: boolean | null; children_count: number | null; equipment: Equipment[]; transport: { transport_type: string | null; vehicle_count: number | null; estimated_km: string | null; assumptions: string[] }; accessibility_requirements: string[] };
type ProfileResponse = { profile: Profile | null; revision: number };
type EquipmentForm = { item_key: string; label: string; quantity: string; unit: string; capacity: string; confirmed: boolean };
const EQUIPMENT_TYPES = [
  ['tent','帐篷','item'],['groundsheet','地布','item'],['tent_repair_kit','帐篷修补工具','item'],
  ['sleeping_bag','睡袋','item'],['sleeping_mat','睡垫','item'],['warm_liner','保暖内衬','item'],
  ['rain_jacket','雨衣','item'],['warm_layers','保暖衣物','item'],['sun_hat','遮阳帽','item'],
  ['windproof_outer_layer','防风外套','item'],['camping_stove','露营炉具','item'],['fuel_canister','燃料罐','item'],
  ['cooking_pot','炊具','item'],['drinking_water','饮用水','litre'],['meal_supplies','餐食','portion'],
  ['child_snacks','儿童零食','portion'],['offline_map','离线地图','item'],
  ['power_bank','充电宝','item'],['first_aid_kit','急救包','item'],['torch','头灯 / 手电','item'],
  ['whistle','哨子','item'],['emergency_contact_card','紧急联系卡','item'],['hand_sanitiser','洗手液','item'],
  ['toilet_kit','卫生用品','item'],['vehicle','车辆','vehicle'],['transport_itinerary','交通连接计划','plan'],
  ['fire_free_meal_plan','无火餐食计划','plan'],['water_container','储水容器','item'],['other','其他装备','item'],
];
const LEVELS = [['BEGINNER','初次 / 初学者'],['INTERMEDIATE','有一定经验'],['EXPERIENCED','经验丰富'],['ADVANCED','熟练 / 进阶']];
const MODES = [['CAR','汽车'],['PUBLIC_TRANSPORT','公共交通'],['WALKING','步行'],['OTHER','其他']];
export function PublicTransportNotice(){
  return <p className="mode-notice">公共交通需自行核对去程、返程及到营地的最后接驳安排。系统使用已登记的营地可达标记及模拟往返费用，不查询实际班次、末班车或实时票价，也不代表已订票。</p>;
}
export function SystemPreparationNotice({mode}:{mode:string}){
  if(mode==='CAR')return null;
  return <p className="mode-notice">公共交通使用营地可达资料和模拟往返费用；具体去程、返程班次及最后接驳在选定营地后核对，不需要先写路线。</p>;
}
export function TransportModeField({value,supported,onChange,error,guidance}:{
  value:string;supported:string[]|null;onChange:(value:string)=>void;error:string;guidance?:string;systemPreparation?:boolean;
}){
  const choices=MODES.filter(([key])=>supported?.includes(key)&&['CAR','PUBLIC_TRANSPORT'].includes(key));
  const unsupported=supported!==null&&!!value&&!choices.some(([key])=>key===value);
  return <><label htmlFor="transport">交通方式</label><select id="transport" disabled={supported===null}
    aria-invalid={!!guidance||unsupported} aria-describedby="transport-hint" value={value} onChange={event=>onChange(event.target.value)}>
    <option value="" disabled hidden>请选择交通方式</option>{choices.map(([key,label])=><option key={key} value={key}>{label}</option>)}
    {value&&!choices.some(([key])=>key===value)&&<option value={value} disabled>{Object.fromEntries(MODES)[value]??value}（{supported===null?'已保存，正在读取支持范围':'历史资料，当前暂不支持'}）</option>}
  </select><FieldHint id="transport-hint" error={error||guidance||(unsupported?'原交通方式已保留，但当前不能用于新规划。请明确选择支持的方式，再重新生成摘要。':undefined)}>{supported===null?'正在读取交通支持范围…':null}</FieldHint>
  </>;
}
export const equipmentLabel = (key: string) => EQUIPMENT_TYPES.find(([type])=>type===key)?.[1] ?? key;
const unitLabel = (unit: string) => ({item:'件',litre:'升',portion:'份',vehicle:'辆',plan:'份计划',set:'套'} as Record<string,string>)[unit] ?? unit;
const EQUIPMENT_UNITS=[['item','件'],['litre','升'],['portion','份'],['vehicle','辆'],['plan','份计划'],['set','套']];
export function fixedEquipmentUnit(key:string,datasetVersion?:string|null){
  if(key==='other')return null;
  return key==='warm_layers'&&datasetVersion==='v1'?'set':EQUIPMENT_TYPES.find(([type])=>type===key)?.[2]??null;
}
function equipmentNumber(number:number):string {
  const digits='零一二三四五六七八九';
  if(number<10)return digits[number];
  if(number<100)return `${number<20?'':digits[Math.floor(number/10)]}十${number%10?digits[number%10]:''}`;
  return String(number);
}
function distinctEquipmentNames(items:EquipmentForm[],key:string):EquipmentForm[]{
  const base=equipmentLabel(key);
  const used=new Set(items.filter(item=>item.item_key===key&&item.label.trim()&&item.label!==base).map(item=>item.label.trim()));
  return items.map(item=>{
    if(item.item_key!==key||(item.label.trim()&&item.label!==base))return item;
    let number=1;while(used.has(base+equipmentNumber(number)))number++;
    const label=base+equipmentNumber(number);used.add(label);return {...item,label};
  });
}
export function addEquipment(items:EquipmentForm[],key:string,datasetVersion?:string|null):EquipmentForm[]{
  return distinctEquipmentNames([...items,{item_key:key,label:equipmentLabel(key),quantity:'',
    unit:fixedEquipmentUnit(key,datasetVersion)??'item',capacity:'',confirmed:false}],key);
}
export function changeEquipmentCategory(items:EquipmentForm[],index:number,key:string,datasetVersion?:string|null):EquipmentForm[]{
  const previous=items[index];if(!previous||previous.item_key===key)return items;
  const base=equipmentLabel(previous.item_key);
  const automatic=previous.label===base||previous.label.startsWith(base)&&/^(?:[一二三四五六七八九十]+|\d+)$/.test(previous.label.slice(base.length));
  return distinctEquipmentNames(items.map((item,i)=>i===index?{...item,item_key:key,
    label:automatic||!item.label.trim()?equipmentLabel(key):item.label,
    unit:fixedEquipmentUnit(key,datasetVersion)??item.unit}:item),key);
}
export function EquipmentUnitField({item,index,datasetVersion,error,onChange}:{
  item:EquipmentForm;index:number;datasetVersion?:string|null;error?:string;onChange:(unit:string)=>void;
}){
  const expected=fixedEquipmentUnit(item.item_key,datasetVersion);
  const mismatch=item.item_key!=='other'&&expected!==null&&expected!==item.unit;
  const label=item.item_key==='tent'&&item.unit==='item'?'顶':unitLabel(item.unit);
  return <div><label htmlFor={`gear-unit-${index}`}>单位</label>
    {item.item_key==='other'?<select id={`gear-unit-${index}`} aria-label={`装备 ${index+1} 单位`} required
      value={item.unit} aria-invalid={!!error} aria-describedby={`gear-unit-hint-${index}`} onChange={event=>onChange(event.target.value)}>
      {EQUIPMENT_UNITS.map(([key,title])=><option key={key} value={key}>{title}</option>)}
      {!EQUIPMENT_UNITS.some(([key])=>key===item.unit)&&<option value={item.unit}>{item.unit||'请选择单位'}</option>}
    </select>:<input id={`gear-unit-${index}`} aria-label={`装备 ${index+1} 单位`} readOnly value={label}
      aria-invalid={!!error||mismatch} aria-describedby={`gear-unit-hint-${index}`}/>}
    <FieldHint id={`gear-unit-hint-${index}`} error={error??(mismatch?'已保存的单位与类别不符，请按类别修正后保存。':undefined)}>
      {item.item_key==='other'?'按此物品的实际计量方式选择。':'单位由类别确定。'}
    </FieldHint>
    {mismatch&&<button type="button" className="text-button" onClick={()=>onChange(expected!)}>按类别修正单位</button>}
  </div>;
}
const canonical = (value: string | null | undefined, choices: string[][]) => choices.find(([key]) => key.toLowerCase() === value?.trim().toLowerCase())?.[0] ?? value ?? '';


export function lines(value: string): string[] { return value.split('\n').map(line => line.trim()).filter(Boolean); }
export function integer(value: string): number | null {
  if (!value.trim()) return null;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value))) throw new Error('人数、数量和容量请填写有效整数。');
  return Number(value);
}

export function GroupSizeField({value,error,guidance,revealValidation,onTouch,onChange}:{
  value:string;error?:string;guidance?:string;revealValidation:boolean;
  onTouch:()=>void;onChange:(value:string)=>void;
}){
  const visibleError=(revealValidation?error:undefined)??guidance;
  return <div><label htmlFor="group-size">小组人数（含儿童） <span className="required-mark">必填</span></label>
    <input id="group-size" type="number" min="1" step="1" required value={value}
      aria-invalid={!!visibleError} aria-describedby="group-hint" onBlur={onTouch} onInvalid={onTouch}
      onChange={event=>onChange(event.target.value)}/>
    <FieldHint id="group-hint" error={visibleError}>包括所有同行者。</FieldHint>
  </div>;
}

export function ProfilePage({ datasetVersion }: { datasetVersion?: string | null }) {
  const { session, reload } = useSession();
  const navigate=useNavigate();
  const [search]=useSearchParams(); const requestedFocus=search.get('focus')??''; const sourceRequest=search.get('request_id');
  const [activeFocus,setActiveFocus]=useState(requestedFocus);
  useEffect(()=>setActiveFocus(requestedFocus),[requestedFocus]);
  const focusDone=useRef('');
  const sourcePlan=search.get('plan_id'); const [relatedIssues,setRelatedIssues]=useState<LogisticsIssue[]>([]);
  const [relatedLoaded,setRelatedLoaded]=useState(false);const [relatedError,setRelatedError]=useState('');
  const [issueRetry,setIssueRetry]=useState(0);
  const [cooking,setCooking]=useState<CookingPreparation|null>(null);
  const [cookingPreview,setCookingPreview]=useState<{value:CookingPreparation;signature:string}|null>(null);
  const [cookingBusy,setCookingBusy]=useState(false);const [cookingError,setCookingError]=useState('');
  const cookingContext=useRef('');
  const preparedContext=useRef('');
  const discardReload=useRef(false);
  useEffect(()=>{discardReload.current=false;},[sourcePlan,requestedFocus,session?.user.user_id]);
  const returnPlan=sourcePlan&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourcePlan)?'/plans/'+encodeURIComponent(sourcePlan):null;
  const returnLabel=returnPlan?'核对修改并更新本次出行 ↗':'返回本次需求，核对并重新确认 ↗';
  const returnRequest=returnPlan?returnPlan+'/update':(sourceRequest&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourceRequest)?'/request/'+encodeURIComponent(sourceRequest):null);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  cookingContext.current=`${sourcePlan??''}:${sourceRequest??''}:${refresh}:${issueRetry}`;
  const [revision, setRevision] = useState(0);
  const [group, setGroup] = useState('');
  const [groupTouched,setGroupTouched]=useState(false);
  const [experience, setExperience] = useState('');
  const [children, setChildren] = useState('unknown');
  const [childrenCount, setChildrenCount] = useState('');
  const [equipment, setEquipment] = useState<EquipmentForm[]>([]);
  const [transport, setTransport] = useState('');
  const [supportedModes,setSupportedModes]=useState<string[]|null>(null);
  const [transportContextError,setTransportContextError]=useState('');
  const [systemPreparation,setSystemPreparation]=useState(false);
  const [requirementCatalogue,setRequirementCatalogue]=useState<RequirementCatalogue|null>(null);
  const [vehicles, setVehicles] = useState('');
  const [km, setKm] = useState('');
  const [assumptions, setAssumptions] = useState('');
  const [accessibility, setAccessibility] = useState('');
  const [busy, setBusy] = useState(false);
  const [savedDraft,setSavedDraft]=useState<Record<string,unknown>|null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const equipmentToSave=equipmentForSave(equipment);
  const quantityConfirmationPending=JSON.stringify(equipmentToSave)!==JSON.stringify(equipment);
  const formDraft={group,experience,children,childrenCount,equipment,transport,vehicles,km,assumptions,accessibility,format:false};
  const unsavedSections=changedSections(savedDraft,formDraft,{group:'同行人数',experience:'露营经验',children:'儿童情况',childrenCount:'儿童人数',equipment:'帐篷及其他装备（数量、容量、确认状态）',transport:'交通方式',vehicles:'车辆数量',km:'预计路程',assumptions:'交通说明',accessibility:'同行特殊需求',format:'资料填写格式'});
  const dirty=unsavedSections.length>0;
  const canSave=dirty||quantityConfirmationPending;
  useEffect(()=>{
    const controller=new AbortController();setRelatedIssues([]);setRelatedLoaded(false);setRelatedError('');setCooking(null);setCookingPreview(null);setCookingError('');
    if(sourcePlan&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourcePlan)){
      privateApi<{plan:{request_id:string};logistics_issues?:LogisticsIssue[];cooking_preparation?:CookingPreparation|null}>('/plans/'+encodeURIComponent(sourcePlan),{signal:controller.signal})
        .then(data=>{if(controller.signal.aborted)return;if(sourceRequest&&data.plan.request_id!==sourceRequest)throw new Error('Request mismatch');
          setRelatedIssues((data.logistics_issues??[]).filter(item=>item.target==='PROFILE'||item.code==='COOKING_ARRANGEMENT'));setCooking(data.cooking_preparation??null);setRelatedLoaded(true);})
        .catch(()=>{if(!controller.signal.aborted){setRelatedError('未能读取本次待补充事项，请重新载入；已有资料仍可编辑。');setRelatedLoaded(true);}});
    }else if(sourceRequest&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourceRequest)){
      privateApi<{cooking_preparation?:CookingPreparation|null}>('/requests/'+encodeURIComponent(sourceRequest),{signal:controller.signal})
        .then(data=>{if(!controller.signal.aborted){setCooking(data.cooking_preparation??null);setRelatedLoaded(true);}})
        .catch(()=>{if(!controller.signal.aborted){setRelatedError('未能读取本次需求的准备清单，请重新载入；已有资料仍可编辑。');setRelatedLoaded(true);}});
    }else setRelatedLoaded(true);
    return()=>controller.abort();
  },[sourcePlan,sourceRequest,refresh,issueRetry]);
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false); setGroupTouched(false); setError(''); setMessage('');setSupportedModes(null);setTransportContextError('');
    const capabilities=privateApi<{supported_transport_modes:string[];system_preparation?:boolean;requirement_choices?:RequirementCatalogue}>('/request-context',{signal:controller.signal})
      .then(value=>{if(!Array.isArray(value.supported_transport_modes))throw new Error('交通支持范围未提供，请更新后端后重新载入页面。');return value;})
      .catch(reason=>{if(!controller.signal.aborted)setTransportContextError(reason instanceof Error?reason.message:'无法读取交通支持范围，请重新载入页面。');return null;});
    Promise.all([privateApi<ProfileResponse>('/profile', { signal: controller.signal }),capabilities]).then(([value,context]) => {
      if (controller.signal.aborted) return;
      const system=context?.system_preparation===true;setSystemPreparation(system);setRequirementCatalogue(context?.requirement_choices??null);setSupportedModes(context?.supported_transport_modes??null);
      setRevision(value.revision); const profile = value.profile;
      setGroup(String(profile?.group_size ?? '')); setExperience(canonical(profile?.experience_level, LEVELS));
      setChildren(profile?.has_children === true ? 'yes' : profile?.has_children === false ? 'no' : 'unknown');
      setChildrenCount(String(profile?.children_count ?? ''));
      const mode=canonical(profile?.transport.transport_type, MODES);
      const raw=profile?.equipment.map(item => ({ item_key: item.item_key, label: item.label, quantity: String(item.quantity ?? ''), unit: item.unit, capacity: String(item.capacity_persons ?? ''), confirmed: item.confirmed })) ?? [];
      const prepared=discardReload.current?raw:prepareProfileEquipment(raw,mode,String(profile?.transport.vehicle_count??''),system);
      setEquipment(prepared);setTransport(mode);setVehicles(mode==='CAR'?(discardReload.current?String(profile?.transport.vehicle_count??''):vehicleCount(prepared)):'');
      setKm(profile?.transport.estimated_km ?? ''); setAssumptions(profile?.transport.assumptions.join('\n') ?? '');
      setAccessibility(profile?.accessibility_requirements.map(item=>termLabel(item,'accessibility')).join('\n') ?? '');
      const aliases = !!profile && (canonical(profile.experience_level, LEVELS) !== (profile.experience_level ?? '') || canonical(profile.transport.transport_type, MODES) !== (profile.transport.transport_type ?? ''));
      const adjusted=!discardReload.current&&(aliases||JSON.stringify(raw)!==JSON.stringify(prepared)||(mode==='CAR'&&String(profile?.transport.vehicle_count??'')!==vehicleCount(prepared)));
      setSavedDraft({group:String(profile?.group_size??''),experience:canonical(profile?.experience_level,LEVELS),children:profile?.has_children===true?'yes':profile?.has_children===false?'no':'unknown',childrenCount:String(profile?.children_count??''),equipment:raw,transport:mode,vehicles:mode==='CAR'?String(profile?.transport.vehicle_count??''):'',km:profile?.transport.estimated_km??'',assumptions:profile?.transport.assumptions.join('\n')??'',accessibility:profile?.accessibility_requirements.map(item=>termLabel(item,'accessibility')).join('\n')??'',format:!discardReload.current&&aliases}); if (adjusted) setMessage('资料填写方式已更新，请核对交通与装备后保存。'); setLoaded(true);
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof ApiFailure ? reason.message : '无法读取资料，请重试。'); if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload(); }
    });
    return () => controller.abort();
  }, [session?.user.user_id, refresh]);
  useEffect(()=>{
    const token=`${session?.user.user_id}:${sourcePlan??''}:${sourceRequest??''}:${requestedFocus}:${refresh}:${issueRetry}:${transport}:${systemPreparation}`;
    if(discardReload.current||!loaded||!relatedLoaded||relatedError||preparedContext.current===token)return;
    preparedContext.current=token;
    const catalog=EQUIPMENT_TYPES.filter(([key])=>!systemPreparation||!PLAN_RECORD_KEYS.has(key));
    const prepared=prepareMissingEquipment(equipment,relatedIssues,requestedFocus,catalog,cooking?.items.map(item=>item.item_key)??[],transport);
    if(prepared!==equipment){setEquipment(prepared);focusDone.current='';}
  },[loaded,relatedLoaded,relatedError,sourcePlan,sourceRequest,requestedFocus,refresh,issueRetry,session?.user.user_id,equipment,relatedIssues,cooking,transport,systemPreparation]);
  const cookingSignature=JSON.stringify(equipmentToSave.filter(item=>['camping_stove','fuel_canister'].includes(item.item_key)));
  async function checkCooking(){
    if(!session||cookingBusy||!relatedLoaded||relatedError||!cooking)return;
    const context=cookingContext.current;const signature=cookingSignature;
    setCookingBusy(true);setCookingError('');
    try{
      const value=await privateApi<CookingPreparation>('/preparation/cooking',{method:'POST',
        headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},
        body:JSON.stringify({...sourcePlan?{plan_id:sourcePlan}:{request_id:sourceRequest},equipment:cookingDraft(equipmentToSave)})});
      if(cookingContext.current===context)setCookingPreview({value,signature});
    }catch(reason){if(cookingContext.current===context){setCookingPreview(null);setCookingError(reason instanceof Error?reason.message:'准备预检查暂不可用，请按正式检查核对。');}}
    finally{setCookingBusy(false);}
  }
  function changed() { setMessage(''); setError(''); }
  function replaceEquipment(items:EquipmentForm[]) {setEquipment(items);if(transport==='CAR')setVehicles(vehicleCount(items));changed();}
  function updateEquipment(index: number, patch: Partial<EquipmentForm>) { replaceEquipment(equipment.map((item, i) => i === index ? { ...item, ...patch } : item)); }
  function removeEquipment(index:number) {replaceEquipment(equipment.filter((_,i)=>i!==index));}
  function changeTransport(mode:string) {const prepared=prepareProfileEquipment(equipment,mode,vehicles,systemPreparation);setEquipment(prepared);setTransport(mode);setVehicles(mode==='CAR'?vehicleCount(prepared):'');changed();}
  async function save(event: FormEvent) {
    event.preventDefault(); if (!session || busy) return;
    setGroupTouched(true);
    const returnAfterSave=(event.nativeEvent as SubmitEvent).submitter?.getAttribute('name')==='save-and-return';
    if (problemIds.length) { setError(issues[problemIds[0]]); document.getElementById(problemIds[0])?.focus(); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const profile: Profile = { group_size: integer(group), experience_level: canonical(experience, LEVELS) || null, has_children: children === 'unknown' ? null : children === 'yes', children_count: integer(childrenCount),
        equipment: equipmentPayload(equipment),
        transport: { transport_type: canonical(transport, MODES) || null, vehicle_count: integer(vehicles), estimated_km: km.trim() || null, assumptions: lines(assumptions) }, accessibility_requirements: canonicalTerms(lines(accessibility),'accessibility') };
      const saved = await privateApi<ProfileResponse>('/profile', { method:'PUT', headers:{ 'Content-Type':'application/json', 'X-CampMate-Client':'1', 'X-CSRF-Token':session.csrf_token }, body:JSON.stringify({ profile, expected_revision:revision }) });
      setRevision(saved.revision); setEquipment(equipmentToSave); setSavedDraft({...formDraft,equipment:equipmentToSave}); setMessage(returnPlan?'资料已保存；当前方案仍使用旧资料，采用新资料后的检查尚未完成。':'露营资料已保存，可以继续填写需求。');
      if(returnAfterSave&&returnRequest)navigate(returnRequest,{state:{profileSaved:true}});
    } catch (reason) {
      setError(reason instanceof ApiFailure ? [reason.message, ...reason.envelope.error.field_errors.map(item => item.message)].join(' ') : reason instanceof Error ? reason.message : '保存失败。');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  const issues: Record<string,string> = {};
  function checkNumber(id:string,value:string,title:string,min:number,required=false) {
    if(!value.trim()){if(required)issues[id]=`请填写${title}。`;return;}
    if(!/^\d+$/.test(value)||!Number.isSafeInteger(Number(value))||Number(value)<min)issues[id]=`${title}请填写${min===0?'非负':'正'}整数。`;
  }
  checkNumber('group-size',group,'小组人数',1,true);
  checkNumber('children-count',childrenCount,'儿童人数',0);
  if(!issues['group-size']&&!issues['children-count']&&group&&childrenCount&&Number(childrenCount)>Number(group))issues['children-count']='儿童人数不能超过小组总人数。';
  checkNumber('vehicle-count',vehicles,'车辆数量',1);
  if(!systemPreparation&&km.trim()&&!/^\d+(\.\d+)?$/.test(km.trim()))issues['estimated-km']='路程请填写非负数字，单位为 km。';
  equipment.forEach((item,index)=>{
    if(systemPreparation&&PLAN_RECORD_KEYS.has(item.item_key))return;
    if(!item.label.trim())issues[`gear-name-${index}`]='请填写装备名称。';
    if(!item.unit.trim())issues[`gear-unit-${index}`]='请选择计量单位。';
    checkNumber(`gear-quantity-${index}`,item.quantity,'数量',0);
    checkNumber(`gear-capacity-${index}`,item.capacity,'每件人数容量',1);
  });
  const equipmentTypes=EQUIPMENT_TYPES.filter(([key])=>!systemPreparation||!PLAN_RECORD_KEYS.has(key));
  const editableEquipment=(item:EquipmentForm)=>item.item_key!=='vehicle'&&(!systemPreparation||!PLAN_RECORD_KEYS.has(item.item_key));
  const guidance=profileGuidance({equipment:equipmentToSave,quantityConfirmsEquipment:true,transport,vehicles,km,children,childrenCount,experience,group,assumptions,systemPreparation},relatedIssues,requestedFocus);
  const guidanceIds=profileCorrectionTargets(guidance,equipmentToSave);
  const problemIds=Object.keys(issues);
  useEffect(()=>{
    if(!loaded||!relatedLoaded||!activeFocus||focusDone.current===activeFocus)return;
    const id=profileFocusId(activeFocus,equipmentToSave,transport,systemPreparation,true); if(id==='add-equipment')return;
    if(id&&focusProfileTargets([id]))focusDone.current=activeFocus;
  },[loaded,relatedLoaded,activeFocus,equipment,transport,systemPreparation]);
  const saveHint=busy?'正在保存资料…':!canSave?revision?(returnPlan?'资料已保存，可以返回方案重新规划。':'资料已保存，可以继续填写需求。'):'填写自己的资料，保存后继续。':problemIds.length?`${issues[problemIds[0]]}${problemIds.length>1?` 另有 ${problemIds.length-1} 项需要修改。`:''}`:quantityConfirmationPending&&!dirty?'核对已填写的实际可用数量，保存即确认这些装备可用于本次出行。':'有未保存的修改，请保存后继续。';
  return <div className="onboarding-page"><TripFlow step={1}/><div className="onboarding-heading"><div><span className="eyebrow">露营资料</span><h1>告诉我们这次出行的准备情况。</h1><p>填写同行人数、装备和交通安排，帮助我们规划适合你的露营方案。</p></div>{loaded&&<span className="onboarding-status">{dirty?'有未保存修改':quantityConfirmationPending?'装备数量待保存确认':revision?'资料已保存':'开始填写'}</span>}</div>
    {error&&<p className="error-box" role="alert">{error}</p>}{message&&<p className="success-box" role="status">{message}</p>}
    {(requestedFocus||relatedIssues.length>0)&&<section className="panel profile-correction-summary" aria-label="补充本次方案资料"><h2>补充本次检查需要的资料</h2>
      <ProfileCorrectionStatus ready={loaded&&relatedLoaded&&!relatedError} loading={!loaded||!relatedLoaded} failed={!!relatedError} targets={guidanceIds} dirty={canSave} returnPlan={!!returnPlan}/>
      <p className="mode-notice">{PROFILE_SAVED_NOTICE.replace('露营资料已保存。','保存资料只更新个人资料。')}</p><p className="muted">{dirty?'修改后的资料需要保存。':''}没有的物品可填 0；尚未确定的装备数量请留空。</p>
      {returnRequest&&!canSave&&<Link className="text-link" to={returnRequest}>{returnLabel}</Link>}
    </section>}
    {relatedError&&<div className="error-box" role="alert"><p>{relatedError}</p><button type="button" className="secondary-button" onClick={()=>setIssueRetry(value=>value+1)}>重新载入</button></div>}
    {!loaded?<section className="panel"><p>正在读取资料…</p><button className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>重新读取</button></section>:<form className="profile-form" onSubmit={save}><fieldset disabled={busy}>
      <div className="profile-intro"><span>填写自己的露营资料</span><p>不确定的数量与容量可以留空，后续评估会提示需要补充的信息。</p></div>

      <div className="bottom-grid profile-main-grid"><section className="panel"><div className="section-title"><span className="eyebrow">同行小组</span><h2>小组信息</h2></div><div className="form-grid">
        <GroupSizeField value={group} error={issues['group-size']} guidance={guidance['group-size']} revealValidation={groupTouched} onTouch={()=>setGroupTouched(true)} onChange={value=>{setGroup(value);changed();}}/>
        <div><label htmlFor="experience">露营经验</label><select id="experience" aria-invalid={!!guidance.experience} aria-describedby="experience-hint" value={experience} onChange={event=>{setExperience(event.target.value);changed();}}><option value="">尚未明确</option>{LEVELS.map(([key,label])=><option key={key} value={key}>{label}</option>)}{experience&&!LEVELS.some(([key])=>key===experience)&&<option value={experience}>{experience}</option>}</select><FieldHint id="experience-hint" error={guidance.experience}/></div>
        <div><label htmlFor="has-children">是否有儿童</label><select id="has-children" aria-invalid={!!guidance['has-children']} aria-describedby="has-children-hint" value={children} onChange={event=>{setChildren(event.target.value);if(event.target.value==='no')setChildrenCount('0');changed();}}><option value="unknown">尚未明确</option><option value="yes">有儿童</option><option value="no">没有儿童</option></select><FieldHint id="has-children-hint" error={guidance['has-children']}/></div>
        <div><label htmlFor="children-count">儿童人数</label><input id="children-count" type="number" min="0" step="1" value={childrenCount} disabled={children==='no'} aria-invalid={!!(issues['children-count']||guidance['children-count'])} aria-describedby="children-hint" onChange={event=>{setChildrenCount(event.target.value);changed();}}/><FieldHint id="children-hint" error={issues['children-count']??guidance['children-count']}>{children==='no'?'已记录为 0 人。':'计入小组总人数；未知可留空。'}</FieldHint></div>
      </div><RequirementChoices id="accessibility" title="同行特殊需求" value={accessibility} choices={requirementCatalogue?.fields.accessibility_requirements??null} onChange={value=>{setAccessibility(value);changed();}} hint="可多选。系统会按这些要求筛选营地。其他要求可先保存，之后在露营请求中提交人工协助。"/></section>
      <section className="panel"><div className="section-title"><span className="eyebrow">出行交通</span><h2>交通安排</h2></div><TransportModeField value={transport} supported={supportedModes} onChange={changeTransport} error={transportContextError} guidance={guidance.transport} systemPreparation={systemPreparation}/><div className="form-grid">
        {!systemPreparation&&<div><label htmlFor="estimated-km">预计总路程 km</label><input id="estimated-km" inputMode="decimal" pattern="[0-9]+([.][0-9]+)?" value={km} aria-invalid={!!(issues['estimated-km']||guidance['estimated-km'])} aria-describedby="km-hint" onChange={event=>{setKm(event.target.value);changed();}}/><FieldHint id="km-hint" error={issues['estimated-km']??guidance['estimated-km']}>填写总路程，未知可留空。</FieldHint></div>}
      </div>{(transport==='CAR'||!systemPreparation&&equipment.some(item=>item.item_key==='vehicle'))&&<VehicleFields equipment={equipment} issues={issues} guidance={guidance} onChange={updateEquipment} onRemove={removeEquipment} onAdd={()=>replaceEquipment([...equipment,{item_key:'vehicle',label:'车辆',quantity:'',unit:'vehicle',capacity:'',confirmed:false}])}/>}{!systemPreparation&&<><label htmlFor="transport-assumptions">{transport==='PUBLIC_TRANSPORT'?'已核对的往返与最后接驳安排（每行一项）':'路程与交通说明（每行一项）'}</label><textarea id="transport-assumptions" value={assumptions} aria-invalid={!!guidance['transport-assumptions']} aria-describedby="transport-assumptions-hint" placeholder={transport==='PUBLIC_TRANSPORT'?'去程：出发点与换乘方式；返程：离开安排；最后接驳：下车或下船后如何到营地。未知内容请注明待确认。':'例如：往返合计，使用自己的车辆'} onChange={event=>{setAssumptions(event.target.value);changed();}}/><FieldHint id="transport-assumptions-hint" error={guidance['transport-assumptions']}>{transport==='PUBLIC_TRANSPORT'?'另请在下方交通连接计划中登记一份计划；只有核实安排后才勾选确认。未知信息可以先保存，正式检查会保留缺项。':undefined}</FieldHint></>}</section></div>
      <CookingPreparationPanel value={cooking} preview={cookingPreview?.value} stale={!!cookingPreview&&cookingPreview.signature!==cookingSignature}
        onCheck={checkCooking} busy={cookingBusy} error={cookingError} onFocus={key=>{const index=equipment.findIndex(item=>item.item_key===key);const node=document.getElementById(`gear-quantity-${index}`);node?.focus();node?.scrollIntoView({block:'center'});}}/>
      <section className="panel equipment-panel"><div className="panel-title"><div><span className="eyebrow">装备准备</span><h2>已有装备 <small>{equipment.filter(editableEquipment).length} 项</small></h2></div><button id="add-equipment" type="button" className="secondary-button" onClick={()=>{const key=activeFocus.split('.')[1];const type=equipmentTypes.find(([value])=>value===key&&value!=='vehicle')??equipmentTypes[0];focusDone.current='';setEquipment(items=>addEquipment(items,type[0],datasetVersion));changed();}}>添加装备</button></div><p className="field-hint">类别用于装备检查，名称用于区分同类物品，可改为“三人帐”“单人帐”等。不同容量请分行添加；每行数量表示该名称下有几件物品。帐篷按顶、水按升、餐食按份记录；仅“其他装备”可选择单位。保存数量即确认该数量可用于本次出行。</p>
        {!equipment.some(editableEquipment)&&<div className="equipment-empty"><span aria-hidden="true">＋</span><p>还没有登记装备</p><small>添加已有物品；不确定的数量可以留空。</small></div>}
        {equipment.map((item,index)=>!editableEquipment(item)?null:<article className={Object.keys(guidance).some(id=>id.startsWith('gear-')&&id.endsWith('-'+index))?'equipment-card equipment-card-needed':'equipment-card'} key={index}><header><span className="equipment-number">{String(equipment.slice(0,index).filter(editableEquipment).length+1).padStart(2,'0')}</span><h3>{item.label||'未命名装备'}</h3><button type="button" className="text-button" aria-label={`移除装备 ${index+1}`} onClick={()=>removeEquipment(index)}>移除</button></header><div className="equipment-fields">
          <div><label htmlFor={`gear-type-${index}`}>类别</label><select id={`gear-type-${index}`} aria-label={`装备 ${index+1} 类别`} value={item.item_key} onChange={event=>replaceEquipment(changeEquipmentCategory(equipment,index,event.target.value,datasetVersion))}>{equipmentTypes.filter(([key])=>key!=='vehicle').map(([key,label])=><option key={key} value={key}>{label}</option>)}{!EQUIPMENT_TYPES.some(([key])=>key===item.item_key)&&<option value={item.item_key}>{item.label}</option>}</select></div>
          <div><label htmlFor={`gear-name-${index}`}>名称</label><input id={`gear-name-${index}`} aria-label={`装备 ${index+1} 名称`} required value={item.label} aria-invalid={!!(issues[`gear-name-${index}`]||guidance[`gear-name-${index}`])} aria-describedby={`gear-name-hint-${index}`} onChange={event=>updateEquipment(index,{label:event.target.value})}/><FieldHint id={`gear-name-hint-${index}`} error={issues[`gear-name-${index}`]??guidance[`gear-name-${index}`]}/></div>
          <div><label htmlFor={`gear-quantity-${index}`}>数量</label><input id={`gear-quantity-${index}`} aria-label={`装备 ${index+1} 数量`} type="number" min="0" step="1" value={item.quantity} aria-invalid={!!(issues[`gear-quantity-${index}`]||guidance[`gear-quantity-${index}`])} aria-describedby={`gear-quantity-hint-${index}`} placeholder="未知" onChange={event=>updateEquipment(index,{quantity:event.target.value})}/><FieldHint id={`gear-quantity-hint-${index}`} error={issues[`gear-quantity-${index}`]??guidance[`gear-quantity-${index}`]}>{item.item_key==='vehicle'?'填写本次实际可用的车辆数，不含尚未落实的借车。':undefined}</FieldHint></div>
          <EquipmentUnitField item={item} index={index} datasetVersion={datasetVersion} error={issues[`gear-unit-${index}`]??guidance[`gear-unit-${index}`]} onChange={unit=>updateEquipment(index,{unit})}/>
          <div><label htmlFor={`gear-capacity-${index}`}>{item.item_key==='vehicle'?'每辆载客人数（含驾驶员）':item.item_key==='tent'?'每顶帐篷可住人数':'每件人数容量'}</label><input id={`gear-capacity-${index}`} aria-label={`装备 ${index+1} 每件人数容量`} type="number" min="1" step="1" value={item.capacity} aria-invalid={!!(issues[`gear-capacity-${index}`]||guidance[`gear-capacity-${index}`])} aria-describedby={`gear-capacity-hint-${index}`} placeholder="未知 / 不适用" onChange={event=>updateEquipment(index,{capacity:event.target.value})}/><FieldHint id={`gear-capacity-hint-${index}`} error={issues[`gear-capacity-${index}`]??guidance[`gear-capacity-${index}`]}>{item.item_key==='vehicle'?'包含驾驶员；例如 5 座车填 5。多辆车容量不同时请分行登记。':undefined}</FieldHint></div>
        </div>{PLAN_RECORD_KEYS.has(item.item_key)&&<><label className="checkbox-label equipment-confirmation"><input id={`gear-confirmed-${index}`} type="checkbox" aria-invalid={!!guidance[`gear-confirmed-${index}`]} aria-describedby={`gear-confirmed-hint-${index}`} checked={item.confirmed} aria-label={`计划 ${index+1} 已核对安排`} onChange={event=>updateEquipment(index,{confirmed:event.target.checked})}/>已核对本次安排</label><FieldHint id={`gear-confirmed-hint-${index}`} error={guidance[`gear-confirmed-${index}`]}/></>}</article>)}
      </section>
      <div className="profile-save-bar"><div><strong>{dirty?(returnRequest?'保存后，核对本次更新':'保存后，继续填写需求'):'准备下一步'}</strong><p id="profile-save-hint" role="status">{saveHint}</p>{problemIds.length>0&&dirty&&<button type="button" className="text-link focus-field" onClick={()=>document.getElementById(problemIds[0])?.focus()}>前往需要修改的字段 ↗</button>}</div><div className="form-actions">{returnRequest&&<button type="submit" name="save-and-return" className="primary-button" disabled={!canSave||problemIds.length>0} aria-describedby="profile-save-hint">{busy?'正在保存…':'保存并核对本次更新'} <span>↗</span></button>}<button className={returnRequest?"secondary-button":"primary-button"} disabled={!canSave||problemIds.length>0} aria-describedby="profile-save-hint">{busy?'正在保存…':returnRequest?'仅保存资料，暂不检查':'保存露营资料'} <span>✓</span></button><DiscardChanges sections={unsavedSections} busy={busy} onDiscard={()=>{discardReload.current=true;preparedContext.current='';setRefresh(value=>value+1);}}/>{!canSave&&revision>0&&<Link className="text-link" to={returnRequest??"/request"}>{returnRequest?returnLabel:"填写露营请求 ↗"}</Link>}</div></div>
    </fieldset></form>}
  </div>;
}

export function ProfileCorrectionStatus({ready,loading,failed,targets,dirty,returnPlan}:{
  ready:boolean;loading:boolean;failed:boolean;targets:string[];dirty:boolean;returnPlan:boolean;
}){
  const [navigationFailed,setNavigationFailed]=useState(false);
  return <><p>{loading?'正在载入本次需要补充的位置…':failed?'待补充事项未能完整载入，请重试。':targets.length
    ?`下方 ${targets.length} 处需要补充或核对，已在对应位置标红。请按实际安排填写。`
    :dirty?'当前表单没有待补充提示。请先保存修改，再核对本次安排。'
    :'当前表单没有待补充提示。资料已保存；这不代表原方案的问题已解决，请核对修改并明确启动新检查。'}</p>
    {ready&&targets.length>0&&<button type="button" className="secondary-button" onClick={()=>setNavigationFailed(!focusProfileTargets(targets))}>前往首个待补充位置 ↓</button>}
    {navigationFailed&&targets.length>0&&<p role="status">待补充字段暂时无法定位，请重新载入资料后再试。</p>}
    {ready&&targets.length===0&&returnPlan&&<p className="muted">原方案仍保留上次确认的资料与检查结果；采用新资料需要先核对，再重新检查。</p>}
  </>;
}

export function ProfileSummary({ profile, systemPreparation=false }: { profile: Profile | null;systemPreparation?:boolean }) {
  if (!profile) return <p>尚无资料快照，请先填写露营资料。</p>;
  const gear=profile.equipment.filter(item=>!['vehicle','charged_phone'].includes(item.item_key)&&(!systemPreparation||!PLAN_RECORD_KEYS.has(item.item_key)));
  const historicalPlans=profile.equipment.filter(item=>PLAN_RECORD_KEYS.has(item.item_key));
  const fleet=profile.equipment.filter(item=>item.item_key==='vehicle');
  return <><dl className="summary-list"><div><dt>小组人数</dt><dd>{profile.group_size ?? '未知'}</dd></div><div><dt>露营经验</dt><dd>{Object.fromEntries(LEVELS)[canonical(profile.experience_level, LEVELS)] ?? profile.experience_level ?? '未知'}</dd></div><div><dt>儿童情况</dt><dd>{profile.has_children === false ? '没有儿童' : profile.has_children === true ? `有儿童，人数 ${profile.children_count ?? '未知'}` : `尚未明确${profile.children_count === null ? '' : `，登记人数 ${profile.children_count}`}`}</dd></div><div><dt>交通方式</dt><dd>{Object.fromEntries(MODES)[canonical(profile.transport.transport_type, MODES)] ?? profile.transport.transport_type ?? '未知'}</dd></div>{(!systemPreparation||profile.transport.transport_type==='CAR')&&<div><dt>{systemPreparation?'车辆数量':'车辆 / 总路程'}</dt><dd>{profile.transport.vehicle_count ?? '未知'} 辆{!systemPreparation&&<> / {profile.transport.estimated_km ?? '未知'} km</>}</dd></div>}</dl>{fleet.length>0&&(!systemPreparation||profile.transport.transport_type==='CAR')&&<><h3>车辆安排</h3><ul>{fleet.map((item,index)=><li key={index}>{item.quantity??'未知'} 辆，每辆 {item.capacity_persons??'未知'} 人（含驾驶员），{item.confirmed?'已确认可用':'尚未确认'}</li>)}</ul></>}<h3>登记装备</h3>{gear.length === 0 ? <p className="muted">未登记，尚未进行装备评估。</p> : <ul className="equipment-summary">{gear.map((item,index) => <li key={index}>{item.label||equipmentLabel(item.item_key)}：{item.quantity ?? '未知'} {item.item_key==='tent'?'顶':unitLabel(item.unit)}，{item.item_key==='tent'?'每顶可住人数':'每件人数容量'} {item.capacity_persons ?? '未知'}{item.item_key==='tent'&&item.unit==='item'&&item.quantity!==null&&item.capacity_persons!==null?`，该行总住宿容量 ${item.quantity*item.capacity_persons} 人`:''}，{item.confirmed ? '已核实拥有' : '未核实'}</li>)}</ul>}{profile.accessibility_requirements.length > 0 && <><h3>同行需求</h3><ul>{profile.accessibility_requirements.map((item,index) => <li key={index}>{termLabel(item,'accessibility')}</li>)}</ul></>}{!systemPreparation&&profile.transport.assumptions.length > 0 && <><h3>交通估算说明</h3><ul>{profile.transport.assumptions.map((item,index) => <li key={index}>{item}</li>)}</ul></>}{systemPreparation&&historicalPlans.length>0&&<details><summary>旧版计划登记记录（仅供历史回看）</summary><ul>{historicalPlans.map((item,index)=><li key={index}>{item.label}：{item.quantity??'未知'} {unitLabel(item.unit)}，{item.confirmed?'原登记已确认':'原登记未确认'}</li>)}</ul><p>本次不将这些记录作为装备或可达证明。</p></details>}</>;
}
