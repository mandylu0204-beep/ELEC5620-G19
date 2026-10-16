import type { LogisticsIssue } from './logistics_issues';

export function logisticsDestinations(items:LogisticsIssue[]){
  const profile=items.find(item=>item.target==='PROFILE'&&item.action_url?.startsWith('/profile?'))?.action_url
    ??items.find(item=>item.alternate_action_url?.startsWith('/profile?'))?.alternate_action_url??null;
  const request=items.find(item=>item.target==='REQUEST'&&item.action_url?.startsWith('/request?'))?.action_url??null;
  return {profile,request,safety:items.some(item=>item.target==='SAFETY')};
}
