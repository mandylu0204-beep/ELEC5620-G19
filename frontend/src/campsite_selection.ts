import {englishSavedReason} from './legacy_filter_reasons';
import { displayProse } from './display_facts';
import {canonicalTerms,termLabel} from './user_terms';

export const facilityNames:Record<string,string>={toilets:'Toilets',showers:'Showers',potable_water:'Drinking water'};
export type SelectionRow={label:string;detail:string;facility?:string;state?:boolean|null;required?:boolean;kind?:string;result?:string};
export function facilityDescription(key:string,state:boolean|null){
  return state===null?'Campsite information is unspecified and needs confirmation.':state?'Listed as provided in campsite information.':key==='potable_water'?'Listed as unavailable; bring your own drinking water.':'Listed as unavailable in campsite information.';
}
const facilityKey=(name:string)=>Object.keys(facilityNames).find(key=>facilityNames[key]===name);

// Layout of known saved reason text only. Never determines a match, risk or eligibility.
// Unrecognised prose stays intact; raw records are always rendered separately.
export function selectionPresentation(reasons:string[]){
  reasons=reasons.map(englishSavedReason);
  const rows:SelectionRow[]=[];const costs:string[]=[];
  for(const text of reasons){
    const visible=displayProse(text);if(!visible)continue;
    const cost=visible.match(/^Accommodation cost: (.+)$/u);
    if(cost){if(!costs.includes(cost[1]))costs.push(cost[1]);continue;}
    const required=visible.match(/^Required condition:\s*(.+?)[,;]\s*(?:registered information:|Recorded as)\s*(supported|not supported|unsupported|unknown)\.$/iu);
    const facility=visible.match(/^Campsite facilities:\s*(.+?);\s*(Listed as provided\.|Not provided; make alternative arrangements\.)$/u);
    let row:SelectionRow;
    if(required&&facilityKey(required[1]))row={label:required[1],detail:facilityDescription(facilityKey(required[1])!,required[2].toLowerCase()==='unknown'?null:required[2].toLowerCase()==='supported'),facility:facilityKey(required[1]),state:required[2].toLowerCase()==='unknown'?null:required[2].toLowerCase()==='supported',required:true};
    else if(facility&&facilityKey(facility[1]))row={label:facility[1],detail:facilityDescription(facilityKey(facility[1])!,facility[2]==='Listed as provided.'),facility:facilityKey(facility[1]),state:facility[2]==='Listed as provided.'};
    else{
      const labelled=visible.match(/^(Destination region|Group size|Transport|Required condition|Campsite facilities):\s*(.+)$/u);
      row=labelled?{label:labelled[1],detail:labelled[2]}:{label:'Other filtering evidence',detail:visible};
    }
    const duplicate=rows.findIndex(item=>row.facility?item.facility===row.facility&&item.state===row.state:item.label===row.label&&item.detail===row.detail);
    if(duplicate<0)rows.push(row);
    else if(row.required&&!rows[duplicate].required)rows[duplicate]=row;
  }
  return {rows,costs};
}


export type SelectedRequirements={preferences?:string[];mandatory_constraints?:string[]};
type PlaceFacts={fields:Record<string,{value:unknown;status:string}>};
const preferenceFields:Record<string,string>={quiet:'quiet_environment',toilets:'toilets',showers:'showers',
  'potable water':'potable_water','public transport':'public_transport_access',
  'wheelchair accessible':'wheelchair_accessible',campfire:'fire_allowed',pets:'pets_allowed'};
const requiredFields:Record<string,string>={toilets:'toilets',showers:'showers',potable_water:'potable_water',
  wheelchair_accessible:'wheelchair_accessible',fire_allowed:'fire_allowed',campfire:'fire_allowed',
  pets_allowed:'pets_allowed',vehicle_access:'vehicle_access',public_transport_access:'public_transport_access',walk_in_only:'walk_in_only'};
const factNames:Record<string,string>={toilets:'Toilets',showers:'Showers',potable_water:'Drinking water',fire_allowed:'Fire use',
  pets_allowed:'Pets',wheelchair_accessible:'Accessibility facilities',step_free_path:'Step-free path',
  vehicle_access:'Vehicle access to campsite',public_transport_access:'Public transport arrival'};
const rowNames:Record<string,string>={...facilityNames,quiet_environment:'Quiet surroundings',pets_allowed:'Pets allowed',
  public_transport_access:'Public transport access',wheelchair_accessible:'Wheelchair access',fire_allowed:'Fire use allowed',
  vehicle_access:'Vehicle access',walk_in_only:'Walk-in access only',step_free_path:'Step-free path'};
export function savedTermLabel(value:string,kind:'preference'|'constraint'|'accessibility'){
  const translated=termLabel(value,kind);return typeof translated==='string'?translated:value;
}
const accessFields:Record<string,string>={'step-free path':'step_free_path','wheelchair access':'wheelchair_accessible','wheelchair-accessible toilet':'accessible_toilet'};
const mealKeys=new Set(['ready-to-eat meals','self-catered meals','ready_to_eat','self_catered']);

