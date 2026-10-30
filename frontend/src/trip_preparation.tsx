const aud=(cents:number)=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD',currencyDisplay:'code'}).format(cents/100);

export type PreparationSummary={system_preparation:true;transport_type:string|null;origin_label:string;
  access_and_capacity:boolean|null;estimated_total_vehicle_km:string|null;vehicle_count:number|null;
  estimated_transport_cents:number|null;meal_mode:string|null;
  source_refs:{dataset_file:string;record_id:string;provenance:{source_date:string}}[]};

export function TripPreparation({value}:{value:PreparationSummary|null|undefined}){
  if(!value)return null;
  const car=value.transport_type==='CAR';
  return <section className="panel" aria-label="本次交通与用餐安排">
    <h2>本次交通与用餐安排</h2>
    <p>出发地：{value.origin_label.replace('（固定模拟出发地）','')}。系统依据登记的营地可达资料筛选，以下费用均为模拟估算。</p>
    <dl className="summary-list"><div><dt>交通方式</dt><dd>{car?'汽车':value.transport_type==='PUBLIC_TRANSPORT'?'公共交通':'待确认'}</dd></div>
      <div><dt>{car?'营地接入与车辆容量':'营地公共交通可达资料'}</dt><dd>{value.access_and_capacity===true?'本次检查符合':value.access_and_capacity===false?'本次检查不符合':'检查尚未完成或资料不足'}</dd></div>
      {car&&<><div><dt>本次确认车辆</dt><dd>{value.vehicle_count??'未知'} 辆</dd></div>
        <div><dt>所有车辆往返累计里程（模拟）</dt><dd>{value.estimated_total_vehicle_km??'未知'} km</dd></div></>}
      <div><dt>预计交通费用{car?'（含停车）':'（往返）'}</dt><dd>{value.estimated_transport_cents===null?'未知，不能按零费用处理':aud(value.estimated_transport_cents)}</dd></div>
      <div><dt>用餐方式</dt><dd>{value.meal_mode==='SELF_CATERED'?'自行烹饪，核对炉具、燃料和炊具':value.meal_mode==='READY_TO_EAT'?'即食餐食':'待确认'}</dd></div>
    </dl>
    {!car&&<p className="muted">可达标记不代表已核实班次或已订票。选定营地后，出发前核对去程、返程末班及下车或下船后的接驳；系统不编造具体线路、时刻和实时票价。</p>}
  </section>;
}
