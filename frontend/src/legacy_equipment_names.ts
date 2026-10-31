// Display known old default labels only. Never infer category/capacity or mutate saved facts.
const aliases:Record<string,string[]>={"tent": ["\u5e10\u7bf7"], "groundsheet": ["\u5730\u5e03"], "tent_repair_kit": ["\u5e10\u7bf7\u4fee\u8865\u5de5\u5177"], "sleeping_bag": ["\u7761\u888b"], "sleeping_mat": ["\u7761\u57ab"], "warm_liner": ["\u4fdd\u6696\u5185\u886c"], "rain_jacket": ["\u96e8\u8863"], "warm_layers": ["\u4fdd\u6696\u8863\u7269"], "sun_hat": ["\u906e\u9633\u5e3d"], "windproof_outer_layer": ["\u9632\u98ce\u5916\u5957"], "camping_stove": ["\u9732\u8425\u7089\u5177"], "fuel_canister": ["\u71c3\u6599\u7f50"], "cooking_pot": ["\u708a\u5177"], "drinking_water": ["\u996e\u7528\u6c34"], "meal_supplies": ["\u9910\u98df"], "child_snacks": ["\u513f\u7ae5\u96f6\u98df"], "offline_map": ["\u79bb\u7ebf\u5730\u56fe"], "power_bank": ["\u5145\u7535\u5b9d"], "first_aid_kit": ["\u6025\u6551\u5305"], "torch": ["\u5934\u706f / \u624b\u7535"], "whistle": ["\u54e8\u5b50"], "emergency_contact_card": ["\u7d27\u6025\u8054\u7cfb\u5361"], "hand_sanitiser": ["\u6d17\u624b\u6db2"], "toilet_kit": ["\u536b\u751f\u7528\u54c1"], "vehicle": ["\u8f66\u8f86"], "transport_itinerary": ["\u4ea4\u901a\u8fde\u63a5\u8ba1\u5212"], "fire_free_meal_plan": ["\u65e0\u706b\u9910\u98df\u8ba1\u5212"], "water_container": ["\u50a8\u6c34\u5bb9\u5668"], "other": ["\u5176\u4ed6\u88c5\u5907"]};
const digits='\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d';
function oldNumber(n:number):string{
 if(n<10)return digits[n];
 return (n<20?'':digits[Math.floor(n/10)])+'\u5341'+(n%10?digits[n%10]:'');
}
export function legacyEquipmentName(key:string,name:string,englishBase:string):string{
 for(const base of Object.hasOwn(aliases,key)?aliases[key]:[]){
  if(name===base)return englishBase;
  if(!name.startsWith(base))continue;
  const suffix=name.slice(base.length);
  if(/^[1-9]\d*$/.test(suffix))return englishBase+' '+suffix;
  for(let n=1;n<100;n++)if(suffix===oldNumber(n))return englishBase+' '+n;
 }
 return name;
}