// Read-only comparison of saved confirmed choices against saved facts and the
// exact digest-bound static catalogue. Never authorises matching/finalisation.
export function selectedRequirementsPresentation(reasons:string[],requirements:SelectedRequirements,place:PlaceFacts|null,accessibility:string[]=[]){
  reasons=reasons.map(englishSavedReason);
  const legacy=selectionPresentation(reasons);
  const rows:SelectionRow[]=legacy.rows.filter(row=>['Destination region','Group size','Transport'].includes(row.label));
  const selected=new Map<string,{key:string;field:string|null;terms:{value:string;kind:'preference'|'constraint'|'accessibility'}[]}>();
  function add(value:string,kind:'preference'|'constraint'|'accessibility'){
    const key=canonicalTerms([value],kind)[0];
    const fields=kind==='preference'?preferenceFields:kind==='constraint'?requiredFields:accessFields;
    const field=Object.hasOwn(fields,key)?fields[key]:null;
    const identity=field??kind+':'+key;
    const prior=selected.get(identity);
    if(prior){if(!prior.terms.some(term=>term.kind===kind&&term.value===key))prior.terms.push({value:key,kind});}
    else selected.set(identity,{key,field:field??null,terms:[{value:key,kind}]});
  }
  (requirements.mandatory_constraints??[]).forEach(value=>add(value,'constraint'));
  accessibility.forEach(value=>add(value,'accessibility'));
  (requirements.preferences??[]).forEach(value=>add(value,'preference'));
  function catalogueState(field:string):boolean|null{
    if(field==='accessible_toilet'){
      const values=[catalogueState('wheelchair_accessible'),catalogueState('toilets')];
      return values.includes(false)?false:values.every(value=>value===true)?true:null;
    }
    const fact=place?.fields[field];
    return fact?.status==='OFFICIAL'&&typeof fact.value==='boolean'?fact.value:null;
  }
  for(const item of selected.values()){
    const {field,terms,key}=item;
    const required=terms.some(term=>term.kind!=='preference');
    const kind=[...new Set(terms.map(term=>term.kind==='constraint'?'Required conditions':term.kind==='preference'?'Preferences':'Group accessibility and other needs'))].join(' · ');
    const label=field==='accessible_toilet'?'Accessible toilet':field?rowNames[field]??field:savedTermLabel(key,terms[0].kind);
    const states:(boolean|null)[]=[];
    if(field)for(const row of legacy.rows){if(row.facility===field&&row.state!==undefined)states.push(row.state);}
    if(field){
      const savedLabel=factNames[field];
      if(savedLabel)for(const value of [true,false,null]){
        const text=`Required condition: ${savedLabel}; registered information: ${value===true?'supported':value===false?'not supported':'unknown'}.`;
        if(reasons.includes(text))states.push(value);
      }
      if(facilityNames[field])for(const value of [true,false]){
        if(reasons.includes(`Campsite facilities: ${facilityNames[field]}; ${value?'Listed as provided.':'Not provided; make alternative arrangements.'}`))states.push(value);
      }
      for(const term of terms.filter(term=>term.kind==='preference')){
        if(reasons.includes(`Soft preference ${term.value} matches source facilities.`))states.push(true);
      }
      if(field==='quiet_environment'){
        if(reasons.includes('Synthetic quiet-environment attribute matches; it is not a real-world guarantee.'))states.push(true);
        if(reasons.includes('Actual quietness is not supplied.'))states.push(null);
      }
      const catalogued=catalogueState(field);
      if(catalogued!==null)states.push(catalogued);
    }
    const distinct=[...new Set(states)];
    const conflict=distinct.length>1;
    const state=distinct.length===1?distinct[0]:null;
    let detail=conflict?'The original filtering record conflicts with the bound source information. Verify it; do not treat this requirement as met.':
      state===null?'The saved information is insufficient to verify this requirement.':
      field&&facilityNames[field]?facilityDescription(field,state):
      field==='pets_allowed'?(state?'Campsite records allow ordinary pets.':'Campsite records do not allow ordinary pets.'):
      field==='quiet_environment'?(state?'The source describes a quiet environment; actual quietness is not guaranteed.':'The source does not support the quiet-environment preference.'):
      field==='fire_allowed'?(state?'The source permits fires in designated facilities subject to restrictions. Actual fire arrangements still require safety checks.':'The source does not support this fire requirement. See the safety check for restrictions.'):
      state?'Campsite records support this requirement.':'Campsite records do not support this requirement.';
    let result=conflict?'Conflicting information':state===true?'Supported by recorded data':state===false?'Not met':'Needs verification';
    if(!field&&(mealKeys.has(key)||key==='no_fires')){
      detail=key==='no_fires'?'No campfire is confirmed. View the formal safety check to verify the itinerary complies.':
        'This meal arrangement is confirmed. See the relevant equipment, cost and fire checks.';
      result='See the relevant checks';
    }
    rows.push({label,detail,kind,result,required,facility:field&&facilityNames[field]?field:undefined,state});
  }
  // Unselected known facilities belong below the main requirement comparison.
  const extra=legacy.rows.filter(row=>row.facility&&!rows.some(selected=>selected.facility===row.facility));
  return {rows,costs:legacy.costs,extra};
}
