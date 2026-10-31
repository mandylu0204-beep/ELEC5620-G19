export function passwordChecks(password:string){
  const length=Array.from(password).length;
  return [
    {key:'length',label:'At least 8 characters',met:length>=8&&length<=256},
    {key:'upper',label:'At least one uppercase English letter (A–Z)',met:/[A-Z]/.test(password)},
    {key:'lower',label:'At least one lowercase English letter (a–z)',met:/[a-z]/.test(password)},
    {key:'digit',label:'At least one digit (0–9)',met:/[0-9]/.test(password)},
    {key:'symbol',label:'At least one ASCII special character (such as ! @ #, ; spaces do not count)',met:/[\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]/.test(password)},
  ];
}
