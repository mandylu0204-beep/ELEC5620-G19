type Kind = 'preference' | 'constraint' | 'accessibility';
// Exact structured-field labels only. Free prose and unknown terms stay intact.
const vocabulary: Record<Kind, Record<string, string[]>> = {
  preference: {
    quiet:["Quiet", "\u5b89\u9759", "\u5b89\u9759\u7684\u73af\u5883", "Quiet surroundings"], 'ready-to-eat meals':["Ready-to-eat meals", "\u5373\u98df\u9910\u98df", "\u5373\u98df\u98df\u54c1", "\u65e0\u9700\u70f9\u996a\u7684\u9910\u98df", "Ready-to-eat food", "Meals requiring no cooking"],
    'self-catered meals':["Self-catered meals", "\u81ea\u884c\u70f9\u996a", "\u81ea\u5df1\u505a\u996d", "Cook own meals"], campfire:["Campfire", "\u8425\u706b"], toilets:["Toilets", "\u5395\u6240"],
    showers:["Showers", "\u6dcb\u6d74"], 'potable water':["Drinking-water facilities", "\u996e\u7528\u6c34\u8bbe\u65bd"], 'public transport':["Public transport", "\u516c\u5171\u4ea4\u901a"],
    'wheelchair accessible':["Wheelchair access", "\u8f6e\u6905\u901a\u884c"], pets:["Bring pets", "\u643a\u5e26\u5ba0\u7269"],
  },
  constraint: {
    toilets:["Toilets", "\u5395\u6240", "\u5fc5\u987b\u6709\u5395\u6240", "\u9700\u8981\u5395\u6240", "Must have toilets", "Toilets required"], showers:["Showers", "\u6dcb\u6d74", "\u5fc5\u987b\u6709\u6dcb\u6d74", "\u9700\u8981\u6dcb\u6d74", "Must have showers", "Need showers"],
    potable_water:["Drinking-water facilities", "\u996e\u7528\u6c34\u8bbe\u65bd", "\u9700\u8981\u996e\u7528\u6c34\u8bbe\u65bd", "Drinking-water facilities required"], wheelchair_accessible:["Wheelchair access", "\u8f6e\u6905\u901a\u884c", "\u9700\u8981\u8f6e\u6905\u901a\u884c", "Need wheelchair access"],
    fire_allowed:["Campfires allowed", "\u5141\u8bb8\u8425\u706b"], campfire:["Campfire", "\u8425\u706b"], no_fires:["No campfire", "\u4e0d\u751f\u706b", "\u4e0d\u4f7f\u7528\u8425\u706b", "\u7981\u6b62\u8425\u706b", "Campfires prohibited"],
    pets_allowed:["Pets allowed", "\u5141\u8bb8\u643a\u5e26\u5ba0\u7269"], vehicle_access:["Vehicle access", "\u8f66\u8f86\u53ef\u8fbe"],
    public_transport_access:["Public transport access", "\u516c\u5171\u4ea4\u901a\u53ef\u8fbe"], walk_in_only:["Walk-in access only", "\u4ec5\u53ef\u6b65\u884c\u8fdb\u5165"],
  },
  accessibility: {
    'step-free path':["Step-free path", "\u65e0\u53f0\u9636\u901a\u9053", "\u9700\u8981\u65e0\u53f0\u9636\u901a\u9053", "Need a step-free path"],
    'wheelchair access':["Wheelchair access", "\u8f6e\u6905\u901a\u884c", "\u9700\u8981\u8f6e\u6905\u901a\u884c"], 'wheelchair-accessible toilet':["Accessible toilet", "\u65e0\u969c\u788d\u5395\u6240", "\u9700\u8981\u65e0\u969c\u788d\u5395\u6240"],
  },
};

export function canonicalTerms(values:string[],kind:Kind):string[] {
  return values.map(value=>{
    const text=value.trim();
    return Object.entries(vocabulary[kind]).find(([key,labels])=>key===text.toLowerCase()||labels.some(label=>label.toLowerCase()===text.toLowerCase()))?.[0]??text;
  });
}

export function termLabel(value:string,kind:Kind):string {
  const key=canonicalTerms([value],kind)[0];
  return Object.hasOwn(vocabulary[kind],key)?vocabulary[kind][key][0]:value;
}

export function itineraryText(description:string):string {
  if(/^Synthetic overnight stay at [^\n]+; no booking implied\.$/.test(description))
    return 'Overnight campsite stay; confirm your campsite booking separately.';
  if(description==='Uncommitted rest period at campsite; no travel time or activity availability inferred.')
    return 'Free time at the campsite; activities and transport still need confirmation.';
  return description;
}
