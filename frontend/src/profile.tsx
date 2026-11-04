import {legacyEquipmentName} from './legacy_equipment_names';
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
  ['tent','Tent','item'],['groundsheet','Groundsheet','item'],['tent_repair_kit','Tent repair kit','item'],
  ['sleeping_bag','Sleeping bag','item'],['sleeping_mat','Sleeping mat','item'],['warm_liner','Warm liner','item'],
  ['rain_jacket','Raincoat','item'],['warm_layers','Warm clothing','item'],['sun_hat','Sun hat','item'],
  ['windproof_outer_layer','Windproof jacket','item'],['camping_stove','Camping stove','item'],['fuel_canister','Fuel canister','item'],
  ['cooking_pot','Cookware','item'],['drinking_water','Drinking water','litre'],['meal_supplies','Meals','portion'],
  ['child_snacks','Child snacks','portion'],['offline_map','Offline map','item'],
  ['power_bank','Power bank','item'],['first_aid_kit','First-aid kit','item'],['torch','Headlamp / Torch','item'],
  ['whistle','Whistle','item'],['emergency_contact_card','Emergency contact card','item'],['hand_sanitiser','Hand sanitiser','item'],
  ['toilet_kit','Hygiene supplies','item'],['vehicle','Vehicles','vehicle'],['transport_itinerary','Transport connection plan','plan'],
  ['fire_free_meal_plan','Fire-free meal plan','plan'],['water_container','Water container','item'],['other','Other equipment','item'],
];
const LEVELS = [['BEGINNER','First time / Beginner'],['INTERMEDIATE','Some experience'],['EXPERIENCED','Experienced'],['ADVANCED','Advanced / Advanced']];
const MODES = [['CAR','Car'],['PUBLIC_TRANSPORT','Public transport'],['WALKING','Walking'],['OTHER','Other']];
export function PublicTransportNotice(){
  return <p className="mode-notice">Check outbound, return and final connections to the campsite yourself. The system uses registered access flags and estimated return costs. It does not query actual services, last departures or live fares, and does not confirm ticket bookings.</p>;
}
export function SystemPreparationNotice({mode}:{mode:string}){
  if(mode==='CAR')return null;
  return <p className="mode-notice">Public transport uses campsite access information and estimated return costs. Verify actual outbound, return and final connections after choosing a campsite. You do not need to plan a route first.</p>;
}
export function TransportModeField({value,supported,onChange,error,guidance}:{
  value:string;supported:string[]|null;onChange:(value:string)=>void;error:string;guidance?:string;systemPreparation?:boolean;
}){
  const choices=MODES.filter(([key])=>supported?.includes(key)&&['CAR','PUBLIC_TRANSPORT'].includes(key));
  const unsupported=supported!==null&&!!value&&!choices.some(([key])=>key===value);
  return <><label htmlFor="transport">Transport mode</label><select id="transport" disabled={supported===null}
    aria-invalid={!!guidance||unsupported} aria-describedby="transport-hint" value={value} onChange={event=>onChange(event.target.value)}>
    <option value="" disabled hidden>Choose a transport mode</option>{choices.map(([key,label])=><option key={key} value={key}>{label}</option>)}
    {value&&!choices.some(([key])=>key===value)&&<option value={value} disabled>{Object.fromEntries(MODES)[value]??value}({supported===null?'Saved; loading supported options':'Historical mode; currently unsupported'})</option>}
  </select><FieldHint id="transport-hint" error={error||guidance||(unsupported?'The previous transport mode is retained but cannot be used for new planning. Select a supported mode and regenerate the summary.':undefined)}>{supported===null?'Loading supported transport modes…':null}</FieldHint>
  </>;
}
export const equipmentLabel = (key: string) => EQUIPMENT_TYPES.find(([type])=>type===key)?.[1] ?? key;
export const displayEquipmentName=(key:string,name:string)=>legacyEquipmentName(key,name,equipmentLabel(key));
const unitLabel = (unit: string) => ({item:'items',litre:'litres',portion:'portions',vehicle:'vehicles',plan:'plans',set:'sets'} as Record<string,string>)[unit] ?? unit;
const EQUIPMENT_UNITS=[['item','items'],['litre','litres'],['portion','portions'],['vehicle','vehicles'],['plan','plans'],['set','sets']];
export function fixedEquipmentUnit(key:string,datasetVersion?:string|null){
  if(key==='other')return null;
  return key==='warm_layers'&&datasetVersion==='v1'?'set':EQUIPMENT_TYPES.find(([type])=>type===key)?.[2]??null;
}
function equipmentNumber(number:number):string { return ' '+String(number); }
function distinctEquipmentNames(items:EquipmentForm[],key:string):EquipmentForm[]{
  const base=equipmentLabel(key);
  const used=new Set(items.filter(item=>item.item_key===key&&item.label.trim()&&displayEquipmentName(key,item.label)!==base).map(item=>displayEquipmentName(key,item.label).trim()));
  return items.map(item=>{
    if(item.item_key!==key||(item.label.trim()&&displayEquipmentName(key,item.label)!==base))return item;
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
  const displayed=displayEquipmentName(previous.item_key,previous.label);
  const automatic=displayed===base||displayed.startsWith(base)&&/^(?:[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+|\s*\d+)$/.test(displayed.slice(base.length));
  return distinctEquipmentNames(items.map((item,i)=>i===index?{...item,item_key:key,
    label:automatic||!item.label.trim()?equipmentLabel(key):item.label,
    unit:fixedEquipmentUnit(key,datasetVersion)??item.unit}:item),key);
}
export function EquipmentUnitField({item,index,datasetVersion,error,onChange}:{
  item:EquipmentForm;index:number;datasetVersion?:string|null;error?:string;onChange:(unit:string)=>void;
}){
  const expected=fixedEquipmentUnit(item.item_key,datasetVersion);
  const mismatch=item.item_key!=='other'&&expected!==null&&expected!==item.unit;
  const label=item.item_key==='tent'&&item.unit==='item'?'tents':unitLabel(item.unit);
  return <div><label htmlFor={`gear-unit-${index}`}>Unit</label>
    {item.item_key==='other'?<select id={`gear-unit-${index}`} aria-label={`Equipment ${index+1} Unit`} required
      value={item.unit} aria-invalid={!!error} aria-describedby={`gear-unit-hint-${index}`} onChange={event=>onChange(event.target.value)}>
      {EQUIPMENT_UNITS.map(([key,title])=><option key={key} value={key}>{title}</option>)}
      {!EQUIPMENT_UNITS.some(([key])=>key===item.unit)&&<option value={item.unit}>{item.unit||'Select unit'}</option>}
    </select>:<input id={`gear-unit-${index}`} aria-label={`Equipment ${index+1} Unit`} readOnly value={label}
      aria-invalid={!!error||mismatch} aria-describedby={`gear-unit-hint-${index}`}/>}
    <FieldHint id={`gear-unit-hint-${index}`} error={error??(mismatch?'The saved unit does not match the category. Correct it before saving.':undefined)}>
      {item.item_key==='other'?'Select the actual measurement unit for this item.':'The category determines the unit.'}
    </FieldHint>
    {mismatch&&<button type="button" className="text-button" onClick={()=>onChange(expected!)}>Correct unit to match category</button>}
  </div>;
}
const canonical = (value: string | null | undefined, choices: string[][]) => choices.find(([key]) => key.toLowerCase() === value?.trim().toLowerCase())?.[0] ?? value ?? '';


export function lines(value: string): string[] { return value.split('\n').map(line => line.trim()).filter(Boolean); }
export function integer(value: string): number | null {
  if (!value.trim()) return null;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value))) throw new Error('Enter valid whole numbers for group size, quantity and capacity.');
  return Number(value);
}

