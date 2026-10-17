export function passwordChecks(password:string){
  const length=Array.from(password).length;
  return [
    {key:'length',label:'8–256 个字符',met:length>=8&&length<=256},
    {key:'upper',label:'至少一个大写英文字母（A–Z）',met:/[A-Z]/.test(password)},
    {key:'lower',label:'至少一个小写英文字母（a–z）',met:/[a-z]/.test(password)},
    {key:'digit',label:'至少一个数字（0–9）',met:/[0-9]/.test(password)},
    {key:'symbol',label:'至少一个半角特殊符号（如 ! @ #，空格不算）',met:/[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]/.test(password)},
  ];
}
