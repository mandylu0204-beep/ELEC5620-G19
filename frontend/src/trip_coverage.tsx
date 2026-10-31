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
const explanation:Record<string,string>={MISSING:'No applicable information was found for this trip.',
  NOT_YET_OBSERVED:'Information for the trip period has not been published. Check again later.',
  STALE:'Existing information has expired. Update it before checking again.',CONFLICTING:'Applicable sources conflict. Verify them before checking again.',
  ROAD_STATE_UNKNOWN:'Existing information cannot confirm road access.'};
const range=(item:Range)=>`${item.start} to ${item.end}`;

export function TripCoveragePanel({value,planId,readOnly=false}:{value:TripCoverage|null|undefined;requestId?:string;planId?:string;readOnly?:boolean}){
  if(!value)return null;
  if(!value.issues.length)return null;
  return <section className="trip-coverage" aria-label="Trip information to confirm"><h3>Confirm before departure</h3>
    {value.weather_requires_staged_checks&&value.issues.some(item=>item.kind==='WEATHER')&&<p>For longer trips, check weather again near departure and during the trip.</p>}
    <ul>{value.issues.map((issue,index)=><li key={index}><strong>{campName(issue.campsite_id)} · {checkNames[issue.kind]??issue.kind}</strong>
      <p>{issue.code==='OUTSIDE_VALIDITY'?issue.uncovered_ranges.length
        ?`Dates still to confirm: ${issue.uncovered_ranges.map(range).join('; ')}.`
        :'Information does not yet cover the entire trip.'
        :explanation[issue.code]??'This trip information remains unconfirmed.'}</p>
      {issue.code!=='OUTSIDE_VALIDITY'&&issue.uncovered_ranges.length>0&&<p>Unconfirmed dates: {issue.uncovered_ranges.map(range).join('; ')}.</p>}
      {issue.kind==='WEATHER'?<p>Suggested recheck:  {value.next_weather_check_on?`${value.next_weather_check_on} or later`:'close to departure'}; check the weather again.</p>:<p>Check again later or consider changing dates or campsite.</p>}
      {issue.available_ranges.length>0&&<details><summary>View information coverage dates</summary><ul>{issue.available_ranges.map((item,i)=><li key={i}>{range(item)}</li>)}</ul></details>}
    </li>)}</ul>
    {(value.alternative_campsites.length>0||value.alternative_dates.length>0)&&<div className="coverage-options"><h3>Possible adjustments</h3>
      {value.alternative_campsites.length>0&&<><p>Other campsites to consider for the same dates: </p><ul>{value.alternative_campsites.map(item=><li key={item.campsite_id}>{campName(item.campsite_id)}</li>)}</ul></>}
      {value.alternative_dates.length>0&&<><p>Keeping the campsite and number of nights, consider these dates: </p><ul>{value.alternative_dates.map(item=><li key={item.start_date}>{item.start_date} to {item.end_date}</li>)}</ul></>}
      <p className="muted">Run checks again after making changes.</p></div>}
    {planId&&!readOnly&&<Link className="text-link" to={tripUpdatePath(planId)}>Review and reconfirm this trip requirements ↗</Link>}
  </section>;
}
