import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiFailure } from './api';
import { privateApi, useSession } from './session';
import demoInputs from '../../docs/demo/v2_inputs.json';

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
      setAccessibility(profile?.accessibility_requirements.join('\n') ?? '');
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
    setDirty(true); setError(''); setMessage('已填入 synthetic 演示资料，尚未保存。请核对小组、交通和装备后保存。');
  }
  function changed() { setDirty(true); setMessage(''); setError(''); }
  function updateEquipment(index: number, patch: Partial<EquipmentForm>) { setEquipment(items => items.map((item, i) => i === index ? { ...item, ...patch } : item)); changed(); }
  async function save(event: FormEvent) {
    event.preventDefault(); if (!session) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const profile: Profile = { group_size: integer(group), experience_level: canonical(experience, LEVELS) || null, has_children: children === 'unknown' ? null : children === 'yes', children_count: integer(childrenCount),
        equipment: equipment.map(item => ({ item_key: item.item_key, label: item.label.trim(), quantity: integer(item.quantity), unit: item.unit.trim(), capacity_persons: integer(item.capacity), confirmed: item.confirmed })),
        transport: { transport_type: canonical(transport, MODES) || null, vehicle_count: integer(vehicles), estimated_km: km.trim() || null, assumptions: lines(assumptions) }, accessibility_requirements: lines(accessibility) };
      const saved = await privateApi<ProfileResponse>('/profile', { method:'PUT', headers:{ 'Content-Type':'application/json', 'X-CampMate-Client':'1', 'X-CSRF-Token':session.csrf_token }, body:JSON.stringify({ profile, expected_revision:revision }) });
      setRevision(saved.revision); setDirty(false); setMessage('资料已保存。已有的确认快照会保留原内容。');
    } catch (reason) {
      setError(reason instanceof ApiFailure ? [reason.message, ...reason.envelope.error.field_errors.map(item => item.message)].join(' ') : reason instanceof Error ? reason.message : '保存失败。');
      if (reason instanceof ApiFailure && reason.envelope.error.code === 'UNAUTHENTICATED') reload();
    } finally { setBusy(false); }
  }
  return <><div className="page-heading"><span className="eyebrow">YOUR CAMPING PROFILE</span><h1>为同行的人做好准备。</h1><p>保存小组、装备与交通信息。不确定的数量或容量可以留空。</p></div>{error && <p className="error-box" role="alert">{error}</p>}{message && <p className="success-box" role="status">{message}</p>}{!loaded ? <section className="panel"><p>正在读取资料…</p><button className="secondary-button" onClick={() => setRefresh(value => value + 1)}>重新读取</button></section> : <form className="profile-form" onSubmit={save}><fieldset disabled={busy}>{demoAvailable && <section className="panel"><h2>演示资料示例</h2><p>可使用示例资料快速填写。</p><button type="button" className="secondary-button" onClick={loadDemo}>载入演示资料</button></section>}<div className="bottom-grid"><section className="panel"><h2>小组信息</h2><div className="form-grid"><div><label htmlFor="group-size">小组人数（含儿童）</label><input id="group-size" type="number" min="1" step="1" required value={group} onChange={event => { setGroup(event.target.value); changed(); }} /></div><div><label htmlFor="experience">露营经验</label><select id="experience" value={experience} onChange={event => { setExperience(event.target.value); changed(); }}><option value="">尚未明确</option>{LEVELS.map(([key,label]) => <option key={key} value={key}>{label}</option>)}{experience && !LEVELS.some(([key]) => key === experience) && <option value={experience}>{experience}</option>}</select></div><div><label htmlFor="has-children">是否有儿童</label><select id="has-children" value={children} onChange={event => { setChildren(event.target.value); if (event.target.value === 'no') setChildrenCount('0'); changed(); }}><option value="unknown">尚未明确</option><option value="yes">有儿童</option><option value="no">没有儿童</option></select></div><div><label htmlFor="children-count">儿童人数</label><input id="children-count" type="number" min="0" step="1" value={childrenCount} disabled={children === 'no'} onChange={event => { setChildrenCount(event.target.value); changed(); }} /></div></div><label htmlFor="accessibility">无障碍及其他同行需求（每行一项）</label><textarea id="accessibility" value={accessibility} onChange={event => { setAccessibility(event.target.value); changed(); }} /></section><section className="panel"><h2>交通安排</h2><label htmlFor="transport">交通方式</label><select id="transport" value={transport} onChange={event => { setTransport(event.target.value); changed(); }}><option value="">尚未明确</option>{MODES.map(([key,label]) => <option key={key} value={key}>{label}</option>)}{transport && !MODES.some(([key]) => key === transport) && <option value={transport}>{transport}</option>}</select><div className="form-grid"><div><label htmlFor="vehicle-count">车辆数量（如适用）</label><input id="vehicle-count" type="number" min="1" step="1" value={vehicles} onChange={event => { setVehicles(event.target.value); changed(); }} /></div><div><label htmlFor="estimated-km">预计总路程 km（可留空）</label><input id="estimated-km" inputMode="decimal" pattern="[0-9]+([.][0-9]+)?" value={km} onChange={event => { setKm(event.target.value); changed(); }} /></div></div><label htmlFor="transport-assumptions">估算说明（每行一项）</label><textarea id="transport-assumptions" value={assumptions} onChange={event => { setAssumptions(event.target.value); changed(); }} /></section></div><section className="panel equipment-panel"><div className="panel-title"><h2>已有装备</h2><button type="button" className="secondary-button" onClick={() => { setEquipment(items => [...items, { item_key:'tent', label:'帐篷', quantity:'', unit:'item', capacity:'', confirmed:false }]); changed(); }}>添加装备</button></div><p className="muted">数量填写件数，人数容量填写每件装备的容量；未知时留空。这里记录拥有情况，是否满足行程需要将在后续评估。</p>{equipment.length === 0 && <p className="muted">尚未登记装备。请添加已有装备。</p>}{equipment.map((item,index) => <div className="equipment-row" key={index}><div><label htmlFor={`gear-type-${index}`}>装备 {index + 1} 类别</label><select id={`gear-type-${index}`} value={item.item_key} onChange={event => updateEquipment(index, { item_key:event.target.value, label:EQUIPMENT_TYPES.find(([key]) => key === event.target.value)?.[1] ?? item.label, unit:event.target.value === 'warm_layers' && datasetVersion === 'v1' ? 'set' : EQUIPMENT_TYPES.find(([key]) => key === event.target.value)?.[2] ?? item.unit })}>{EQUIPMENT_TYPES.map(([key,label]) => <option key={key} value={key}>{label}</option>)}{!EQUIPMENT_TYPES.some(([key]) => key === item.item_key) && <option value={item.item_key}>{item.label}</option>}</select></div><div><label htmlFor={`gear-name-${index}`}>装备 {index + 1} 名称</label><input id={`gear-name-${index}`} required value={item.label} onChange={event => updateEquipment(index,{label:event.target.value})} /></div><div><label htmlFor={`gear-quantity-${index}`}>装备 {index + 1} 数量</label><input id={`gear-quantity-${index}`} type="number" min="0" step="1" value={item.quantity} onChange={event => updateEquipment(index,{quantity:event.target.value})} /></div><div><label htmlFor={`gear-unit-${index}`}>装备 {index + 1} 单位</label><input id={`gear-unit-${index}`} required value={item.unit} onChange={event => updateEquipment(index,{unit:event.target.value})} /></div><div><label htmlFor={`gear-capacity-${index}`}>装备 {index + 1} 每件人数容量</label><input id={`gear-capacity-${index}`} type="number" min="1" step="1" value={item.capacity} onChange={event => updateEquipment(index,{capacity:event.target.value})} /></div><label className="checkbox-label"><input type="checkbox" checked={item.confirmed} onChange={event => updateEquipment(index,{confirmed:event.target.checked})} />已核实拥有</label><button type="button" className="text-button" aria-label={`移除装备 ${index + 1}`} onClick={() => { setEquipment(items => items.filter((_,i) => i !== index)); changed(); }}>移除</button></div>)}</section><div className="form-actions"><button className="primary-button" disabled={!dirty}>保存露营资料 <span>↗</span></button><button type="button" className="secondary-button" onClick={() => setRefresh(value => value + 1)}>恢复已保存字段</button>{!dirty && <Link className="text-link" to="/request">填写露营请求 ↗</Link>}</div></fieldset></form>}</>;
}

