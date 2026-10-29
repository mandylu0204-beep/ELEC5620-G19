import { Link } from 'react-router-dom';
import { tripUpdatePath } from './trip_update';
import { campName } from './plans';
import { checkNames } from './plan_language';

type Range={start:string;end:string};
export type TripCoverage={dataset_version:string;checked_on:string;selection_digest:string;
  weather_forecast_window?:Range;next_weather_check_on?:string|null;weather_requires_staged_checks?:boolean;
  issues:{campsite_id:string;kind:string;code:string;requested_range:Range;available_ranges:Range[];uncovered_ranges:Range[];reason:string}[];
  alternative_campsites:{campsite_id:string;start_date:string;end_date:string}[];
  alternative_dates:{start_date:string;end_date:string}[]};
const explanation:Record<string,string>={MISSING:'没有找到适用于此次行程的资料。',
  NOT_YET_OBSERVED:'出行期间的信息尚未发布，请稍后重新检查。',
  STALE:'现有资料已经过期，需要更新后再检查。',CONFLICTING:'同时适用的来源内容不一致，需要核实后再检查。',
  ROAD_STATE_UNKNOWN:'现有资料无法确认道路是否开放。'};
const range=(item:Range)=>`${item.start} 至 ${item.end}`;

export function TripCoveragePanel({value,planId,readOnly=false}:{value:TripCoverage|null|undefined;requestId?:string;planId?:string;readOnly?:boolean}){
  if(!value)return null;
  if(!value.issues.length)return null;
  return <section className="trip-coverage" aria-label="待确认的出行信息"><h3>出发前还需确认</h3>
    {value.weather_requires_staged_checks&&value.issues.some(item=>item.kind==='WEATHER')&&<p>行程较长，请在临近出发及途中分段查看天气。</p>}
    <ul>{value.issues.map((issue,index)=><li key={index}><strong>{campName(issue.campsite_id)} · {checkNames[issue.kind]??issue.kind}</strong>
      <p>{issue.code==='OUTSIDE_VALIDITY'?issue.uncovered_ranges.length
        ?`以下日期仍待确认：${issue.uncovered_ranges.map(range).join('；')}。`
        :'行程期间的信息尚未确认完整。'
        :explanation[issue.code]??'这项出行信息仍待确认。'}</p>
      {issue.code!=='OUTSIDE_VALIDITY'&&issue.uncovered_ranges.length>0&&<p>待确认日期：{issue.uncovered_ranges.map(range).join('；')}。</p>}
      {issue.kind==='WEATHER'?<p>建议在 {value.next_weather_check_on?`${value.next_weather_check_on} 或之后`:'临近出发时'}重新检查天气。</p>:<p>请稍后重新检查，或考虑调整日期与营地。</p>}
      {issue.available_ranges.length>0&&<details><summary>查看信息适用日期</summary><ul>{issue.available_ranges.map((item,i)=><li key={i}>{range(item)}</li>)}</ul></details>}
    </li>)}</ul>
    {(value.alternative_campsites.length>0||value.alternative_dates.length>0)&&<div className="coverage-options"><h3>可以参考的调整</h3>
      {value.alternative_campsites.length>0&&<><p>相同日期下可考虑的其他营地：</p><ul>{value.alternative_campsites.map(item=><li key={item.campsite_id}>{campName(item.campsite_id)}</li>)}</ul></>}
      {value.alternative_dates.length>0&&<><p>保留当前营地和晚数，可考虑这些日期：</p><ul>{value.alternative_dates.map(item=><li key={item.start_date}>{item.start_date} 至 {item.end_date}</li>)}</ul></>}
      <p className="muted">调整后需重新检查方案。</p></div>}
    {planId&&!readOnly&&<Link className="text-link" to={tripUpdatePath(planId)}>调整本次需求并重新确认 ↗</Link>}
  </section>;
}
