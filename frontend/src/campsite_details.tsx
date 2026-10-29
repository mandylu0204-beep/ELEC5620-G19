import catalogue from '../../data/sydney_surrounds_v2_2/data/source_catalogue.json';
import { facilityNames, facilityDescription, type SelectionRow } from './campsite_selection';

type Place = {
  source_urls: string[];
  access_notes: string;
  static_restrictions: string[];
  fields: Record<string, {value: unknown; status: string}>;
};

export function cataloguePlace(id:string|undefined,catalogueId:string|undefined):Place|null {
  // Never project today's compiled place facts into a different saved source.
  if(!id||catalogueId!=='sydney-surrounds-2.2-2026-10-23')return null;
  const places:Record<string,Place> = catalogue.campsites;
  return Object.hasOwn(places,id)?places[id]:null;
}

export function additionalFacilities(place:Place|null,rows:SelectionRow[]):SelectionRow[]{
  if(!place)return [];
  return Object.entries(facilityNames).flatMap(([key,label])=>{
    const field=place.fields[key];
    const state=field?.status==='OFFICIAL'&&typeof field.value==='boolean'?field.value:null;
    if(rows.some(row=>row.facility===key&&row.state===state))return [];
    return [{label,detail:facilityDescription(key,state),facility:key,state}];
  });
}

export function campsiteSourceLabel(url:string){
  try{
    const parsed=new URL(url);const path=parsed.pathname.replace(/\/$/u,'');
    if(parsed.hostname==='www.nationalparks.nsw.gov.au'){
      if(/^\/camping-and-accommodation\/campgrounds\/[^/]+\/visitor-info$/u.test(path))return '官方到达与访客信息';
      if(/^\/camping-and-accommodation\/campgrounds\/[^/]+$/u.test(path))return '官方营地概况';
    }
    if(parsed.hostname==='www.cockatooisland.gov.au'){
      if(path==='/en/stay/waterfront-campground')return '官方营地概况';
      if(path==='/en/stay/waterfront-campground/byo-tent-option')return '官方自带帐篷露营说明';
    }
    return `资料来源：${parsed.hostname}${parsed.pathname}${parsed.search}${parsed.hash}`;
  }catch{return `资料来源：${url}`;}
}

export function CampsiteArrivalDetails({place}:{place:Place|null}) {
  if(!place)return null;
  return <>
    <h3>到达方式与注意事项</h3><p>{place.access_notes}</p>
    <p className="muted">营地接入资料不代表已确认实际班次、接驳或预订，出发前仍需核对。</p>
    <details className="source-details"><summary>营地规定与资料来源</summary>
      <ul>{place.static_restrictions.map(text=><li key={text}>{text}</li>)}</ul>
      {place.source_urls.map(url=><p key={url}><a href={url} target="_blank" rel="noreferrer">{campsiteSourceLabel(url)} ↗</a></p>)}
    </details>
  </>;
}
