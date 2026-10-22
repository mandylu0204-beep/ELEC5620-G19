// Presentation only. Saved assessment outcomes and server action guards stay authoritative.
export type CheckEvidence={kind:string;summary:string|null;source_date:string|null;status:string;
  valid_from:string|null;valid_to:string|null;road_state:string|null;
  source_refs:{valid_from:string|null;valid_to:string|null}[]};
type Dates={start_date?:string|null;end_date?:string|null};
export const checkNames:Record<string,string>={WEATHER:'天气预估',FIRE:'营火规定',ROAD:'道路通行',RESTRICTION:'营地规定'};

export function evidenceState(item:CheckEvidence,dates?:Dates|null){
  if(item.status==='CONFLICTING')return {title:'资料有冲突',detail:'现有资料的说明不一致，暂时无法确认。'};
  if(item.status==='STALE')return {title:'资料需要更新',detail:'此前资料已过期，需要更新后再检查。'};
  const ranges=[{valid_from:item.valid_from,valid_to:item.valid_to},...item.source_refs.filter(ref=>ref.valid_from||ref.valid_to)];
  const uncovered=ranges.find(range=>dates?.start_date&&dates.end_date&&range.valid_from&&range.valid_to&&
    (range.valid_from>dates.start_date||range.valid_to<dates.end_date));
  if(uncovered)return {title:'日期不适用',detail:`资料仅适用于 ${uncovered.valid_from} 至 ${uncovered.valid_to}，无法覆盖此次 ${dates!.start_date} 至 ${dates!.end_date} 的行程。`};
  if(item.status==='MISSING')return {title:item.summary||item.source_refs.length?'资料待核实':'暂无适用资料',
    detail:item.summary||item.source_refs.length?'已有资料，但适用范围、发布时间或内容尚不能支持此次行程的判断。':'暂时没有适用于此次行程的资料，无法完成这项检查。'};
  if(item.road_state==='CLOSED')return {title:'道路关闭',detail:'资料明确显示通往营地的道路关闭，需要更换可通行的营地。'};
  if(item.status==='AVAILABLE')return {title:'资料适用',detail:'已提供适用于此次行程的资料。'};
  return {title:'信息待确认',detail:'目前无法确认这项信息。'};
}

export function checkState(kind:string,status:string,evidence:CheckEvidence[],dates?:Dates|null){
  const matching=evidence.filter(item=>item.kind===kind);
  const issue=matching.find(item=>item.status!=='AVAILABLE')??matching.find(item=>item.road_state==='CLOSED');
  if(issue)return evidenceState(issue,dates);
  if(status!=='AVAILABLE')return {title:status==='CONFLICTING'?'资料有冲突':status==='STALE'?'资料需要更新':matching.length?'资料待核实':'暂无适用资料',
    detail:'现有资料尚不能支持此次行程的判断。'};
  return matching.length?evidenceState(matching[0],dates):{title:'暂无适用资料',detail:'未提供可核对的资料。'};
}

export function planRowState(row:{run_status:string|null;stage:string|null;version_status:string|null;search_outcome?:string|null}){
  if(row.run_status==='PENDING')return '等待开始规划';
  if(row.run_status==='RUNNING')return '正在准备方案';
  if(row.run_status==='FAILED')return '规划未完成';
  if(row.run_status==='CANCELLED')return '已取消规划';
  if(row.search_outcome==='NO_MATCH')return '未找到满足条件的营地';
  return ({FINALISED:'最终方案已保存',BLOCKED:'方案有待完善',REVISION_REQUIRED:'需要调整方案',
    ESCALATED:'等待审核员处理',ELIGIBLE_FOR_FINALISATION:'方案已生成，待确认保存',ASSESSING:'正在检查方案',
    REJECTED:'审核未通过',DRAFT:'方案草稿'} as Record<string,string>)[row.version_status??'']??'本次尚未生成行程';
}

export function blockerText(code:string){
  return ({ROAD_CLOSED:'通往营地的道路关闭，需要更换可通行的营地。',ROAD_UNAVAILABLE:'无法确认行程期间道路是否可通行。',
    CAMPSITE_CLOSED:'营地关闭，需要选择其他营地。',FIRE_PROHIBITED:'营火安排与营地规定冲突，需要取消营火或调整营地。',
    ESSENTIAL_GEAR_MISSING:'必要装备仍有缺口，请在装备页核对数量和安排。',TRANSPORT_UNAVAILABLE:'目前的交通方式或载客容量无法支持此次行程。',
    HARD_CONSTRAINT:'营地或行程未满足你设定的必须条件，请核对并调整。',COSTS_INCOMPLETE:'部分必要费用未知，暂时无法判断总费用。',
    LOGISTICS_INCOMPLETE:'装备与交通检查尚未完成；若未显示具体缺项，请联系项目负责人核对原因。',BUDGET_MISMATCH:'费用与预算信息需要重新核对。',
    EVIDENCE_COVERAGE:'部分资料的适用日期无法覆盖整段行程，请在安全页核对范围。',
    EVIDENCE_UNAVAILABLE:'部分安全资料不足、已过期或有冲突，暂时无法确认方案。',
    EVIDENCE_DEPENDENCY:'装备、费用与安全检查的关联需要更新。',STUB_RESULT:'本次仅为预览，尚未完成正式规划。',
    ASSESSMENTS_MISSING:'装备、费用或安全检查尚未完成。',ITINERARY_MISSING:'行程内容尚不完整。',
    REVIEW_REQUIRED:'这份方案需要审核员处理。',REVISION_REQUIRED:'方案还有需要调整的内容。'} as Record<string,string>)[code]??'另有条件需要核对，请展开检查详情查看完整说明。';
}

export function safetySummary(text:string|null){
  if(!text)return null;
  return ({'Mild synthetic conditions.':'天气预估：天气温和。','Dry synthetic conditions.':'天气预估：天气干燥。',
    'No adverse synthetic weather.':'天气预估：未注明恶劣天气。','No synthetic fire restriction.':'现有资料未注明额外营火限制。',
    'Synthetic comprehensive no-fire restriction.':'现有资料规定禁止使用明火。','Closed road access.':'道路通行关闭。',
    'Estimated mild conditions.':'天气预估：天气温和。','Estimated dry conditions.':'天气预估：天气干燥。',
    'No additional fire restriction recorded.':'现有资料未注明额外营火限制。',
    'No adverse weather estimated.':'天气预估：未注明恶劣天气。'} as Record<string,string>)[text]??null;
}
