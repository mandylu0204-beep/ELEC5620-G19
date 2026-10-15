type Kind = 'preference' | 'constraint' | 'accessibility';
// Exact structured-field labels only. Free prose and unknown terms stay intact.
const vocabulary: Record<Kind, Record<string, string[]>> = {
  preference: {
    quiet:['安静','安静的环境'], 'ready-to-eat meals':['即食餐食','即食食品','无需烹饪的餐食'],
    'self-catered meals':['自行烹饪','自己做饭'], campfire:['营火'], toilets:['厕所'],
    showers:['淋浴'], 'potable water':['饮用水设施'], 'public transport':['公共交通'],
    'wheelchair accessible':['轮椅通行'], pets:['携带宠物'],
  },
  constraint: {
    toilets:['厕所','必须有厕所','需要厕所'], showers:['淋浴','必须有淋浴','需要淋浴'],
    potable_water:['饮用水设施','需要饮用水设施'], wheelchair_accessible:['轮椅通行','需要轮椅通行'],
    fire_allowed:['允许营火'], campfire:['营火'], no_fires:['不生火','不使用营火','禁止营火'],
    pets_allowed:['允许携带宠物'], vehicle_access:['车辆可达'],
    public_transport_access:['公共交通可达'], walk_in_only:['仅可步行进入'],
  },
  accessibility: {
    'step-free path':['无台阶通道','需要无台阶通道'],
    'wheelchair access':['轮椅通行'], 'wheelchair-accessible toilet':['无障碍厕所'],
  },
};

export function canonicalTerms(values:string[],kind:Kind):string[] {
  return values.map(value=>{
    const text=value.trim();
    return Object.entries(vocabulary[kind]).find(([key,labels])=>key===text.toLowerCase()||labels.includes(text))?.[0]??text;
  });
}

export function termLabel(value:string,kind:Kind):string {
  return vocabulary[kind][value]?.[0]??value;
}

export function itineraryText(description:string):string {
  if(/^Synthetic overnight stay at [^\n]+; no booking implied\.$/.test(description))
    return '在营地过夜，请另行确认营位预订。';
  if(description==='Uncommitted rest period at campsite; no travel time or activity availability inferred.')
    return '在营地自由安排，活动与交通安排仍需确认。';
  return description;
}
