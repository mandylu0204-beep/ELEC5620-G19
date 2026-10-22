import catalogue from '../../data/sydney_surrounds_v2_2/data/source_catalogue.json';
import manifest from '../../data/sydney_surrounds_v2_2/manifest.json';

type Place = {
  source_urls: string[];
  access_notes: string;
  static_restrictions: string[];
  fields: Record<string, {value: unknown; status: string}>;
};

export function CampsiteDetails({id,source}:{id:string;source?:{dataset_version:string;file_digests?:Record<string,string>}}) {
  // Never project today's compiled place facts into a different saved source.
  if(source?.dataset_version!==catalogue.dataset_version ||
     source.file_digests?.['source_catalogue.json']!==manifest.files_sha256['data/source_catalogue.json'])return null;
  const places:Record<string,Place> = catalogue.campsites;
  const place=places[id];
  if(!place)return null; // Historical fictional IDs retain their original data.
  const state=(key:string,yes:string,no:string)=>{
    const field=place.fields[key];
    return field?.status==='OFFICIAL' && typeof field.value==='boolean'
      ?field.value?yes:no:'待确认';
  };
  return <section className="panel">
    <div className="section-title"><span className="eyebrow">ABOUT THE CAMPGROUND</span><h2>营地与到达方式</h2></div>
    <p>{place.access_notes}</p>
    <dl className="cost-summary">
      <div><dt>饮用水</dt><dd>{state('potable_water','有饮用水供应','需自备饮用水')}</dd></div>
      <div><dt>厕所</dt><dd>{state('toilets','有','无')}</dd></div>
      <div><dt>淋浴</dt><dd>{state('showers','有','无')}</dd></div>
    </dl>
    <details><summary>营地规定</summary><ul>{place.static_restrictions.map(text=><li key={text}>{text}</li>)}</ul></details>
    <p><a href={place.source_urls[0]} target="_blank" rel="noreferrer">查看官方营地信息 ↗</a></p>
  </section>;
}
