import { Link } from 'react-router-dom';
import { campName } from './plans';
import { checkNames } from './plan_language';

type Range={start:string;end:string};
export type TripCoverage={dataset_version:string;checked_on:string;selection_digest:string;
  issues:{campsite_id:string;kind:string;code:string;requested_range:Range;available_ranges:Range[];uncovered_ranges:Range[];reason:string}[];
  alternative_campsites:{campsite_id:string;start_date:string;end_date:string}[];
  alternative_dates:{start_date:string;end_date:string}[]};
const explanation:Record<string,string>={MISSING:'没有找到适用于此次行程的资料。',
  NOT_YET_OBSERVED:'覆盖此次出行日期的资料尚未发布或观测，可保留方案，待资料发布后重新检查。',
  STALE:'现有资料已经过期，需要更新后再检查。',CONFLICTING:'同时适用的来源内容不一致，需要核实后再检查。',
  ROAD_STATE_UNKNOWN:'现有资料无法确认道路是否开放。'};
const range=(item:Range)=>`${item.start} 至 ${item.end}`;

export function TripCoveragePanel({value,requestId}:{value:TripCoverage|null|undefined;requestId:string}){
  if(!value)return null;
  if(!value.issues.length)return <p className="coverage-complete">已找到覆盖此次行程的四类安全资料，具体出行限制见下方检查结果。</p>;
  return <section className="trip-coverage" aria-label="资料覆盖与可选调整"><h3>哪些资料还不能支持这次行程？</h3>
    <ul>{value.issues.map((issue,index)=><li key={index}><strong>{campName(issue.campsite_id)} · {checkNames[issue.kind]??issue.kind}</strong>
      <p>{issue.code==='OUTSIDE_VALIDITY'?issue.uncovered_ranges.length
        ?`尚未覆盖：${issue.uncovered_ranges.map(range).join('；')}。`
        :'现有资料分布于多个有效区间，尚没有一份资料能独立覆盖整段行程。'
        :explanation[issue.code]??'当前资料尚不能支持此次行程的判断。'}</p>
      {issue.available_ranges.length>0&&<details><summary>查看已发布资料的日期</summary><ul>{issue.available_ranges.map((item,i)=><li key={i}>{range(item)}</li>)}</ul></details>}
    </li>)}</ul>
    {(value.alternative_campsites.length>0||value.alternative_dates.length>0)&&<div className="coverage-options"><h3>可以参考的调整</h3>
      {value.alternative_campsites.length>0&&<><p>相同日期下，资料覆盖完整的其他营地：</p><ul>{value.alternative_campsites.map(item=><li key={item.campsite_id}>{campName(item.campsite_id)}</li>)}</ul></>}
      {value.alternative_dates.length>0&&<><p>保留当前营地和晚数，可参考这些有完整资料的日期：</p><ul>{value.alternative_dates.map(item=><li key={item.start_date}>{item.start_date} 至 {item.end_date}</li>)}</ul></>}
      <p className="muted">这些选项已核对资料覆盖和营地基本条件；完整费用、装备和安全仍需重新评估，由你决定是否调整。</p></div>}
    {!value.alternative_campsites.length&&!value.alternative_dates.length&&<p>当前资料中未找到保留现有条件且覆盖完整的替代选项。可调整出行日期、晚数或营地，或保留草稿等待资料更新。</p>}
    <Link className="text-link" to={'/request?copy_from='+encodeURIComponent(requestId)}>调整需求并重新确认 ↗</Link>
  </section>;
}
