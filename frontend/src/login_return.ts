export function loginReturnPath(value:unknown,role:'CAMPER'|'FOUNDER'):string {
  const fallback=role==='FOUNDER'?'/review':'/plans';
  if(typeof value!=='string')return fallback;
  const route=role==='FOUNDER'
    ? /^\/review(?:\/[A-Za-z0-9_-]+)?(?:\?[^#\r\n]*)?$/
    : /^\/(?:profile|request|plans)(?:\/[A-Za-z0-9_-]+)*(?:\?[^#\r\n]*)?$/;
  return route.test(value)?value:fallback;
}
