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
  NOT_YET_OBSERVED:'覆盖此次出行日期的资料尚未发布或观测，可保留方案，待资料发布后重新检查。',
  STALE:'现有资料已经过期，需要更新后再检查。',CONFLICTING:'同时适用的来源内容不一致，需要核实后再检查。',
  ROAD_STATE_UNKNOWN:'现有资料无法确认道路是否开放。'};
const range=(item:Range)=>`${item.start} 至 ${item.end}`;

export function TripCoveragePanel({value,planId,readOnly=false}:{value:TripCoverage|null|undefined;requestId?:string;planId?:string;readOnly?:boolean}){
  if(!value)return null;
  if(!value.issues.length)return <p className="coverage-complete">已找到覆盖此次行程的四类安全资料，具体出行限制见下方检查结果。</p>;
  return <section className="trip-coverage" aria-label="资料覆盖与可选调整"><h3>哪些资料还不能支持这次行程？</h3>
    {value.weather_forecast_window&&value.issues.some(item=>item.kind==='WEATHER')&&<div className="coverage-options"><p>行程已保留，天气仍待确认。本次检查日期为 {value.checked_on}，当前模拟天气预报覆盖 {range(value.weather_forecast_window)}。</p>
      {value.weather_requires_staged_checks?<p>这次行程超过七天，单次天气预报无法覆盖全程；需要临近出发及途中分段检查，当前不能确认全程安全。</p>
        :value.next_weather_check_on&&<p>可先核对行程、装备与费用，建议在 {value.next_weather_check_on} 或之后重新检查天气。届时仍以实际检查结果为准。</p>}</div>}
    <ul>{value.issues.map((issue,index)=><li key={index}><strong>{campName(issue.campsite_id)} · {checkNames[issue.kind]??issue.kind}</strong>
      <p>{issue.code==='OUTSIDE_VALIDITY'?issue.uncovered_ranges.length
        ?`尚未覆盖：${issue.uncovered_ranges.map(range).join('；')}。`
        :'现有资料分布于多个有效区间，尚没有一份资料能独立覆盖整段行程。'
        :explanation[issue.code]??'当前资料尚不能支持此次行程的判断。'}</p>
      {issue.code!=='OUTSIDE_VALIDITY'&&issue.uncovered_ranges.length>0&&<p>缺少日期：{issue.uncovered_ranges.map(range).join('；')}。</p>}
      <p>影响：本项检查尚未完成，不能据此确认整段行程安全。处理：调整日期或营地，或保留草稿等待适用资料更新后重新检查。</p>
      {issue.kind==='WEATHER'&&<p>建议重查：{value.next_weather_check_on?`${value.next_weather_check_on} 或之后`:'临近出发、预报覆盖所缺日期后'}{value.weather_requires_staged_checks?'，并在途中分段复查':''}；届时仍以实际资料为准。</p>}
      {issue.available_ranges.length>0&&<details><summary>查看已发布资料的日期</summary><ul>{issue.available_ranges.map((item,i)=><li key={i}>{range(item)}</li>)}</ul></details>}
    </li>)}</ul>
    {(value.alternative_campsites.length>0||value.alternative_dates.length>0)&&<div className="coverage-options"><h3>可以参考的调整</h3>
      {value.alternative_campsites.length>0&&<><p>相同日期下，资料覆盖完整的其他营地：</p><ul>{value.alternative_campsites.map(item=><li key={item.campsite_id}>{campName(item.campsite_id)}</li>)}</ul></>}
      {value.alternative_dates.length>0&&<><p>保留当前营地和晚数，可参考这些有完整资料的日期：</p><ul>{value.alternative_dates.map(item=><li key={item.start_date}>{item.start_date} 至 {item.end_date}</li>)}</ul></>}
      <p className="muted">这些选项已核对资料覆盖和营地基本条件；完整费用、装备和安全仍需重新评估，由你决定是否调整。</p></div>}
    {!value.alternative_campsites.length&&!value.alternative_dates.length&&<p>当前资料中未找到保留现有条件且覆盖完整的替代选项。可调整出行日期、晚数或营地，或保留草稿等待资料更新。</p>}
    {planId&&!readOnly&&<Link className="text-link" to={tripUpdatePath(planId)}>调整本次需求并重新确认 ↗</Link>}
  </section>;
}
