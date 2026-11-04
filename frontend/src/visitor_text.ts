// Presentation only. Never use this text to determine risk, eligibility or input identity.
// Only system/model copy is passed here; user-entered names and requirements stay intact.
export function visitorText(value:string|null|undefined):string{
 if(!value)return '';
 if(!/\b(?:synthetic|simulated|fictional|fake|demonstration|demo)\b/i.test(value))return value;
 return value
  .replace(/\bSynthetic data only\s*[;:.]?\s*/gi,'')
  .replace(/\b(?:this is|it is) (?:only )?(?:a )?(?:synthetic |simulated )?(?:demo|simulation)\.?/gi,'')
  .replace(/\b(?:Demonstration|Demo) only\s*:\s*/gi,'')
  .replace(/\((?:synthetic|simulated|demo) data\)/gi,'')
  .replace(/\b(?:synthetic|simulated|fictional|fake)(?:\s+demo)?\s+(?:data|information|facts)\b/gi,'available information')
  .replace(/\b(?:synthetic|simulated|fictional|demonstration|demo)\s+/gi,'')
  .replace(/\bsynthetic_/gi,'')
  .replace(/[ \t]{2,}/g,' ').replace(/\s+([,;.])/g,'$1').trim();
}
export function sourceDisplayName(file:string):string{
 const names:Record<string,string>={
  'synthetic_campsites.csv':'Campsite information','synthetic_gear_rules.csv':'Equipment rules',
  'synthetic_cost_reference.csv':'Cost reference','synthetic_safety_scenarios.json':'Safety information',
  'synthetic_weather_events.json':'Weather information','runtime_safety_evidence.json':'Safety evidence',
 };
 const base=file.split('/').pop()??file;return Object.hasOwn(names,base)?names[base]:visitorText(base);
}

// A readable diagnostic summary, not a replacement for the original server audit.
export function diagnosticSummary(value:unknown):unknown{
 if(Array.isArray(value))return value.map(diagnosticSummary);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value)
  .filter(([key])=>!['source_type','demo_only','file_digests','fixture_digests','selection_config','workflow_context','source_context'].includes(key))
  .map(([key,item])=>[key,key==='dataset_file'&&typeof item==='string'?sourceDisplayName(item):diagnosticSummary(item)]));
 return typeof value==='string'?visitorText(value):value;
}
