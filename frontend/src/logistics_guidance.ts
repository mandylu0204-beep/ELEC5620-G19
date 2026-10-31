type Question = {field:string;question:string;reason:string};

export function logisticsQuestions(items:Question[]) {
  const messages=items.map(item=>{
    if(['meal_mode','gear_rule_input.meal_mode'].includes(item.field))return 'Select ready-to-eat meals or self-catering, then reconfirm the request.';
    if(item.field==='transport.estimated_km')return 'Enter the estimated total driving distance for the whole trip in your camping profile.';
    if(item.field==='cooking_method')return 'Confirm cooking arrangements that do not rely on a campfire, or select ready-to-eat meals.';
    return `${item.question} · ${item.reason}`;
  });
  return [...new Set(messages)];
}

export function needsMealChoice(items:Question[]) {
  return items.some(item=>['meal_mode','gear_rule_input.meal_mode'].includes(item.field));
}
