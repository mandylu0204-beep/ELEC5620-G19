import { chineseProse } from './display_facts';
import {canonicalTerms,termLabel} from './user_terms';

export const facilityNames:Record<string,string>={toilets:'厕所',showers:'淋浴',potable_water:'饮用水'};
export type SelectionRow={label:string;detail:string;facility?:string;state?:boolean|null;required?:boolean;kind?:string;result?:string};
export function facilityDescription(key:string,state:boolean|null){
  return state===null?'营地资料尚未明确，待确认。':state?'营地资料登记提供。':key==='potable_water'?'营地资料登记不提供，需自备饮用水。':'营地资料登记不提供。';
}
const facilityKey=(name:string)=>Object.keys(facilityNames).find(key=>facilityNames[key]===name);

// Layout of known saved reason text only. Never determines a match, risk or eligibility.
// Unrecognised prose stays intact; raw records are always rendered separately.
export function selectionPresentation(reasons:string[]){
  const rows:SelectionRow[]=[];const costs:string[]=[];
  for(const text of reasons){
    const visible=chineseProse(text);if(!visible)continue;
    const cost=visible.match(/^住宿费用：(.+)$/u);
    if(cost){if(!costs.includes(cost[1]))costs.push(cost[1]);continue;}
    const required=visible.match(/^必须条件：([^，]+)，登记信息为(支持|不支持|未知)。$/u);
    const facility=visible.match(/^营地配套：(.+?)(已登记提供。|未提供，需另作安排。)$/u);
    let row:SelectionRow;
    if(required&&facilityKey(required[1]))row={label:required[1],detail:facilityDescription(facilityKey(required[1])!,required[2]==='未知'?null:required[2]==='支持'),facility:facilityKey(required[1]),state:required[2]==='未知'?null:required[2]==='支持',required:true};
    else if(facility&&facilityKey(facility[1]))row={label:facility[1],detail:facilityDescription(facilityKey(facility[1])!,facility[2]==='已登记提供。'),facility:facilityKey(facility[1]),state:facility[2]==='已登记提供。'};
    else{
      const labelled=visible.match(/^(目的地区域|同行人数|交通|必须条件|营地配套)：(.+)$/u);
      row=labelled?{label:labelled[1],detail:labelled[2]}:{label:'其他筛选依据',detail:visible};
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
const factNames:Record<string,string>={toilets:'厕所',showers:'淋浴',potable_water:'饮用水',fire_allowed:'用火',
  pets_allowed:'宠物同行',wheelchair_accessible:'无障碍设施',step_free_path:'无台阶通道',
  vehicle_access:'车辆进入营地',public_transport_access:'公共交通抵达'};
const rowNames:Record<string,string>={...facilityNames,quiet_environment:'安静的环境',pets_allowed:'允许携带宠物',
  public_transport_access:'公共交通可达',wheelchair_accessible:'轮椅通行',fire_allowed:'允许用火',
  vehicle_access:'车辆可达',walk_in_only:'仅可步行进入',step_free_path:'无台阶通道'};
export function savedTermLabel(value:string,kind:'preference'|'constraint'|'accessibility'){
  const translated=termLabel(value,kind);return typeof translated==='string'?translated:value;
}
const accessFields:Record<string,string>={'step-free path':'step_free_path','wheelchair access':'wheelchair_accessible','wheelchair-accessible toilet':'accessible_toilet'};
const mealKeys=new Set(['ready-to-eat meals','self-catered meals','ready_to_eat','self_catered']);

// Read-only comparison of saved confirmed choices against saved facts and the
// exact digest-bound static catalogue. Never authorises matching/finalisation.
export function selectedRequirementsPresentation(reasons:string[],requirements:SelectedRequirements,place:PlaceFacts|null,accessibility:string[]=[]){
  const legacy=selectionPresentation(reasons);
  const rows:SelectionRow[]=legacy.rows.filter(row=>['目的地区域','同行人数','交通'].includes(row.label));
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
    const kind=[...new Set(terms.map(term=>term.kind==='constraint'?'必须条件':term.kind==='preference'?'偏好':'同行特殊需求'))].join(' · ');
    const label=field==='accessible_toilet'?'无障碍厕所':field?rowNames[field]??field:savedTermLabel(key,terms[0].kind);
    const states:(boolean|null)[]=[];
    if(field){
      const savedLabel=factNames[field];
      if(savedLabel)for(const value of [true,false,null]){
        const text=`必须条件：${savedLabel}，登记信息为${value===true?'支持':value===false?'不支持':'未知'}。`;
        if(reasons.includes(text))states.push(value);
      }
      if(facilityNames[field])for(const value of [true,false]){
        if(reasons.includes(`营地配套：${facilityNames[field]}${value?'已登记提供。':'未提供，需另作安排。'}`))states.push(value);
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
    let detail=conflict?'原筛选记录与绑定资料的说明不一致，请核实；不能按已满足处理。':
      state===null?'这次保存的资料不足以核实此项要求。':
      field&&facilityNames[field]?facilityDescription(field,state):
      field==='pets_allowed'?(state?'营地资料登记允许携带普通宠物。':'营地资料登记不允许普通宠物。'):
      field==='quiet_environment'?(state?'资料标注为安静环境，但不保证现场实际安静。':'资料未支持安静环境偏好。'):
      field==='fire_allowed'?(state?'登记资料在指定设施和限制条件下允许用火；实际用火安排仍须通过安全检查。':'登记资料不支持此项用火要求；具体限制见安全检查。'):
      state?'营地资料登记支持此项要求。':'营地资料登记不支持此项要求。';
    let result=conflict?'资料冲突':state===true?'资料符合':state===false?'未满足':'待核实';
    if(!field&&(mealKeys.has(key)||key==='no_fires')){
      detail=key==='no_fires'?'已确认不使用营火；实际行程是否遵守，请查看正式安全检查。':
        '已确认此用餐方式；装备准备、费用及用火条件请查看对应检查。';
      result='另见专项检查';
    }
    rows.push({label,detail,kind,result,required,facility:field&&facilityNames[field]?field:undefined,state});
  }
  // Unselected known facilities belong below the main requirement comparison.
  const extra=legacy.rows.filter(row=>row.facility&&!rows.some(selected=>selected.facility===row.facility));
  return {rows,costs:legacy.costs,extra};
}
