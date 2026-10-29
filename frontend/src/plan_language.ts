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
  if(item.status==='AVAILABLE')return {title:'资料覆盖本次日期',detail:'资料覆盖本次日期；是否存在关闭、禁火或其他限制，仍须查看具体检查结果。'};
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

// Show saved conditions, never treat available evidence as permission or safety clearance.
export function safetyCondition(kind:string,status:string,evidence:CheckEvidence[],dates?:Dates|null,codes:string[]=[]){
  const matching=evidence.filter(item=>item.kind===kind);
  const pending=(title='待确认')=>({title,detail:'出发前请重新检查这项信息。',attention:true});
  if(kind==='ROAD'&&codes.includes('ROAD_CLOSED'))return {title:'道路关闭',detail:'请更换可通行的营地或调整路线。',attention:true};
  if(kind==='RESTRICTION'&&codes.includes('CAMPSITE_CLOSED'))return {title:'营地关闭',detail:'请选择其他营地。',attention:true};
  if(kind==='FIRE'&&codes.includes('FIRE_PROHIBITED'))return {title:'营火安排不符合规定',detail:'请取消营火或调整营地。',attention:true};
  if(status==='CONFLICTING'||matching.some(item=>item.status==='CONFLICTING'))return pending('信息有冲突，待核实');
  if(status==='STALE'||matching.some(item=>item.status==='STALE'))return pending('需要更新');
  if(status!=='AVAILABLE'||!matching.length||matching.some(item=>evidenceState(item,dates).title==='日期不适用'||item.status!=='AVAILABLE'))return pending();
  if(kind==='ROAD'){
    if(matching.some(item=>item.road_state==='CLOSED'))return {title:'道路关闭',detail:'请更换可通行的营地或调整路线。',attention:true};
    return matching.every(item=>item.road_state==='OPEN')?{title:'道路可通行',detail:'出发前留意临时封路通知。',attention:false}:pending();
  }
  if(kind==='WEATHER'){
    const descriptions=matching.map(item=>{
      const text=safetySummary(item.summary);
      return text?.startsWith('天气预估：')?text:null;
    });
    return descriptions.every(Boolean)?{title:[...new Set(descriptions)].map(text=>text!.replace(/^天气预估：|。$/g,'')).join('、'),detail:'临近出发时再次查看天气。',attention:false}:pending('天气待确认');
  }
  if(kind==='FIRE'){
    if(matching.some(item=>item.summary==='Synthetic comprehensive no-fire restriction.'))return {title:'禁止使用明火',detail:'请使用符合营地规定的用餐安排。',attention:true};
    if(matching.every(item=>['No synthetic fire restriction.','No additional fire restriction recorded.'].includes(item.summary??'')))return {title:'未注明额外限制',detail:'仍需遵守营地用火规定。',attention:false};
    return pending('用火规定待确认');
  }
  if(kind==='RESTRICTION'){
    if(matching.every(item=>item.summary==='No synthetic campsite restrictions reported.'))return {title:'未注明额外规定',detail:'出发前核对营地最新公告。',attention:false};
    return matching.every(item=>!!item.summary)?{title:'请留意营地规定',detail:'查看下方规定，提前准备饮水、交通及用火安排。',attention:true}:pending();
  }
  return pending();
}

