import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi, useSession } from './session';
import demoInputs from '../../docs/demo/v2_inputs.json';
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
  ['child_snacks','儿童零食','portion'],['offline_map','离线地图','item'],['charged_phone','已充电手机','item'],
  ['power_bank','充电宝','item'],['first_aid_kit','急救包','item'],['torch','头灯 / 手电','item'],
  ['whistle','哨子','item'],['emergency_contact_card','紧急联系卡','item'],['hand_sanitiser','洗手液','item'],
  ['toilet_kit','卫生用品','item'],['vehicle','车辆','vehicle'],['transport_itinerary','交通连接计划','plan'],
  ['fire_free_meal_plan','无火餐食计划','plan'],['water_container','储水容器','item'],['other','其他装备','item'],
];
const LEVELS = [['BEGINNER','初次 / 初学者'],['INTERMEDIATE','有一定经验'],['EXPERIENCED','经验丰富'],['ADVANCED','熟练 / 进阶']];
const MODES = [['CAR','汽车'],['PUBLIC_TRANSPORT','公共交通'],['WALKING','步行'],['OTHER','其他']];
export const equipmentLabel = (key: string) => EQUIPMENT_TYPES.find(([type])=>type===key)?.[1] ?? key;
const unitLabel = (unit: string) => ({item:'件',litre:'升',portion:'份',vehicle:'辆',plan:'份计划',set:'套'} as Record<string,string>)[unit] ?? unit;
const canonical = (value: string | null | undefined, choices: string[][]) => choices.find(([key]) => key.toLowerCase() === value?.trim().toLowerCase())?.[0] ?? value ?? '';


export function lines(value: string): string[] { return value.split('\n').map(line => line.trim()).filter(Boolean); }
export function integer(value: string): number | null {
  if (!value.trim()) return null;
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value))) throw new Error('人数、数量和容量请填写有效整数。');
  return Number(value);
}

