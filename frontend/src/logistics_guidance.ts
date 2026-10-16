type Question = {field:string;question:string;reason:string};

export function logisticsQuestions(items:Question[]) {
  const messages=items.map(item=>{
    if(['meal_mode','gear_rule_input.meal_mode'].includes(item.field))return '请选择用餐方式：即食餐食或自行烹饪，再重新确认需求。';
    if(item.field==='transport.estimated_km')return '请在露营资料中填写整个行程的预计行车总公里数。';
    if(item.field==='cooking_method')return '请确认不依赖营火的烹饪安排，或改选无需烹饪的即食餐食。';
    return `${item.question} · ${item.reason}`;
  });
  return [...new Set(messages)];
}

export function needsMealChoice(items:Question[]) {
  return items.some(item=>['meal_mode','gear_rule_input.meal_mode'].includes(item.field));
}
