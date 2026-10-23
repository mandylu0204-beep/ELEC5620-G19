export type LogisticsAudit = {audit_id:string;run_id:string;plan_version_id:string;assessment_id:string;attempt_id?:string;
  trace?:{requested_model:string;served_models:string[];turns:number;http_attempts:number;usage:Record<string,number>};
  plan:{gear_actions:{fact:{item_key:string;missing_quantity:string|null;unit:string;essential:boolean};method:string;
    procurement_quantity:string|null;procurement_unit:string;estimated_cost_cents:number|null;confirmation_required:boolean;reason_unverified:string}[];
    budget_allocations:{line_id:string;required_cents:number|null;allocated_cents:number|null;unfunded_cents:number|null}[];
    projected_cost_breakdown:{category:string;item_key:string}[];unallocated_known_budget_cents:number;
    budget_feasible:boolean|null;requires_user_confirmation:boolean;decision_summary_unverified:string}};

const methods:Record<string,string>={KEEP_CONFIRMED:'使用已确认装备',PROPOSE_RENTAL:'拟租借',PROPOSE_PURCHASE:'拟购买',
  PROPOSE_BORROW:'拟借用',ASK_USER:'需补充信息',DEFER_OPTIONAL:'暂缓可选装备'};
const categories:Record<string,string>={CAMPSITE:'营地',TRANSPORT:'交通',FOOD:'食物',WATER:'饮水',ADDITIONAL_GEAR:'装备'};

export function LogisticsPlanPanel({value,section,money,itemName,unitName}:{value:LogisticsAudit|null|undefined;section:'gear'|'cost';
  money:(value:number|null|undefined)=>string;itemName:(value:string)=>string;unitName:(value:string)=>string}) {
  if(!value)return null;
  const plan=value.plan;
  const costItemName=(value:string)=>value==='no_priced_equipment_gaps'?'无待报价装备':itemName(value);
  return <section className="panel logistics-plan-panel"><div className="section-title"><span className="eyebrow">出行准备</span><h2>{section==='gear'?'装备准备建议':'预算安排建议'}</h2></div>
    {section==='gear'?<><p className="muted">租借、购买和借用仍需你核实确认，建议不会增加已具备的装备。</p><div className="logistics-actions">{plan.gear_actions.map(item=><article key={item.fact.item_key} className={'logistics-action '+(item.confirmation_required?'logistics-action-pending':'')}>
      <div><h3>{itemName(item.fact.item_key)}</h3><span className="tag">{methods[item.method]??item.method}</span></div>
      {item.method==='KEEP_CONFIRMED'?<p>按已确认清单携带，无需额外补充。</p>:item.method==='DEFER_OPTIONAL'?<p>暂不采购，保留现有缺口。</p>:<p>建议补充：{item.procurement_quantity??'待确认'} {unitName(item.procurement_unit)} · 补缺费用 {money(item.estimated_cost_cents)}</p>}
      <small>{item.fact.missing_quantity===null?'现有缺口未知':`现有缺口 ${item.fact.missing_quantity} ${unitName(item.fact.unit)}`} · {item.fact.essential?'必要装备':'可选装备'}{item.confirmation_required?' · 待确认':''}</small>
      <details><summary>查看建议理由</summary><p>{item.reason_unverified}</p></details>
    </article>)}</div></>:<><p className="muted">按建议优先级分配已知费用。未知费用未被计为零，尚未分配的预算需要预留。</p>
      <div className="table-scroll"><table><caption>预算分配与缺口（AUD）</caption><thead><tr><th>优先级 / 项目</th><th>所需费用</th><th>计划分配</th><th>未覆盖</th></tr></thead><tbody>{plan.budget_allocations.map((line,index)=>{const cost=plan.projected_cost_breakdown[index];return <tr key={line.line_id}><td>{index+1}. {cost?categories[cost.category]??cost.category:'费用项目'}{cost?.category==='ADDITIONAL_GEAR'&&<small className="cost-site">{costItemName(cost.item_key)}</small>}</td><td>{money(line.required_cents)}</td><td>{money(line.allocated_cents)}</td><td>{money(line.unfunded_cents)}</td></tr>;})}</tbody></table></div>
      <p>尚未分配的已知预算：<strong>{money(plan.unallocated_known_budget_cents)}</strong></p><p className={plan.budget_feasible===true?'muted':'clarifications'}>{plan.budget_feasible===null?'仍有未知费用，暂不能判断预算是否足够。':plan.budget_feasible?'已知估算在预算内，供应安排仍需核实。':'当前预计费用超出预算，需要调整安排。'}</p></>}
    <details className="source-details"><summary>查看模型意见</summary><p>{plan.decision_summary_unverified}</p><small>模型意见供参考，数量与金额由程序核算。</small></details>
  </section>;
}

export function LogisticsTracePanel({value}:{value:LogisticsAudit|null|undefined}) {
  if(!value?.trace)return null;
  const trace=value.trace;
  return <section className="panel"><details className="planning-details"><summary>装备与预算模型诊断</summary><h2>本次物流模型评估记录</h2>
    {trace.served_models.includes('offline-test-only')&&<p className="mode-notice">离线接线测试：使用模拟模型响应。</p>}
    <p>本记录对应当前显示的物流评估，与原行程生成记录分别保存。</p><dl className="summary-list"><div><dt>请求模型</dt><dd>{trace.requested_model}</dd></div><div><dt>返回模型</dt><dd>{trace.served_models.join('、')||'未提供'}</dd></div><div><dt>工具轮数 / HTTP尝试</dt><dd>{trace.turns} / {trace.http_attempts}</dd></div><div><dt>Token usage</dt><dd>输入 {trace.usage.prompt_tokens??'未提供'} · 生成 {trace.usage.completion_tokens??'未提供'} · 合计 {trace.usage.total_tokens??'未提供'}</dd></div></dl>
    <p className="muted">usage是本次成功响应报告的用量，不是完整账单。</p><details><summary>查看关联记录</summary><p className="identifier">运行：{value.run_id} · 版本：{value.plan_version_id}</p><p className="identifier">评估：{value.assessment_id} · 保存尝试：{value.attempt_id}</p></details>
  </details></section>;
}