export function ProfilePage({ demoAvailable = false, datasetVersion }: { demoAvailable?: boolean; datasetVersion?: string | null }) {
  const { session, reload } = useSession();
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [revision, setRevision] = useState(0);
  const [group, setGroup] = useState('');
  const [experience, setExperience] = useState('');
  const [children, setChildren] = useState('unknown');
  const [childrenCount, setChildrenCount] = useState('');
  const [equipment, setEquipment] = useState<EquipmentForm[]>([]);
  const [transport, setTransport] = useState('');
  const [vehicles, setVehicles] = useState('');
  const [km, setKm] = useState('');
  const [assumptions, setAssumptions] = useState('');
  const [accessibility, setAccessibility] = useState('');
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false); setError(''); setMessage('');
    privateApi<ProfileResponse>('/profile', { signal: controller.signal }).then(value => {
      if (controller.signal.aborted) return;
      setRevision(value.revision); const profile = value.profile;
      setGroup(String(profile?.group_size ?? '')); setExperience(canonical(profile?.experience_level, LEVELS));
      setChildren(profile?.has_children === true ? 'yes' : profile?.has_children === false ? 'no' : 'unknown');
      setChildrenCount(String(profile?.children_count ?? ''));
      setEquipment(profile?.equipment.map(item => ({ item_key: item.item_key, label: item.label, quantity: String(item.quantity ?? ''), unit: item.unit, capacity: String(item.capacity_persons ?? ''), confirmed: item.confirmed })) ?? []);
      setTransport(canonical(profile?.transport.transport_type, MODES)); setVehicles(String(profile?.transport.vehicle_count ?? ''));
      setKm(profile?.transport.estimated_km ?? ''); setAssumptions(profile?.transport.assumptions.join('\n') ?? '');
      setAccessibility(profile?.accessibility_requirements.map(item=>termLabel(item,'accessibility')).join('\n') ?? '');
      const aliases = !!profile && (canonical(profile.experience_level, LEVELS) !== (profile.experience_level ?? '') || canonical(profile.transport.transport_type, MODES) !== (profile.transport.transport_type ?? ''));
      setDirty(aliases); if (aliases) setMessage('已有资料使用旧取值，请核对并保存更新后再创建新需求。'); setLoaded(true);
    }).catch(reason => {
      if (!controller.signal.aborted) { setError(reason instanceof ApiFailure ? reason.message : '无法读取资料，请重试。'); if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload(); }
    });
    return () => controller.abort();
  }, [session?.user.user_id, refresh]);
  function loadDemo() {
    const profile = demoInputs.profile;
    setGroup(String(profile.group_size)); setExperience(canonical(profile.experience_level, LEVELS));
    setChildren(profile.has_children ? 'yes' : 'no'); setChildrenCount(String(profile.children_count));
    setEquipment(profile.equipment.map(item => ({ item_key: item.item_key, label: EQUIPMENT_TYPES.find(([key]) => key === item.item_key)?.[1] ?? item.label,
      quantity: String(item.quantity), unit: item.unit, capacity: 'capacity_persons' in item ? String(item.capacity_persons) : '', confirmed: item.confirmed })));
    setTransport(canonical(profile.transport.transport_type, MODES)); setVehicles(String(profile.transport.vehicle_count));
    setKm(profile.transport.estimated_km); setAssumptions(''); setAccessibility('');
    setDirty(true); setError(''); setMessage('已载入演示样例，尚未保存。请核对并保存。');
  }
  function changed() { setDirty(true); setMessage(''); setError(''); }
  function updateEquipment(index: number, patch: Partial<EquipmentForm>) { setEquipment(items => items.map((item, i) => i === index ? { ...item, ...patch } : item)); changed(); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!session || busy) return;
    if (problemIds.length) { setError(issues[problemIds[0]]); document.getElementById(problemIds[0])?.focus(); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const profile: Profile = { group_size: integer(group), experience_level: canonical(experience, LEVELS) || null, has_children: children === 'unknown' ? null : children === 'yes', children_count: integer(childrenCount),
        equipment: equipment.map(item => ({ item_key: item.item_key, label: item.label.trim(), quantity: integer(item.quantity), unit: item.unit.trim(), capacity_persons: integer(item.capacity), confirmed: item.confirmed })),
        transport: { transport_type: canonical(transport, MODES) || null, vehicle_count: integer(vehicles), estimated_km: km.trim() || null, assumptions: lines(assumptions) }, accessibility_requirements: canonicalTerms(lines(accessibility),'accessibility') };
      const saved = await privateApi<ProfileResponse>('/profile', { method:'PUT', headers:{ 'Content-Type':'application/json', 'X-CampMate-Client':'1', 'X-CSRF-Token':session.csrf_token }, body:JSON.stringify({ profile, expected_revision:revision }) });
      setRevision(saved.revision); setDirty(false); setMessage('露营资料已保存，可以继续填写需求。');
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
  if(km.trim()&&!/^\d+(\.\d+)?$/.test(km.trim()))issues['estimated-km']='路程请填写非负数字，单位为 km。';
  equipment.forEach((item,index)=>{
    if(!item.label.trim())issues[`gear-name-${index}`]='请填写装备名称。';
    if(!item.unit.trim())issues[`gear-unit-${index}`]='请选择计量单位。';
    checkNumber(`gear-quantity-${index}`,item.quantity,'数量',0);
    checkNumber(`gear-capacity-${index}`,item.capacity,'每件人数容量',1);
  });
  const problemIds=Object.keys(issues);
  const saveHint=busy?'正在保存资料…':!dirty?revision?'资料已保存，可以继续填写需求。':demoAvailable?'填写自己的资料，或展开下方演示样例。':'填写自己的资料，保存后继续。':problemIds.length?`${issues[problemIds[0]]}${problemIds.length>1?` 另有 ${problemIds.length-1} 项需要修改。`:''}`:'有未保存的修改，请保存后继续。';
  const units=[['item','件'],['litre','升'],['portion','份'],['vehicle','辆'],['plan','份计划'],['set','套']];
  return <div className="onboarding-page"><TripFlow step={1}/><div className="onboarding-heading"><div><span className="eyebrow">YOUR CAMPING PROFILE</span><h1>为同行的人做好准备。</h1><p>填写小组、交通与已有装备，让计划更贴合你们。</p></div>{loaded&&<span className="onboarding-status">{dirty?'有未保存修改':revision?'资料已保存':'开始填写'}</span>}</div>
    {error&&<p className="error-box" role="alert">{error}</p>}{message&&<p className="success-box" role="status">{message}</p>}
    {!loaded?<section className="panel"><p>正在读取资料…</p><button className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>重新读取</button></section>:<form className="profile-form" onSubmit={save}><fieldset disabled={busy}>
      <div className="profile-intro"><span>填写自己的露营资料</span><p>不确定的数量、容量和路程可以留空，后续评估会提示需要补充的信息。</p></div>
      {demoAvailable&&<details className="demo-profile-option"><summary>想先体验？使用演示样例</summary><div><p>样例包含两位同行者、交通安排与装备。载入后请核对并保存。</p><button type="button" className="secondary-button" onClick={loadDemo}>载入演示资料</button></div></details>}
      <div className="bottom-grid profile-main-grid"><section className="panel"><div className="section-title"><span className="eyebrow">WHO'S COMING</span><h2>小组信息</h2></div><div className="form-grid">
        <div><label htmlFor="group-size">小组人数（含儿童） <span className="required-mark">必填</span></label><input id="group-size" type="number" min="1" step="1" required value={group} aria-invalid={!!issues['group-size']} aria-describedby="group-hint" onChange={event=>{setGroup(event.target.value);changed();}}/><FieldHint id="group-hint" error={issues['group-size']}>包括所有同行者。</FieldHint></div>
        <div><label htmlFor="experience">露营经验</label><select id="experience" value={experience} onChange={event=>{setExperience(event.target.value);changed();}}><option value="">尚未明确</option>{LEVELS.map(([key,label])=><option key={key} value={key}>{label}</option>)}{experience&&!LEVELS.some(([key])=>key===experience)&&<option value={experience}>{experience}</option>}</select></div>
        <div><label htmlFor="has-children">是否有儿童</label><select id="has-children" value={children} onChange={event=>{setChildren(event.target.value);if(event.target.value==='no')setChildrenCount('0');changed();}}><option value="unknown">尚未明确</option><option value="yes">有儿童</option><option value="no">没有儿童</option></select></div>
        <div><label htmlFor="children-count">儿童人数</label><input id="children-count" type="number" min="0" step="1" value={childrenCount} disabled={children==='no'} aria-invalid={!!issues['children-count']} aria-describedby="children-hint" onChange={event=>{setChildrenCount(event.target.value);changed();}}/><FieldHint id="children-hint" error={issues['children-count']}>{children==='no'?'已记录为 0 人。':'计入小组总人数；未知可留空。'}</FieldHint></div>
      </div><label htmlFor="accessibility">无障碍及其他同行需求（每行一项）</label><textarea id="accessibility" value={accessibility} placeholder="例如：需要无台阶通道" onChange={event=>{setAccessibility(event.target.value);changed();}}/></section>
      <section className="panel"><div className="section-title"><span className="eyebrow">GETTING THERE</span><h2>交通安排</h2></div><label htmlFor="transport">交通方式</label><select id="transport" value={transport} onChange={event=>{setTransport(event.target.value);changed();}}><option value="">尚未明确</option>{MODES.map(([key,label])=><option key={key} value={key}>{label}</option>)}{transport&&!MODES.some(([key])=>key===transport)&&<option value={transport}>{transport}</option>}</select><div className="form-grid">
        <div><label htmlFor="vehicle-count">车辆数量（如适用）</label><input id="vehicle-count" type="number" min="1" step="1" value={vehicles} aria-invalid={!!issues['vehicle-count']} aria-describedby="vehicles-hint" onChange={event=>{setVehicles(event.target.value);changed();}}/><FieldHint id="vehicles-hint" error={issues['vehicle-count']}>没有明确安排时留空。</FieldHint></div>
        <div><label htmlFor="estimated-km">预计总路程 km</label><input id="estimated-km" inputMode="decimal" pattern="[0-9]+([.][0-9]+)?" value={km} aria-invalid={!!issues['estimated-km']} aria-describedby="km-hint" onChange={event=>{setKm(event.target.value);changed();}}/><FieldHint id="km-hint" error={issues['estimated-km']}>填写总路程，未知可留空。</FieldHint></div>
      </div><label htmlFor="transport-assumptions">路程与交通说明（每行一项）</label><textarea id="transport-assumptions" value={assumptions} placeholder="例如：往返合计，使用自己的车辆" onChange={event=>{setAssumptions(event.target.value);changed();}}/></section></div>
      <section className="panel equipment-panel"><div className="panel-title"><div><span className="eyebrow">PACK & PREPARE</span><h2>已有装备 <small>{equipment.length} 项</small></h2></div><button type="button" className="secondary-button" onClick={()=>{setEquipment(items=>[...items,{item_key:'tent',label:'帐篷',quantity:'',unit:'item',capacity:'',confirmed:false}]);changed();}}>添加装备</button></div><p className="field-hint">帐篷数量填件数，人数容量填每件可容纳的人数；水按升、餐食按份记录。勾选确认拥有的装备。</p>
        {equipment.length===0&&<div className="equipment-empty"><span aria-hidden="true">＋</span><p>还没有登记装备</p><small>添加已有物品；不确定的数量可以留空。</small></div>}
        {equipment.map((item,index)=><article className="equipment-card" key={index}><header><span className="equipment-number">{String(index+1).padStart(2,'0')}</span><h3>{item.label||'未命名装备'}</h3><button type="button" className="text-button" aria-label={`移除装备 ${index+1}`} onClick={()=>{setEquipment(items=>items.filter((_,i)=>i!==index));changed();}}>移除</button></header><div className="equipment-fields">
          <div><label htmlFor={`gear-type-${index}`}>类别</label><select id={`gear-type-${index}`} aria-label={`装备 ${index+1} 类别`} value={item.item_key} onChange={event=>updateEquipment(index,{item_key:event.target.value,label:equipmentLabel(event.target.value),unit:event.target.value==='warm_layers'&&datasetVersion==='v1'?'set':EQUIPMENT_TYPES.find(([key])=>key===event.target.value)?.[2]??item.unit})}>{EQUIPMENT_TYPES.map(([key,label])=><option key={key} value={key}>{label}</option>)}{!EQUIPMENT_TYPES.some(([key])=>key===item.item_key)&&<option value={item.item_key}>{item.label}</option>}</select></div>
          <div><label htmlFor={`gear-name-${index}`}>名称</label><input id={`gear-name-${index}`} aria-label={`装备 ${index+1} 名称`} required value={item.label} aria-invalid={!!issues[`gear-name-${index}`]} aria-describedby={`gear-name-hint-${index}`} onChange={event=>updateEquipment(index,{label:event.target.value})}/><FieldHint id={`gear-name-hint-${index}`} error={issues[`gear-name-${index}`]}/></div>
          <div><label htmlFor={`gear-quantity-${index}`}>数量</label><input id={`gear-quantity-${index}`} aria-label={`装备 ${index+1} 数量`} type="number" min="0" step="1" value={item.quantity} aria-invalid={!!issues[`gear-quantity-${index}`]} aria-describedby={`gear-quantity-hint-${index}`} placeholder="未知" onChange={event=>updateEquipment(index,{quantity:event.target.value})}/><FieldHint id={`gear-quantity-hint-${index}`} error={issues[`gear-quantity-${index}`]}/></div>
          <div><label htmlFor={`gear-unit-${index}`}>单位</label><select id={`gear-unit-${index}`} aria-label={`装备 ${index+1} 单位`} required value={item.unit} aria-invalid={!!issues[`gear-unit-${index}`]} aria-describedby={`gear-unit-hint-${index}`} onChange={event=>updateEquipment(index,{unit:event.target.value})}>{units.map(([key,title])=><option key={key} value={key}>{title}</option>)}{!units.some(([key])=>key===item.unit)&&<option value={item.unit}>{item.unit||'请选择单位'}</option>}</select><FieldHint id={`gear-unit-hint-${index}`} error={issues[`gear-unit-${index}`]}/></div>
          <div><label htmlFor={`gear-capacity-${index}`}>每件人数容量</label><input id={`gear-capacity-${index}`} aria-label={`装备 ${index+1} 每件人数容量`} type="number" min="1" step="1" value={item.capacity} aria-invalid={!!issues[`gear-capacity-${index}`]} aria-describedby={`gear-capacity-hint-${index}`} placeholder="未知 / 不适用" onChange={event=>updateEquipment(index,{capacity:event.target.value})}/><FieldHint id={`gear-capacity-hint-${index}`} error={issues[`gear-capacity-${index}`]}/></div>
        </div><label className="checkbox-label equipment-confirmation"><input type="checkbox" checked={item.confirmed} aria-label={`装备 ${index+1} 已核实拥有`} onChange={event=>updateEquipment(index,{confirmed:event.target.checked})}/>已核实拥有</label></article>)}
      </section>
      <div className="profile-save-bar"><div><strong>{dirty?'保存后，继续填写需求':'准备下一步'}</strong><p id="profile-save-hint" role="status">{saveHint}</p>{problemIds.length>0&&dirty&&<button type="button" className="text-link focus-field" onClick={()=>document.getElementById(problemIds[0])?.focus()}>前往需要修改的字段 ↗</button>}</div><div className="form-actions"><button className="primary-button" disabled={!dirty||problemIds.length>0} aria-describedby="profile-save-hint">{busy?'正在保存…':'保存露营资料'} <span>✓</span></button><button type="button" className="secondary-button" onClick={()=>setRefresh(value=>value+1)}>恢复已保存字段</button>{!dirty&&revision>0&&<Link className="text-link" to="/request">填写露营请求 ↗</Link>}</div></div>
    </fieldset></form>}
  </div>;
}

