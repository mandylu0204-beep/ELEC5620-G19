import type { DraftEquipment } from './profile_guidance';
import { FieldHint } from './trip_flow';

export function VehicleFields({equipment,issues,guidance,onChange,onRemove,onAdd}: {
  equipment:DraftEquipment[];issues:Record<string,string>;guidance:Record<string,string>;
  onChange:(index:number,patch:Partial<DraftEquipment>)=>void;onRemove:(index:number)=>void;onAdd:()=>void;
}) {
  const rows=equipment.map((item,index)=>({item,index})).filter(({item})=>item.item_key==='vehicle');
  return <section className="vehicle-details" aria-label="Vehicle arrangements"><div className="panel-title"><h3>Available vehicles</h3>
    <button id="add-vehicle" type="button" className="text-button" onClick={onAdd}>Add vehicle</button></div>
    <p className="field-hint">Vehicles with the same seating capacity can share a row. Add separate rows for different capacities. Record only vehicles available for this trip.</p>
    {rows.map(({item,index},position)=><article key={index} className={Object.keys(guidance).some(id=>id.startsWith('gear-')&&id.endsWith('-'+index))?'vehicle-card equipment-card-needed':'vehicle-card'}>
      <header><strong>Vehicles {position+1}</strong><button type="button" className="text-button" aria-label={`Remove vehicle ${position+1}`} onClick={()=>onRemove(index)}>Remove</button></header>
      <div className="form-grid"><div><label htmlFor={`gear-quantity-${index}`}>Number of vehicles</label>
        <input id={`gear-quantity-${index}`} aria-label={`Vehicles ${position+1} Quantity`} type="number" min="0" step="1" placeholder="Unknown" value={item.quantity}
          aria-invalid={!!(issues[`gear-quantity-${index}`]||guidance[`gear-quantity-${index}`]||position===0&&guidance['vehicle-count'])} aria-describedby={`gear-quantity-hint-${index}`}
          onChange={event=>onChange(index,{quantity:event.target.value})}/>
        <FieldHint id={`gear-quantity-hint-${index}`} error={issues[`gear-quantity-${index}`]??guidance[`gear-quantity-${index}`]??(position===0?guidance['vehicle-count']:undefined)}/></div>
      <div><label htmlFor={`gear-capacity-${index}`}>Seats per vehicle (including driver)</label>
        <input id={`gear-capacity-${index}`} aria-label={`Vehicles ${position+1} Seating capacity`} type="number" min="1" step="1" placeholder="For example 5" value={item.capacity}
          aria-invalid={!!(issues[`gear-capacity-${index}`]||guidance[`gear-capacity-${index}`])} aria-describedby={`gear-capacity-hint-${index}`}
          onChange={event=>onChange(index,{capacity:event.target.value})}/>
        <FieldHint id={`gear-capacity-hint-${index}`} error={issues[`gear-capacity-${index}`]??guidance[`gear-capacity-${index}`]}>Includes the driver; for example,  5 seat vehicle: enter 5.</FieldHint></div></div>
    </article>)}
  </section>;
}
