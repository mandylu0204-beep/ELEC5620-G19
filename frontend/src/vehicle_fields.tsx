import type { DraftEquipment } from './profile_guidance';
import { FieldHint } from './trip_flow';

export function VehicleFields({equipment,issues,guidance,onChange,onRemove,onAdd}: {
  equipment:DraftEquipment[];issues:Record<string,string>;guidance:Record<string,string>;
  onChange:(index:number,patch:Partial<DraftEquipment>)=>void;onRemove:(index:number)=>void;onAdd:()=>void;
}) {
  const rows=equipment.map((item,index)=>({item,index})).filter(({item})=>item.item_key==='vehicle');
  return <section className="vehicle-details" aria-label="车辆安排"><div className="panel-title"><h3>可用车辆</h3>
    <button id="add-vehicle" type="button" className="text-button" onClick={onAdd}>添加车辆</button></div>
    <p className="field-hint">相同座位数的车辆可合并填写；不同座位数请分别添加。只登记本次实际可用的车辆。</p>
    {rows.map(({item,index},position)=><article key={index} className={Object.keys(guidance).some(id=>id.startsWith('gear-')&&id.endsWith('-'+index))?'vehicle-card equipment-card-needed':'vehicle-card'}>
      <header><strong>车辆 {position+1}</strong><button type="button" className="text-button" aria-label={`移除车辆 ${position+1}`} onClick={()=>onRemove(index)}>移除</button></header>
      <div className="form-grid"><div><label htmlFor={`gear-quantity-${index}`}>车辆数量</label>
        <input id={`gear-quantity-${index}`} aria-label={`车辆 ${position+1} 数量`} type="number" min="0" step="1" placeholder="未知" value={item.quantity}
          aria-invalid={!!(issues[`gear-quantity-${index}`]||guidance[`gear-quantity-${index}`]||position===0&&guidance['vehicle-count'])} aria-describedby={`gear-quantity-hint-${index}`}
          onChange={event=>onChange(index,{quantity:event.target.value})}/>
        <FieldHint id={`gear-quantity-hint-${index}`} error={issues[`gear-quantity-${index}`]??guidance[`gear-quantity-${index}`]??(position===0?guidance['vehicle-count']:undefined)}/></div>
      <div><label htmlFor={`gear-capacity-${index}`}>每辆载客人数（含驾驶员）</label>
        <input id={`gear-capacity-${index}`} aria-label={`车辆 ${position+1} 载客人数`} type="number" min="1" step="1" placeholder="例如 5" value={item.capacity}
          aria-invalid={!!(issues[`gear-capacity-${index}`]||guidance[`gear-capacity-${index}`])} aria-describedby={`gear-capacity-hint-${index}`}
          onChange={event=>onChange(index,{capacity:event.target.value})}/>
        <FieldHint id={`gear-capacity-hint-${index}`} error={issues[`gear-capacity-${index}`]??guidance[`gear-capacity-${index}`]}>包含驾驶员，例如 5 座车填 5。</FieldHint></div></div>
      <label className="checkbox-label"><input id={`gear-confirmed-${index}`} type="checkbox" checked={item.confirmed} aria-label={`车辆 ${position+1} 已确认可用`}
        aria-invalid={!!guidance[`gear-confirmed-${index}`]} aria-describedby={`gear-confirmed-hint-${index}`}
        onChange={event=>onChange(index,{confirmed:event.target.checked})}/>已确认可用于本次出行</label>
      <FieldHint id={`gear-confirmed-hint-${index}`} error={guidance[`gear-confirmed-${index}`]}/>
    </article>)}
  </section>;
}