export function ProfileSummary({ profile }: { profile: Profile | null }) {
  if (!profile) return <p>尚无资料快照，请先填写露营资料。</p>;
  return <><dl className="summary-list"><div><dt>小组人数</dt><dd>{profile.group_size ?? '未知'}</dd></div><div><dt>露营经验</dt><dd>{Object.fromEntries(LEVELS)[canonical(profile.experience_level, LEVELS)] ?? profile.experience_level ?? '未知'}</dd></div><div><dt>儿童情况</dt><dd>{profile.has_children === false ? '没有儿童' : profile.has_children === true ? `有儿童，人数 ${profile.children_count ?? '未知'}` : `尚未明确${profile.children_count === null ? '' : `，登记人数 ${profile.children_count}`}`}</dd></div><div><dt>交通方式</dt><dd>{Object.fromEntries(MODES)[canonical(profile.transport.transport_type, MODES)] ?? profile.transport.transport_type ?? '未知'}</dd></div><div><dt>车辆 / 总路程</dt><dd>{profile.transport.vehicle_count ?? '未知'} 辆 / {profile.transport.estimated_km ?? '未知'} km</dd></div></dl><h3>登记装备</h3>{profile.equipment.length === 0 ? <p className="muted">未登记，尚未进行装备评估。</p> : <ul className="equipment-summary">{profile.equipment.map((item,index) => <li key={index}>{item.label}：{item.quantity ?? '未知'} {unitLabel(item.unit)}，每件人数容量 {item.capacity_persons ?? '未知'}，{item.confirmed ? '已核实拥有' : '未核实'}</li>)}</ul>}{profile.accessibility_requirements.length > 0 && <><h3>同行需求</h3><ul>{profile.accessibility_requirements.map((item,index) => <li key={index}>{termLabel(item,'accessibility')}</li>)}</ul></>}{profile.transport.assumptions.length > 0 && <><h3>交通估算说明</h3><ul>{profile.transport.assumptions.map((item,index) => <li key={index}>{item}</li>)}</ul></>}</>;
}
