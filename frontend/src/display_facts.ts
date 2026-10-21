// Read-only presentation of saved facts; never used to calculate eligibility.
export type TentCapacity = {records:{quantity:number|null;capacity_per_tent:number|null;total_capacity:number|null;confirmed:boolean;unit:string}[];
  group_size:number|null;registered_tent_count:number|null;registered_capacity:number|null;
  assessed_capacity:string|null;required_person_spaces:string|null;missing_person_spaces:string|null};

export function tentSummary(value:TentCapacity):string {
  const count=value.registered_tent_count??'未知数量的';
  const per=value.records.length===1?`，每顶可住 ${value.records[0].capacity_per_tent??'未知'} 人`:'';
  const gap=value.missing_person_spaces;
  return `${value.group_size??'未知人数'} 人同行，目前登记 ${count} 顶帐篷${per}，登记总住宿容量 ${value.registered_capacity??'未知'} 人。`
    +(gap===null?'可用于本次检查的住宿容量尚未确定，请核对数量、每顶真实容量及确认状态。'
      :Number(gap)>0?`本次检查缺少 ${gap} 人住宿容量，请核对每顶真实容量或补充住宿安排。`:'本次保存的检查未记录住宿容量缺口；仍须核实实际安排。');
}

export function changedSections(saved:Record<string,unknown>|null,current:Record<string,unknown>,names:Record<string,string>):string[]{
  if(!saved)return [];
  return [...new Set(Object.keys(names).filter(key=>JSON.stringify(saved[key])!==JSON.stringify(current[key])).map(key=>names[key]))];
}

export function discardMessage(sections:string[]):string {
  return `将放弃尚未保存的：${sections.join('、')}。仅重新读取最后保存的表单内容，不会恢复历史方案，也不会重新检查方案。`;
}

// Preserve arbitrary model prose in a folded original record rather than invent
// a translation or infer safety facts from an English sentence.
export function chineseProse(text:string|undefined):string|null {
  const known:Record<string,string>={
    'Registered synthetic region, capacity and known hard constraints match.':'演示资料中的地区、人数容量和已知必须条件与本次需求相符。',
    'Synthetic quiet-environment attribute matches; it is not a real-world guarantee.':'演示资料标注为安静环境，符合安静偏好，但不保证现场实际安静。',
    'Source lists a quiet-hours policy, not a quietness guarantee.':'来源规定了安静时段，但不保证现场实际安静。',
    'Actual quietness is not supplied.':'资料没有提供现场实际安静程度。',
    'Campsite fee is unknown.':'营地费用未知，需要核实。',
    'Transport type is not confirmed.':'交通方式尚未确认。',
    'Recommendation is not booking availability or safety clearance.':'推荐不代表营位可订，也不代表安全放行。',
  };
  if(!text)return null;
  return known[text]??(/[\u3400-\u9fff]/u.test(text)?text:null);
}

export const PROFILE_SAVED_NOTICE='露营资料已保存。当前方案仍采用原先确认的资料快照，尚未采用新资料完成检查。请使用“使用最新资料重新规划”，核对并确认新安排后，再等待新方案检查结果；原方案会保留。';