export function GroupSizeField({value,error,guidance,revealValidation,onTouch,onChange}:{
  value:string;error?:string;guidance?:string;revealValidation:boolean;
  onTouch:()=>void;onChange:(value:string)=>void;
}){
  const visibleError=(revealValidation?error:undefined)??guidance;
  return <div><label htmlFor="group-size" className="required-field-label"><span>Group size (including children)</span> <span className="required-mark">Required</span></label>
    <input id="group-size" type="number" min="1" step="1" required value={value}
      aria-invalid={!!visibleError} aria-describedby="group-hint" onBlur={onTouch} onInvalid={onTouch}
      onChange={event=>onChange(event.target.value)}/>
    <FieldHint id="group-hint" error={visibleError}>Include everyone travelling.</FieldHint>
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
  const returnLabel=returnPlan?'Review changes and update this trip ↗':'Return to this request, review and reconfirm ↗';
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
  const unsavedSections=changedSections(savedDraft,formDraft,{group:'Group size',experience:'Camping experience',children:'Children in the group',childrenCount:'Number of children',equipment:'Tents and other equipment (quantity, capacity, confirmation)',transport:'Transport mode',vehicles:'Number of vehicles',km:'Estimated distance',assumptions:'Transport notes',accessibility:'Group accessibility and other needs',format:'Profile input format'});
  const dirty=unsavedSections.length>0;
  const canSave=dirty||quantityConfirmationPending;
  useEffect(()=>{
    const controller=new AbortController();setRelatedIssues([]);setRelatedLoaded(false);setRelatedError('');setCooking(null);setCookingPreview(null);setCookingError('');
    if(sourcePlan&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourcePlan)){
      privateApi<{plan:{request_id:string};logistics_issues?:LogisticsIssue[];cooking_preparation?:CookingPreparation|null}>('/plans/'+encodeURIComponent(sourcePlan),{signal:controller.signal})
        .then(data=>{if(controller.signal.aborted)return;if(sourceRequest&&data.plan.request_id!==sourceRequest)throw new Error('Request mismatch');
          setRelatedIssues((data.logistics_issues??[]).filter(item=>item.target==='PROFILE'||item.code==='COOKING_ARRANGEMENT'));setCooking(data.cooking_preparation??null);setRelatedLoaded(true);})
        .catch(()=>{if(!controller.signal.aborted){setRelatedError('Could not load the tasks for this check. Reload; existing profile information remains editable.');setRelatedLoaded(true);}});
    }else if(sourceRequest&&/^[a-zA-Z0-9_-]{1,100}$/.test(sourceRequest)){
      privateApi<{cooking_preparation?:CookingPreparation|null}>('/requests/'+encodeURIComponent(sourceRequest),{signal:controller.signal})
        .then(data=>{if(!controller.signal.aborted){setCooking(data.cooking_preparation??null);setRelatedLoaded(true);}})
        .catch(()=>{if(!controller.signal.aborted){setRelatedError('Could not load the preparation checklist for this request. Reload; existing profile information remains editable.');setRelatedLoaded(true);}});
    }else setRelatedLoaded(true);
    return()=>controller.abort();
  },[sourcePlan,sourceRequest,refresh,issueRetry]);
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false); setGroupTouched(false); setError(''); setMessage('');setSupportedModes(null);setTransportContextError('');
    const capabilities=privateApi<{supported_transport_modes:string[];system_preparation?:boolean;requirement_choices?:RequirementCatalogue}>('/request-context',{signal:controller.signal})
      .then(value=>{if(!Array.isArray(value.supported_transport_modes))throw new Error('Transport capabilities were not provided. Update the backend and reload the page.');return value;})
      .catch(reason=>{if(!controller.signal.aborted)setTransportContextError(reason instanceof Error?reason.message:'Could not read transport capabilities. Reload the page.');return null;});
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
      setSavedDraft({group:String(profile?.group_size??''),experience:canonical(profile?.experience_level,LEVELS),children:profile?.has_children===true?'yes':profile?.has_children===false?'no':'unknown',childrenCount:String(profile?.children_count??''),equipment:raw,transport:mode,vehicles:mode==='CAR'?String(profile?.transport.vehicle_count??''):'',km:profile?.transport.estimated_km??'',assumptions:profile?.transport.assumptions.join('\n')??'',accessibility:profile?.accessibility_requirements.map(item=>termLabel(item,'accessibility')).join('\n')??'',format:!discardReload.current&&aliases}); if (adjusted) setMessage('The profile input method changed. Review transport and equipment before saving.'); setLoaded(true);
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof ApiFailure ? reason.message : 'Could not read the profile. Please retry.'); if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload(); }
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
  const savedCookingSignature=JSON.stringify(equipmentForSave((savedDraft?.equipment??[]) as EquipmentForm[]).filter(item=>['camping_stove','fuel_canister'].includes(item.item_key)));
  const cookingEdited=savedDraft!==null&&cookingSignature!==savedCookingSignature;
  async function checkCooking(){
    if(!session||cookingBusy||!relatedLoaded||relatedError||!cooking)return;
    const context=cookingContext.current;const signature=cookingSignature;
    setCookingBusy(true);setCookingError('');
    try{
      const value=await privateApi<CookingPreparation>('/preparation/cooking',{method:'POST',
        headers:{'Content-Type':'application/json','X-CampMate-Client':'1','X-CSRF-Token':session.csrf_token},
        body:JSON.stringify({...sourcePlan?{plan_id:sourcePlan}:{request_id:sourceRequest},equipment:cookingDraft(equipmentToSave)})});
      if(cookingContext.current===context)setCookingPreview({value,signature});
    }catch(reason){if(cookingContext.current===context){setCookingPreview(null);setCookingError(reason instanceof Error?reason.message:'Preparation precheck is unavailable. Refer to formal checks.');}}
    finally{setCookingBusy(false);}
  }
  function changed() { setMessage(''); setError(''); }
  function appendEquipment() { const key=activeFocus.split('.')[1];const type=equipmentTypes.find(([value])=>value===key&&value!=='vehicle')??equipmentTypes[0];focusDone.current='';setEquipment(items=>addEquipment(items,type[0],datasetVersion));changed(); }
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
      setRevision(saved.revision); setEquipment(equipmentToSave); setSavedDraft({...formDraft,equipment:equipmentToSave}); setMessage(returnPlan?'Profile saved. The current plan still uses old information. Checks using the new profile are incomplete.':'Camping profile saved. Continue entering requirements.');
      if(returnAfterSave&&returnRequest)navigate(returnRequest,{state:{profileSaved:true}});
    } catch (reason) {
      setError(reason instanceof ApiFailure ? [reason.message, ...reason.envelope.error.field_errors.map(item => item.message)].join(' ') : reason instanceof Error ? reason.message : 'Save failed.');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  const issues: Record<string,string> = {};
  function checkNumber(id:string,value:string,title:string,min:number,required=false) {
    if(!value.trim()){if(required)issues[id]=`Please enter${title}.`;return;}
    if(!/^\d+$/.test(value)||!Number.isSafeInteger(Number(value))||Number(value)<min)issues[id]=`${title}Please enter${min===0?'nonnegative ':'positive '}whole number.`;
  }
  checkNumber('group-size',group,'Group size',1,true);
  checkNumber('children-count',childrenCount,'Number of children',0);
  if(!issues['group-size']&&!issues['children-count']&&group&&childrenCount&&Number(childrenCount)>Number(group))issues['children-count']='Child count cannot exceed total group size.';
  checkNumber('vehicle-count',vehicles,'Number of vehicles',1);
  if(!systemPreparation&&km.trim()&&!/^\d+(\.\d+)?$/.test(km.trim()))issues['estimated-km']='Enter a nonnegative distance in km.';
  equipment.forEach((item,index)=>{
    if(systemPreparation&&PLAN_RECORD_KEYS.has(item.item_key))return;
    if(!item.label.trim())issues[`gear-name-${index}`]='Enter an equipment name.';
    if(!item.unit.trim())issues[`gear-unit-${index}`]='Select a measurement unit.';
    checkNumber(`gear-quantity-${index}`,item.quantity,'Quantity',0);
    checkNumber(`gear-capacity-${index}`,item.capacity,'People accommodated per item',1);
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
  const saveHint=busy?'Saving profile…':!canSave?revision?(returnPlan?'Profile saved. Return to the plan to replan.':'Profile saved. Continue entering requirements.'):'Complete your profile and save to continue.':problemIds.length?`${issues[problemIds[0]]}${problemIds.length>1?` Another ${problemIds.length-1} fields need attention.`:''}`:quantityConfirmationPending&&!dirty?'Review the available quantities entered. Saving confirms this equipment is available for the trip.':'Unsaved changes. Save before continuing.';
  return <div className="onboarding-page"><TripFlow step={1}/><div className="onboarding-heading"><div><span className="eyebrow">Camping profile</span><h1>Tell us how you are preparing for this trip.</h1><p>Enter group size, equipment and transport to help plan a suitable camping trip.</p></div>{loaded&&<span className="onboarding-status">{dirty?'Unsaved changes':quantityConfirmationPending?'Equipment quantities await save confirmation':revision?'Profile saved':'Start entering details'}</span>}</div>
    {error&&<p className="error-box" role="alert">{error}</p>}{message&&<p className="success-box" role="status">{message}</p>}
    {(requestedFocus||relatedIssues.length>0)&&<section className="panel profile-correction-summary" aria-label="Complete profile for this plan"><h2>Complete information for this check</h2>
      <ProfileCorrectionStatus ready={loaded&&relatedLoaded&&!relatedError} loading={!loaded||!relatedLoaded} failed={!!relatedError} targets={guidanceIds} dirty={canSave} returnPlan={!!returnPlan}/>
      <p className="mode-notice">{PROFILE_SAVED_NOTICE.replace('Camping profile saved.','Saving only updates your personal profile.')}</p><p className="muted">{dirty?'Save the changed profile information.':''}For unavailable items, enter  0; Leave unverified equipment quantities blank.</p>
      {returnRequest&&!canSave&&<Link className="text-link" to={returnRequest}>{returnLabel}</Link>}
    </section>}
    {relatedError&&<div className="error-box" role="alert"><p>{relatedError}</p><button type="button" className="secondary-button" onClick={()=>setIssueRetry(value=>value+1)}>Reload</button></div>}
    {!loaded?<section className="panel"><p>Loading profile…</p><button className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>Reload</button></section>:<form className="profile-form" onSubmit={save}><fieldset disabled={busy}>
      <div className="profile-intro"><span>Enter your camping profile</span><p>Leave uncertain quantities and capacities blank. Later assessments identify missing information.</p></div>

      <div className="bottom-grid profile-main-grid"><section className="panel group-information"><div className="section-title"><span className="eyebrow">Travel group</span><h2>Group information</h2></div><div className="form-grid">
        <GroupSizeField value={group} error={issues['group-size']} guidance={guidance['group-size']} revealValidation={groupTouched} onTouch={()=>setGroupTouched(true)} onChange={value=>{setGroup(value);changed();}}/>
        <div><label htmlFor="experience">Camping experience</label><select id="experience" aria-invalid={!!guidance.experience} aria-describedby="experience-hint" value={experience} onChange={event=>{setExperience(event.target.value);changed();}}><option value="">Not yet specified</option>{LEVELS.map(([key,label])=><option key={key} value={key}>{label}</option>)}{experience&&!LEVELS.some(([key])=>key===experience)&&<option value={experience}>{experience}</option>}</select><FieldHint id="experience-hint" error={guidance.experience}/></div>
        <div><label htmlFor="has-children">Children travelling</label><select id="has-children" aria-invalid={!!guidance['has-children']} aria-describedby="has-children-hint" value={children} onChange={event=>{setChildren(event.target.value);if(event.target.value==='no')setChildrenCount('0');changed();}}><option value="unknown">Not yet specified</option><option value="yes">Children included</option><option value="no">No children</option></select><FieldHint id="has-children-hint" error={guidance['has-children']}/></div>
        <div><label htmlFor="children-count">Number of children</label><input id="children-count" type="number" min="0" step="1" value={childrenCount} disabled={children==='no'} aria-invalid={!!(issues['children-count']||guidance['children-count'])} aria-describedby="children-hint" onChange={event=>{setChildrenCount(event.target.value);changed();}}/><FieldHint id="children-hint" error={issues['children-count']??guidance['children-count']}>{children==='no'?'Recorded as 0 people.':'Included in total group size. Leave blank if unknown.'}</FieldHint></div>
      </div><RequirementChoices id="accessibility" title="Group accessibility and other needs" value={accessibility} choices={requirementCatalogue?.fields.accessibility_requirements??null} onChange={value=>{setAccessibility(value);changed();}} hint="Select any that apply. The system filters campsites using these requirements. Save other requirements now and submit them for assistance from the camping request later."/></section>
      <section className="panel"><div className="section-title"><span className="eyebrow">Trip transport</span><h2>Transport arrangements</h2></div><TransportModeField value={transport} supported={supportedModes} onChange={changeTransport} error={transportContextError} guidance={guidance.transport} systemPreparation={systemPreparation}/><div className="form-grid">
        {!systemPreparation&&<div><label htmlFor="estimated-km">Estimated total distance km</label><input id="estimated-km" inputMode="decimal" pattern="[0-9]+([.][0-9]+)?" value={km} aria-invalid={!!(issues['estimated-km']||guidance['estimated-km'])} aria-describedby="km-hint" onChange={event=>{setKm(event.target.value);changed();}}/><FieldHint id="km-hint" error={issues['estimated-km']??guidance['estimated-km']}>Enter the total distance, or leave blank if unknown.</FieldHint></div>}
      </div>{(transport==='CAR'||!systemPreparation&&equipment.some(item=>item.item_key==='vehicle'))&&<VehicleFields equipment={equipment} issues={issues} guidance={guidance} onChange={updateEquipment} onRemove={removeEquipment} onAdd={()=>replaceEquipment([...equipment,{item_key:'vehicle',label:'Vehicles',quantity:'',unit:'vehicle',capacity:'',confirmed:false}])}/>}{!systemPreparation&&<><label htmlFor="transport-assumptions">{transport==='PUBLIC_TRANSPORT'?'Verified return travel and final connections (one per line)':'Distance and transport notes (one per line)'}</label><textarea id="transport-assumptions" value={assumptions} aria-invalid={!!guidance['transport-assumptions']} aria-describedby="transport-assumptions-hint" placeholder={transport==='PUBLIC_TRANSPORT'?'Outbound: origin and transfers. Return: departure arrangements. Final connection: travel from the stop or wharf to the campsite. Mark unknown details as pending confirmation.':'For example: combined return distance, using our own vehicles'} onChange={event=>{setAssumptions(event.target.value);changed();}}/><FieldHint id="transport-assumptions-hint" error={guidance['transport-assumptions']}>{transport==='PUBLIC_TRANSPORT'?'Also register one connection plan below. Confirm only after verifying arrangements. Unknown information can be saved; formal checks retain the gaps.':undefined}</FieldHint></>}</section></div>
      <CookingPreparationPanel value={cooking} preview={cookingPreview?.value} stale={cookingPreview?cookingPreview.signature!==cookingSignature:cookingEdited}
        unsaved={cookingEdited} attention={relatedIssues.some(item=>['camping_stove','fuel_canister'].includes(item.item_key??'')||item.code==='COOKING_ARRANGEMENT')}
        onCheck={checkCooking} busy={cookingBusy} error={cookingError} onFocus={key=>{const index=equipment.findIndex(item=>item.item_key===key);const node=document.getElementById(`gear-quantity-${index}`);node?.focus();node?.scrollIntoView({block:'center'});}}/>
      <section className="panel equipment-panel"><div className="panel-title"><div><span className="eyebrow">Equipment preparation</span><h2>Available equipment <small>{equipment.filter(editableEquipment).length} items</small></h2></div><button id="add-equipment" type="button" className="secondary-button" onClick={appendEquipment}>Add equipment</button></div><p className="field-hint">Category is used for checks; names distinguish items of the same type, such as Three-person tent or Solo tent. Use separate rows for different capacities. Quantity is the item count for that name. Record tents as items, water in litres and meals as portions. Only Other equipment allows unit selection. Saving quantities confirms availability for this trip.</p>
        {!equipment.some(editableEquipment)&&<div className="equipment-empty"><span aria-hidden="true">＋</span><p>No equipment registered yet</p><small>Add available items. Leave uncertain quantities blank.</small></div>}
        {equipment.map((item,index)=>!editableEquipment(item)?null:<article className={Object.keys(guidance).some(id=>id.startsWith('gear-')&&id.endsWith('-'+index))?'equipment-card equipment-card-needed':'equipment-card'} key={index}><header><span className="equipment-number">{String(equipment.slice(0,index).filter(editableEquipment).length+1).padStart(2,'0')}</span><h3>{displayEquipmentName(item.item_key,item.label)||'Unnamed equipment'}</h3><button type="button" className="text-button" aria-label={`Remove equipment ${index+1}`} onClick={()=>removeEquipment(index)}>Remove</button></header><div className="equipment-fields">
          <div><label htmlFor={`gear-type-${index}`}>Category</label><select id={`gear-type-${index}`} aria-label={`Equipment ${index+1} Category`} value={item.item_key} onChange={event=>replaceEquipment(changeEquipmentCategory(equipment,index,event.target.value,datasetVersion))}>{equipmentTypes.filter(([key])=>key!=='vehicle').map(([key,label])=><option key={key} value={key}>{label}</option>)}{!EQUIPMENT_TYPES.some(([key])=>key===item.item_key)&&<option value={item.item_key}>{displayEquipmentName(item.item_key,item.label)}</option>}</select></div>
          <div><label htmlFor={`gear-name-${index}`}>Name</label><input id={`gear-name-${index}`} aria-label={`Equipment ${index+1} Name`} required value={displayEquipmentName(item.item_key,item.label)} aria-invalid={!!(issues[`gear-name-${index}`]||guidance[`gear-name-${index}`])} aria-describedby={`gear-name-hint-${index}`} onChange={event=>updateEquipment(index,{label:event.target.value})}/><FieldHint id={`gear-name-hint-${index}`} error={issues[`gear-name-${index}`]??guidance[`gear-name-${index}`]}/></div>
          <div><label htmlFor={`gear-quantity-${index}`}>Quantity</label><input id={`gear-quantity-${index}`} aria-label={`Equipment ${index+1} Quantity`} type="number" min="0" step="1" value={item.quantity} aria-invalid={!!(issues[`gear-quantity-${index}`]||guidance[`gear-quantity-${index}`])} aria-describedby={`gear-quantity-hint-${index}`} placeholder="Unknown" onChange={event=>updateEquipment(index,{quantity:event.target.value})}/><FieldHint id={`gear-quantity-hint-${index}`} error={issues[`gear-quantity-${index}`]??guidance[`gear-quantity-${index}`]}>{item.item_key==='vehicle'?'Enter available vehicles, excluding unsecured loans.':undefined}</FieldHint></div>
          <EquipmentUnitField item={item} index={index} datasetVersion={datasetVersion} error={issues[`gear-unit-${index}`]??guidance[`gear-unit-${index}`]} onChange={unit=>updateEquipment(index,{unit})}/>
          <div><label htmlFor={`gear-capacity-${index}`}>{item.item_key==='vehicle'?'Seats per vehicle (including driver)':item.item_key==='tent'?'People per tent':'People accommodated per item'}</label><input id={`gear-capacity-${index}`} aria-label={`Equipment ${index+1} People accommodated per item`} type="number" min="1" step="1" value={item.capacity} aria-invalid={!!(issues[`gear-capacity-${index}`]||guidance[`gear-capacity-${index}`])} aria-describedby={`gear-capacity-hint-${index}`} placeholder="Unknown / Not applicable" onChange={event=>updateEquipment(index,{capacity:event.target.value})}/><FieldHint id={`gear-capacity-hint-${index}`} error={issues[`gear-capacity-${index}`]??guidance[`gear-capacity-${index}`]}>{item.item_key==='vehicle'?'Includes the driver; for example, 5 seat vehicle: enter 5. Use separate rows for different vehicle capacities.':undefined}</FieldHint></div>
        </div>{PLAN_RECORD_KEYS.has(item.item_key)&&<><label className="checkbox-label equipment-confirmation"><input id={`gear-confirmed-${index}`} type="checkbox" aria-invalid={!!guidance[`gear-confirmed-${index}`]} aria-describedby={`gear-confirmed-hint-${index}`} checked={item.confirmed} aria-label={`Plan ${index+1} Arrangements verified`} onChange={event=>updateEquipment(index,{confirmed:event.target.checked})}/>Trip arrangements verified</label><FieldHint id={`gear-confirmed-hint-${index}`} error={guidance[`gear-confirmed-${index}`]}/></>}</article>)}
        <button id="add-equipment-bottom" type="button" className="equipment-add-bottom" aria-label="Add equipment" title="Add equipment" onClick={appendEquipment}><span aria-hidden="true">＋</span></button>
      </section>
      <div className="profile-save-bar"><div><strong>{dirty?(returnRequest?'After saving, review this update':'After saving, continue to requirements'):'Next step'}</strong><p id="profile-save-hint" role="status">{saveHint}</p>{problemIds.length>0&&dirty&&<button type="button" className="text-link focus-field" onClick={()=>document.getElementById(problemIds[0])?.focus()}>Go to fields needing attention ↗</button>}</div><div className="form-actions">{returnRequest&&<button type="submit" name="save-and-return" className="primary-button" disabled={!canSave||problemIds.length>0} aria-describedby="profile-save-hint">{busy?'Saving…':'Save and review this update'} <span>↗</span></button>}<button className={returnRequest?"secondary-button":"primary-button"} disabled={!canSave||problemIds.length>0} aria-describedby="profile-save-hint">{busy?'Saving…':returnRequest?'Save profile without checking':'Save camping profile'} <span>✓</span></button><DiscardChanges sections={unsavedSections} busy={busy} onDiscard={()=>{discardReload.current=true;preparedContext.current='';setRefresh(value=>value+1);}}/>{!canSave&&revision>0&&<Link className="text-link" to={returnRequest??"/request"}>{returnRequest?returnLabel:"Enter camping request ↗"}</Link>}</div></div>
    </fieldset></form>}
  </div>;
}

export function ProfileCorrectionStatus({ready,loading,failed,targets,dirty,returnPlan}:{
  ready:boolean;loading:boolean;failed:boolean;targets:string[];dirty:boolean;returnPlan:boolean;
}){
  const [navigationFailed,setNavigationFailed]=useState(false);
  return <><p>{loading?'Loading fields needing attention…':failed?'Some tasks could not be loaded. Please retry.':targets.length
    ?`Below ${targets.length} fields need completion or review and are highlighted below. Enter actual arrangements.`
    :dirty?'No missing-field notices remain on this form. Save changes, then review the arrangements.'
    :'No missing-field notices remain on this form. Profile saved; this does not resolve the original plan issues. Review changes and explicitly start new checks.'}</p>
    {ready&&targets.length>0&&<button type="button" className="secondary-button" onClick={()=>setNavigationFailed(!focusProfileTargets(targets))}>Go to first field requiring attention ↓</button>}
    {navigationFailed&&targets.length>0&&<p role="status">The missing field cannot be located. Reload the profile and retry.</p>}
    {ready&&targets.length===0&&returnPlan&&<p className="muted">The original plan retains its confirmed profile and check results. Review and check again to adopt new information.</p>}
  </>;
}

export function ProfileSummary({ profile, systemPreparation=false }: { profile: Profile | null;systemPreparation?:boolean }) {
  if (!profile) return <p>No profile snapshot yet. Complete your camping profile first.</p>;
  const gear=profile.equipment.filter(item=>!['vehicle','charged_phone'].includes(item.item_key)&&(!systemPreparation||!PLAN_RECORD_KEYS.has(item.item_key)));
  const historicalPlans=profile.equipment.filter(item=>PLAN_RECORD_KEYS.has(item.item_key));
  const fleet=profile.equipment.filter(item=>item.item_key==='vehicle');
  return <><dl className="summary-list"><div><dt>Group size</dt><dd>{profile.group_size ?? 'Unknown'}</dd></div><div><dt>Camping experience</dt><dd>{Object.fromEntries(LEVELS)[canonical(profile.experience_level, LEVELS)] ?? profile.experience_level ?? 'Unknown'}</dd></div><div><dt>Children in the group</dt><dd>{profile.has_children === false ? 'No children' : profile.has_children === true ? `Children travelling; count: ${profile.children_count ?? 'Unknown'}` : `Not yet specified${profile.children_count === null ? '' : `, Recorded group size ${profile.children_count}`}`}</dd></div><div><dt>Transport mode</dt><dd>{Object.fromEntries(MODES)[canonical(profile.transport.transport_type, MODES)] ?? profile.transport.transport_type ?? 'Unknown'}</dd></div>{(!systemPreparation||profile.transport.transport_type==='CAR')&&<div><dt>{systemPreparation?'Number of vehicles':'Vehicles / Total distance'}</dt><dd>{profile.transport.vehicle_count ?? 'Unknown'} vehicles{!systemPreparation&&<> / {profile.transport.estimated_km ?? 'Unknown'} km</>}</dd></div>}</dl>{fleet.length>0&&(!systemPreparation||profile.transport.transport_type==='CAR')&&<><h3>Vehicle arrangements</h3><ul>{fleet.map((item,index)=><li key={index}>{item.quantity??'Unknown'}  vehicles, each seating  {item.capacity_persons??'Unknown'}  people (including driver), {item.confirmed?'Confirmed available':'Unconfirmed'}</li>)}</ul></>}<h3>Registered equipment</h3>{gear.length === 0 ? <p className="muted">Not registered; equipment has not been assessed.</p> : <ul className="equipment-summary">{gear.map((item,index) => <li key={index}>{displayEquipmentName(item.item_key,item.label)||equipmentLabel(item.item_key)}: {item.quantity ?? 'Unknown'} {item.item_key==='tent'?'tents':unitLabel(item.unit)}, {item.item_key==='tent'?'Capacity per tent':'People accommodated per item'} {item.capacity_persons ?? 'Unknown'}{item.item_key==='tent'&&item.unit==='item'&&item.quantity!==null&&item.capacity_persons!==null?`, Total sleeping capacity in this row ${item.quantity*item.capacity_persons} people`:''}, {item.confirmed ? 'Ownership verified' : 'Unverified'}</li>)}</ul>}{profile.accessibility_requirements.length > 0 && <><h3>Group requirements</h3><ul>{profile.accessibility_requirements.map((item,index) => <li key={index}>{termLabel(item,'accessibility')}</li>)}</ul></>}{!systemPreparation&&profile.transport.assumptions.length > 0 && <><h3>Transport estimate assumptions</h3><ul>{profile.transport.assumptions.map((item,index) => <li key={index}>{item}</li>)}</ul></>}{systemPreparation&&historicalPlans.length>0&&<details><summary>Legacy plan registrations (historical reference only)</summary><ul>{historicalPlans.map((item,index)=><li key={index}>{displayEquipmentName(item.item_key,item.label)}: {item.quantity??'Unknown'} {unitLabel(item.unit)}, {item.confirmed?'Previously confirmed':'Previously unconfirmed'}</li>)}</ul><p>These records are not used as equipment or access evidence for this run.</p></details>}</>;
}