export function ProfileSummary({ profile }: { profile: Profile | null }) {
  if (!profile) return <p>尚无资料快照，请先填写露营资料。</p>;
  return <><dl className="summary-list"><div><dt>小组人数</dt><dd>{profile.group_size ?? '未知'}</dd></div><div><dt>露营经验</dt><dd>{Object.fromEntries(LEVELS)[canonical(profile.experience_level, LEVELS)] ?? profile.experience_level ?? '未知'}</dd></div><div><dt>儿童情况</dt><dd>{profile.has_children === false ? '没有儿童' : profile.has_children === true ? `有儿童，人数 ${profile.children_count ?? '未知'}` : `尚未明确${profile.children_count === null ? '' : `，登记人数 ${profile.children_count}`}`}</dd></div><div><dt>交通方式</dt><dd>{Object.fromEntries(MODES)[canonical(profile.transport.transport_type, MODES)] ?? profile.transport.transport_type ?? '未知'}</dd></div><div><dt>车辆 / 总路程</dt><dd>{profile.transport.vehicle_count ?? '未知'} 辆 / {profile.transport.estimated_km ?? '未知'} km</dd></div></dl><h3>登记装备</h3>{profile.equipment.length === 0 ? <p className="muted">未登记，尚未进行装备评估。</p> : <ul className="equipment-summary">{profile.equipment.map((item,index) => <li key={index}>{item.label}：{item.quantity ?? '未知'} {item.unit}，每件人数容量 {item.capacity_persons ?? '未知'}，{item.confirmed ? '已核实拥有' : '未核实'}</li>)}</ul>}{profile.accessibility_requirements.length > 0 && <><h3>同行需求</h3><ul>{profile.accessibility_requirements.map((item,index) => <li key={index}>{item}</li>)}</ul></>}{profile.transport.assumptions.length > 0 && <><h3>交通估算说明</h3><ul>{profile.transport.assumptions.map((item,index) => <li key={index}>{item}</li>)}</ul></>}</>;
}
