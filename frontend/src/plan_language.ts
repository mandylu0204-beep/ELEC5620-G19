// Presentation only. Saved assessment outcomes and server action guards stay authoritative.
export type CheckEvidence={kind:string;summary:string|null;source_date:string|null;status:string;
  valid_from:string|null;valid_to:string|null;road_state:string|null;
  source_refs:{valid_from:string|null;valid_to:string|null}[]};
type Dates={start_date?:string|null;end_date?:string|null};
export const checkNames:Record<string,string>={WEATHER:'Weather outlook',FIRE:'Fire restrictions',ROAD:'Road access',RESTRICTION:'Campsite rules'};

// Exact saved descriptions only: display labels do not calculate official risk.
const WEATHER_DESCRIPTIONS:Record<string,{title:string;attention:boolean}>={
  'Mild synthetic conditions.':{title:'Mild weather',attention:false},
  'Estimated mild conditions.':{title:'Mild weather',attention:false},
  'Dry synthetic conditions.':{title:'Dry weather',attention:false},
  'Estimated dry conditions.':{title:'Dry weather',attention:false},
  'No adverse synthetic weather.':{title:'No severe weather recorded',attention:false},
  'No adverse weather estimated.':{title:'No severe weather recorded',attention:false},
  'Synthetic extreme heat expected.':{title:'Extreme heat forecast',attention:true},
  'Strong wind in synthetic forecast.':{title:'Strong winds forecast',attention:true},
  'Strong wind in this synthetic scenario.':{title:'Strong winds forecast',attention:true},
  'Heavy rain in synthetic forecast.':{title:'Heavy rain forecast',attention:true},
  'Heavy rain in synthetic conditions.':{title:'Heavy rain forecast',attention:true},
  'Cold synthetic forecast.':{title:'Cold weather forecast',attention:true},
};
const weatherDescription=(text:string|null)=>text&&Object.hasOwn(WEATHER_DESCRIPTIONS,text)?WEATHER_DESCRIPTIONS[text]:null;

export function evidenceState(item:CheckEvidence,dates?:Dates|null){
  if(item.status==='CONFLICTING')return {title:'Conflicting information',detail:'Existing information conflicts and cannot yet be confirmed.'};
  if(item.status==='STALE')return {title:'Information needs updating',detail:'Previous information has expired. Update it before checking again.'};
  const ranges=[{valid_from:item.valid_from,valid_to:item.valid_to},...item.source_refs.filter(ref=>ref.valid_from||ref.valid_to)];
  const uncovered=ranges.find(range=>dates?.start_date&&dates.end_date&&range.valid_from&&range.valid_to&&
    (range.valid_from>dates.start_date||range.valid_to<dates.end_date));
  if(uncovered)return {title:'Dates not covered',detail:`Information covers only ${uncovered.valid_from} to ${uncovered.valid_to}, and does not cover this trip: ${dates!.start_date} to ${dates!.end_date} .`};
  if(item.status==='MISSING')return {title:item.summary||item.source_refs.length?'Information needs verification':'No applicable information',
    detail:item.summary||item.source_refs.length?'Information exists, but its coverage, publication date or content does not support a decision for this trip.':'No applicable information is available for this trip. This check cannot be completed.'};
  if(item.road_state==='CLOSED')return {title:'Road closed',detail:'The source explicitly reports that the road to the campsite is closed. Choose an accessible campsite.'};
  if(item.status==='AVAILABLE')return {title:'Information covers these trip dates',detail:'Information covers the trip dates. Check individual results for closures, fire bans and other restrictions.'};
  return {title:'Information pending confirmation',detail:'This information cannot currently be confirmed.'};
}

