const aud=(cents:number)=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',currencyDisplay:'code'}).format(cents/100);

export type PreparationSummary={system_preparation:true;transport_type:string|null;origin_label:string;
  access_and_capacity:boolean|null;estimated_total_vehicle_km:string|null;vehicle_count:number|null;
  estimated_transport_cents:number|null;meal_mode:string|null;
  source_refs:{dataset_file:string;record_id:string;provenance:{source_date:string}}[]};

export function TripPreparation({value}:{value:PreparationSummary|null|undefined}){
  if(!value)return null;
  const car=value.transport_type==='CAR';
  return <section className="panel" aria-label="Transport and meals for this trip">
    <h2>Transport and meals for this trip</h2>
    <p>Departure point: {value.origin_label.replace(/\s*\((?:fixed simulated origin|fixed demonstration origin)\)/,'').replace('Central Sydney','Sydney CBD').trim()}. The system filters using registered campsite access information. All costs below are simulated estimates.</p>
    <dl className="summary-list"><div><dt>Transport mode</dt><dd>{car?'Car':value.transport_type==='PUBLIC_TRANSPORT'?'Public transport':'To be confirmed'}</dd></div>
      <div><dt>{car?'Campsite access and vehicle capacity':'Campsite public-transport access information'}</dt><dd>{value.access_and_capacity===true?'Meets this check':value.access_and_capacity===false?'Does not meet this check':'Check incomplete or insufficient information'}</dd></div>
      {car&&<><div><dt>Confirmed vehicles for this trip</dt><dd>{value.vehicle_count??'Unknown'} vehicles</dd></div>
        <div><dt>Combined return distance for all vehicles (simulated)</dt><dd>{value.estimated_total_vehicle_km??'Unknown'} km</dd></div></>}
      <div><dt>Estimated transport cost{car?'(including parking)':'(return)'}</dt><dd>{value.estimated_transport_cents===null?'Unknown; cannot be treated as zero cost':aud(value.estimated_transport_cents)}</dd></div>
      <div><dt>Meal arrangement</dt><dd>{value.meal_mode==='SELF_CATERED'?'Self-catering; verify stove, fuel and cookware':value.meal_mode==='READY_TO_EAT'?'Ready-to-eat meals':'To be confirmed'}</dd></div>
    </dl>
    {!car&&<p className="muted">An access flag does not verify services or confirm tickets. After selecting a campsite, check outbound, last return and final connections before departure. The system does not invent routes, schedules or live fares.</p>}
  </section>;
}
