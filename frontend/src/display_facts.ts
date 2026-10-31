// Read-only presentation of saved facts; never used to calculate eligibility.
export type TentCapacity = {records:{quantity:number|null;capacity_per_tent:number|null;total_capacity:number|null;confirmed:boolean;unit:string}[];
  group_size:number|null;registered_tent_count:number|null;registered_capacity:number|null;
  assessed_capacity:string|null;required_person_spaces:string|null;missing_person_spaces:string|null};

export function tentSummary(value:TentCapacity):string {
  const group=value.group_size===null?'Group size unknown':`${value.group_size} people travelling`;
  const count=value.registered_tent_count===null?'tent count unknown':`${value.registered_tent_count} tents recorded`;
  const per=value.records.length===1?`, capacity per tent: ${value.records[0].capacity_per_tent??'unknown'}`:'';
  const gap=value.missing_person_spaces;
  return `${group}; ${count}${per}; recorded sleeping capacity: ${value.registered_capacity??'unknown'}. `
    +(gap===null?'Available capacity is unknown. Verify quantities, capacity per tent and availability.'
      :Number(gap)>0?`Shortage: ${gap} sleeping places. Verify tent capacities or arrange additional accommodation.`
      :'No sleeping-capacity gap was recorded in this check. Verify actual arrangements.');
}

export function changedSections(saved:Record<string,unknown>|null,current:Record<string,unknown>,names:Record<string,string>):string[]{
  if(!saved)return [];
  return [...new Set(Object.keys(names).filter(key=>JSON.stringify(saved[key])!==JSON.stringify(current[key])).map(key=>names[key]))];
}

export function discardMessage(sections:string[]):string {
  return `Unsaved changes to discard: ${sections.join(', ')}. This reloads the last saved form only. It does not restore a historical plan or rerun checks.`;
}

// Preserve arbitrary model prose in a folded original record rather than invent
// a translation or infer safety facts from an English sentence.
export function displayProse(text:string|undefined):string|null {
  const known:Record<string,string>={
    'Registered synthetic region, capacity and known hard constraints match.':'The registered region, group capacity and known required conditions match this request.',
    'Synthetic quiet-environment attribute matches; it is not a real-world guarantee.':'The source describes a quiet environment, matching the quiet preference; actual quietness is not guaranteed.',
    'Source lists a quiet-hours policy, not a quietness guarantee.':'The source specifies quiet hours; actual quietness is not guaranteed.',
    'Actual quietness is not supplied.':'No information about actual on-site quietness is provided.',
    'Campsite fee is unknown.':'Campsite fees are unknown and need verification.',
    'Transport type is not confirmed.':'Transport mode is unconfirmed.',
    'Recommendation is not booking availability or safety clearance.':'A recommendation does not confirm availability. Verify safety information before departure.',
  };
  if(!text)return null;
  return known[text]??(/[\u3400-\u9fff]/u.test(text)?null:text);
}

export const PROFILE_SAVED_NOTICE='Profile saved. The current plan still uses its original confirmed profile snapshot and has not been checked with the new information. Select Replan with latest profile, review and confirm the arrangements, then wait for the new check results. The original plan is retained.';