export function checkState(kind:string,status:string,evidence:CheckEvidence[],dates?:Dates|null){
  const matching=evidence.filter(item=>item.kind===kind);
  const issue=matching.find(item=>item.status!=='AVAILABLE')??matching.find(item=>item.road_state==='CLOSED');
  if(issue)return evidenceState(issue,dates);
  if(status!=='AVAILABLE')return {title:status==='CONFLICTING'?'Conflicting information':status==='STALE'?'Information needs updating':matching.length?'Information needs verification':'No applicable information',
    detail:'Existing information does not support a decision for this trip.'};
  return matching.length?evidenceState(matching[0],dates):{title:'No applicable information',detail:'No verifiable information was provided.'};
}

// Show saved conditions, never treat available evidence as permission or safety clearance.
export function safetyCondition(kind:string,status:string,evidence:CheckEvidence[],dates?:Dates|null,codes:string[]=[]){
  const matching=evidence.filter(item=>item.kind===kind);
  const pending=(title='To be confirmed')=>({title,detail:'Check this information again before departure.',attention:true});
  if(kind==='ROAD'&&codes.includes('ROAD_CLOSED'))return {title:'Road closed',detail:'Choose an accessible campsite or adjust the route.',attention:true};
  if(kind==='RESTRICTION'&&codes.includes('CAMPSITE_CLOSED'))return {title:'Campsite closed',detail:'Choose another campsite.',attention:true};
  if(kind==='FIRE'&&codes.includes('FIRE_PROHIBITED'))return {title:'Campfire arrangements do not comply',detail:'Cancel the campfire or change campsite.',attention:true};
  if(status==='CONFLICTING'||matching.some(item=>item.status==='CONFLICTING'))return pending('Conflicting information; verification required');
  if(status==='STALE'||matching.some(item=>item.status==='STALE'))return pending('Update required');
  if(status!=='AVAILABLE'||!matching.length||matching.some(item=>evidenceState(item,dates).title==='Dates not covered'||item.status!=='AVAILABLE'))return pending();
  if(kind==='ROAD'){
    if(matching.some(item=>item.road_state==='CLOSED'))return {title:'Road closed',detail:'Choose an accessible campsite or adjust the route.',attention:true};
    return matching.every(item=>item.road_state==='OPEN')?{title:'Road open',detail:'Check for temporary road closures before departure.',attention:false}:pending();
  }
  if(kind==='WEATHER'){
    const descriptions=matching.map(item=>weatherDescription(item.summary));
    const known=descriptions.filter((item):item is {title:string;attention:boolean}=>item!==null);
    if(!known.length)return pending('Weather needs confirmation');
    const unknown=known.length!==descriptions.length;
    const attention=unknown||known.some(item=>item.attention);
    return {title:[...new Set(known.map(item=>item.title))].join(', ')+(unknown?'; Other weather details need confirmation':''),
      detail:attention?'Review the risks below and check the weather again before departure.':'Check the weather again close to departure.',attention};
  }
  if(kind==='FIRE'){
    if(matching.some(item=>item.summary==='Synthetic comprehensive no-fire restriction.'))return {title:'Open flames prohibited',detail:'Use meal arrangements that comply with campsite rules.',attention:true};
    if(matching.every(item=>['No synthetic fire restriction.','No additional fire restriction recorded.'].includes(item.summary??'')))return {title:'No additional restrictions recorded',detail:'Campsite fire rules still apply.',attention:false};
    return pending('Fire restrictions pending confirmation');
  }
  if(kind==='RESTRICTION'){
    if(matching.every(item=>item.summary==='No synthetic campsite restrictions reported.'))return {title:'No additional rules specified',detail:'Check the latest campsite notices before departure.',attention:false};
    return matching.every(item=>!!item.summary)?{title:'Observe campsite rules',detail:'Review the rules below and prepare water, transport and fire arrangements.',attention:true}:pending();
  }
  return pending();
}