export function planRowState(row:{run_status:string|null;stage:string|null;version_status:string|null;search_outcome?:string|null;display_status?:string|null}){
  if(row.run_status==='PENDING')return '等待开始规划';
  if(row.run_status==='RUNNING')return '正在准备方案';
  if(row.run_status==='FAILED')return '规划未完成';
  if(row.run_status==='CANCELLED')return '已取消规划';
  if(row.search_outcome==='NO_MATCH')return '未找到满足条件的营地';
  const display:Record<string,string>={NEEDS_USER_INPUT:'需要用户补充',NEEDS_EVIDENCE:'需要补齐检查资料',NEEDS_REVISION:'需要修改方案',AWAITING_REVIEW:'等待人工审核',CANNOT_RELEASE:'需要调整方案'};
  if(row.display_status&&display[row.display_status])return display[row.display_status];
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

export function safetyRegulations(text:string|null){
  if(!text)return null;
  if(text==='No synthetic campsite restrictions reported.')return '未注明额外营地规定。';
  // Translate known source clauses exactly; preserve unfamiliar real restrictions.
  // Legacy fixture prose belongs in the review record, not the trip instructions.
  if(/synthetic|demo/i.test(text))return null;
  const clauses:Record<string,string>={
    'Advance booking required':'需提前预订','same-day bookings not accepted':'不接受当天预订',
    'Amplified music prohibited':'禁止使用扩音设备播放音乐',
    'Arrival by ferry, boat or on foot':'乘渡轮、船只或步行抵达','no vehicle access to the campground':'车辆无法进入营地',
    'Arrive by ferry or other water transport and carry equipment from the wharf':'乘渡轮或其他水上交通抵达，从码头自行搬运装备',
    'BYO tent on a 4m by 4m unpowered site':'自备帐篷，营位为 4 × 4 米，无电力供应','standard occupancy is 4 guests':'标准入住人数为 4 人',
    'Bring a cooking stove':'自备炉具','Bring all drinking and cooking water':'自备全部饮用水和烹饪用水','Bring all drinking water':'自备全部饮用水',
    'Bring drinking and cooking water':'自备饮用水和烹饪用水','available water needs treatment':'现场水源需处理后使用',
    'Campfires and solid fuel burners prohibited':'禁止营火及固体燃料炉具','gas/electric barbecues provided':'提供燃气或电烧烤设施',
    'Campfires prohibited':'禁止营火','cooking is permitted in provided wood barbecues and fire rings, subject to current restrictions':'可在提供的木柴烧烤设施和火圈内烹饪，须遵守当时用火限制',
    'Carry all equipment and drinking water down a steep 1.2 km gravel trail':'需沿陡峭的 1.2 公里碎石步道搬运全部装备和饮用水',
    'Carry all equipment and water along a 750 metre gravel trail from Grahame Drive':'从 Grahame Drive 沿 750 米碎石步道搬运全部装备和水',
    'Enter via Plassey Road, not Riverside Drive':'从 Plassey Road 进入，请勿走 Riverside Drive',
    'Enter via Wolstenholme Avenue, not Bents Basin Road':'从 Wolstenholme Avenue 进入，请勿走 Bents Basin Road',
    'Fires only in designated or portable off-the-ground barbecues, subject to current restrictions':'仅可在指定或离地式便携烧烤设施中用火，须遵守当时用火限制',
    'Fires only in designated wood barbecues or bookable fire pits, subject to current restrictions':'仅可在指定木柴烧烤设施或已预订火坑中用火，须遵守当时用火限制',
    'From West Head Road parking, carry equipment down a steep 2.8 km track':'从 West Head Road 停车处沿陡峭的 2.8 公里步道搬运装备',
    'Keep noise down after 10pm':'晚上 10 点后保持安静','Noise restrictions after 10pm':'晚上 10 点后限制噪音','heat beads prohibited':'禁止使用烧烤燃料块',
    'Maximum 6 people per campsite':'每个营位最多 6 人','No overnight stays in vehicles':'不得在车内过夜','no overnight stays in vehicles':'不得在车内过夜',
    'Observe Glenbrook gate hours':'请留意 Glenbrook 大门开放时间','Observe gate hours':'请留意大门开放时间','retain the booking gate code':'保留预订时提供的大门密码',
    'One parking space per site':'每个营位提供一个停车位','One vehicle per site':'每个营位限一辆车',
    'Tent-only sites with a short walk from parking':'仅限帐篷，停车后需步行一小段距离','Tent-only sites':'仅限帐篷','walk 5 to 15 metres from campground parking':'从营地停车处步行 5 至 15 米',
    'Use designated fire rings or raised cooking equipment, subject to current restrictions':'使用指定火圈或离地式炉具，须遵守当时用火限制',
    'Wood campfires prohibited at campground and beach':'营地及海滩禁止木柴营火',
  };
  return text.split('; ').map(clause=>clauses[clause]??clause).join('；');
}
