import { chineseProse } from './display_facts';

export const facilityNames:Record<string,string>={toilets:'厕所',showers:'淋浴',potable_water:'饮用水'};
export type SelectionRow={label:string;detail:string;facility?:string;state?:boolean|null;required?:boolean};
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