export function planRowState(row:{run_status:string|null;stage:string|null;version_status:string|null;search_outcome?:string|null;display_status?:string|null}){
  if(row.run_status==='PENDING')return 'Checks incomplete';
  if(row.run_status==='RUNNING')return 'Checks incomplete';
  if(row.run_status==='FAILED')return 'Checks incomplete';
  if(row.run_status==='CANCELLED')return 'Checks cancelled';
  if(row.run_status==='SUPERSEDED')return 'Historical plan';
  if(row.search_outcome==='NO_MATCH')return 'Plan changes needed';
  const display:Record<string,string>={NEEDS_USER_INPUT:'Plan changes needed',NEEDS_EVIDENCE:'Plan changes needed',NEEDS_REVISION:'Plan changes needed',AWAITING_REVIEW:'Awaiting human review',CANNOT_RELEASE:'Plan changes needed'};
  if(row.display_status&&display[row.display_status])return display[row.display_status];
  return ({FINALISED:'Final plan saved',BLOCKED:'Plan changes needed',REVISION_REQUIRED:'Plan changes needed',
    ESCALATED:'Awaiting human review',ELIGIBLE_FOR_FINALISATION:'To be confirmed',ASSESSING:'Checks incomplete',
    REJECTED:'Plan changes needed',DRAFT:'Checks incomplete'} as Record<string,string>)[row.version_status??'']??'Checks incomplete';
}

export function blockerText(code:string){
  return ({ROAD_CLOSED:'The access road is closed. Choose a campsite with an open route.',ROAD_UNAVAILABLE:'Road access during the trip cannot be confirmed.',
    CAMPSITE_CLOSED:'Campsite closed. Choose another campsite.',FIRE_PROHIBITED:'Campfire arrangements conflict with campsite rules. Cancel the campfire or change campsite.',
    ESSENTIAL_GEAR_MISSING:'Essential equipment is missing. Review quantities and arrangements on the Equipment page.',TRANSPORT_UNAVAILABLE:'The transport mode or seating capacity cannot support this trip.',
    HARD_CONSTRAINT:'The campsite or itinerary does not meet your required conditions. Review and adjust the plan.',COSTS_INCOMPLETE:'Some essential costs are unknown. The total cannot yet be determined.',
    LOGISTICS_INCOMPLETE:'Equipment and transport checks are incomplete. If no specific gaps appear, contact the project maintainer.',BUDGET_MISMATCH:'Costs and budget information need review.',
    EVIDENCE_COVERAGE:'Some sources do not cover the entire trip. Review their date ranges on the Safety page.',
    EVIDENCE_UNAVAILABLE:'Some safety information is missing, expired or conflicting. The plan cannot yet be confirmed.',
    EVIDENCE_DEPENDENCY:'The links between equipment, cost and safety checks need updating.',STUB_RESULT:'This is a preview only. Formal planning is incomplete.',
    ASSESSMENTS_MISSING:'Equipment, cost or safety checks are incomplete.',ITINERARY_MISSING:'The itinerary is incomplete.',
    REVIEW_REQUIRED:'This plan requires reviewer action.',REVISION_REQUIRED:'Some parts of the plan need adjustment.'} as Record<string,string>)[code]??'Other conditions need review. Expand check details for the full explanation.';
}

export function safetySummary(text:string|null){
  if(!text)return null;
  const weather=weatherDescription(text);
  if(weather)return 'Weather outlook: '+weather.title+'.';
  return ({'No synthetic fire restriction.':'Available information lists no additional campfire restrictions.',
    'Synthetic comprehensive no-fire restriction.':'Existing information prohibits open flames.','Closed road access.':'Road access is closed.',
    'No additional fire restriction recorded.':'Available information lists no additional campfire restrictions.',
  } as Record<string,string>)[text]??null;
}

export function safetyRegulations(text:string|null){
  if(!text)return null;
  if(text==='No synthetic campsite restrictions reported.')return 'No additional campsite rules specified.';
  // Translate known source clauses exactly; preserve unfamiliar real restrictions.
  // Untranslated legacy prose is preserved in the safety panel's business-record fallback.
  if(/synthetic|demo/i.test(text))return null;
  return text;
}
