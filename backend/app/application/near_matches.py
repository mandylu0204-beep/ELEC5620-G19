"""A-owned read model for saved exclusions; never supplies Agent candidates."""
import re

from ..contracts.dto import ConfirmedContext
from ..agents.rules.planning import SOFT_FEATURES, violations

FEATURES = {'toilets':'厕所','potable_water':'饮用水','showers':'淋浴','fire_allowed':'允许营火',
    'campfire':'允许营火','pets_allowed':'允许宠物','wheelchair_accessible':'轮椅通行',
    'vehicle_access':'车辆通行','public_transport_access':'公共交通通达'}
SEASONS = {'spring':'春季（9–11月）','summer':'夏季（12–2月）','autumn':'秋季（3–5月）','winter':'冬季（6–8月）','all':'全年'}

def money(cents):
    return '未知' if cents is None else f'AUD {cents // 100}.{cents % 100:02d}'

def problem(reason, camp, requirements, profile):
    expected, actual, suggestion = None, None, '核对这一条件后，调整需求并重新确认。'
    status = 'UNVERIFIED'
    field, title = 'other', '其他未满足条件'
    detail = reason
    if reason == 'Destination does not match.':
        field,title='destination','目的地'
        expected=requirements.destination;actual=camp.region if camp else '原地区未知'
        status='MISMATCH';detail='营地所在地区与已确认的目的地不同。'
        suggestion='选择目标地区的营地；如愿意更换地区，再修改目的地。'
    elif reason == 'Group capacity is insufficient or unknown.':
        field,title='profile.group_size','同行人数与营地容量'
        expected=f'{profile.group_size} 人';capacity=camp.max_group_size if camp else None
        actual=f'最多 {capacity} 人' if capacity is not None else '容量未知'
        status='MISMATCH' if capacity is not None else 'UNVERIFIED'
        detail=f'容量还差 {profile.group_size-capacity} 人。' if capacity is not None else '未提供足以容纳小组的容量信息。'
        suggestion=f'选择容量至少 {profile.group_size} 人的营地；仅在实际同行人数变化时更新露营资料。'
    elif reason == 'Trip season is unsupported or unknown.':
        field,title='start_date','行程季节'
        expected=f'{requirements.start_date} 至 {requirements.end_date}'
        seasons=camp.supported_seasons if camp else []
        actual='、'.join(SEASONS.get(s,s) for s in seasons) if seasons else '开放季节未知'
        status='MISMATCH' if seasons else 'UNVERIFIED';detail='这段行程未被已知支持季节完整覆盖。'
        suggestion='选择支持整个行程季节的营地，或在核对开放信息后调整日期。'
    elif reason == 'Campsite fee alone exceeds the confirmed group budget.':
        field,title='budget_cents','营地费用与小组预算'
        expected=f'小组总预算 {money(requirements.budget_cents)}'
        fee=camp.nightly_fee_cents if camp else None
        subtotal=fee*requirements.duration_nights if fee is not None else None
        actual=f'{requirements.duration_nights} 晚营地费 {money(subtotal)}'
        status='MISMATCH'
        detail=f'仅营地费已超预算 {money(subtotal-requirements.budget_cents)}，尚未加交通、食物、水及装备。' if subtotal is not None else '保存的筛选结果显示仅营地费已超预算；原报价目前无法核对。'
        suggestion=f'增加预算至至少 {money(subtotal)}（只含营地费），并另计其他开支；或减少晚数、比较更便宜的营地。' if subtotal is not None else '核对营地报价，增加预算、减少晚数或比较更便宜的营地。'
    else:
        feature=None
        match=re.fullmatch(r'Mandatory feature (.+) is unavailable or unknown\.',reason)
        if match:
            feature=match[1];field='mandatory_constraints';title='必须条件：'+FEATURES.get(feature,feature)
            expected='明确提供 '+FEATURES.get(feature,feature)
            feature='fire_allowed' if feature=='campfire' else feature
        elif reason == 'Vehicle access is unavailable or unknown.':
            field,title,feature,expected='profile.transport','汽车通达','vehicle_access','汽车可到达'
        elif reason == 'Public transport access is unavailable or unknown.':
            field,title,feature,expected='profile.transport','公共交通通达','public_transport_access','公共交通可到达'
        if feature:
            supplied=getattr(camp,feature,None) if camp else None
            actual='明确不提供' if supplied is False else '未提供可验证信息'
            status='MISMATCH' if supplied is False else 'UNVERIFIED'
            detail='当前营地不满足这项条件。' if supplied is False else '信息未知，不能当作已满足。'
            suggestion='若这项条件确实可选，可修改必须条件；否则选择明确满足条件的营地或补齐来源。'
            if feature=='fire_allowed':suggestion='选择明确允许营火的营地，或改为无营火行程；实际禁火限制不能由修改表单解除。'
            if field=='profile.transport':suggestion='选择实际交通方式可到达的营地；只有交通安排真正改变后再更新资料。'
            if feature=='wheelchair_accessible':suggestion='保留实际无障碍需求，选择已验证支持的营地；未知信息需核实。'
        elif reason.startswith('Accessible requirement '):
            field,title='profile.accessibility_requirements','无障碍需求'
            expected=reason.removeprefix('Accessible requirement ').removesuffix(' is unavailable or unverified.').strip("'")
            actual='不提供或尚未验证';detail='已保存的筛选结果未确认这项无障碍需求。'
            if camp:
                normalized=expected.casefold()
                unavailable=(normalized=='wheelchair access' and camp.wheelchair_accessible is False) or (
                    normalized=='wheelchair-accessible toilet' and (camp.wheelchair_accessible is False or camp.toilets is False)) or (
                    normalized=='step-free path' and camp.step_free_path is False)
                if unavailable:
                    status='MISMATCH';actual='明确不提供';detail='营地明确不满足这项无障碍需求。'
            suggestion='保留实际无障碍需求，选择明确支持的营地，或补充可验证设施信息。'
        elif reason == 'Walk-in-only access is not established.':
            field,title='mandatory_constraints','仅步行进入'
            expected='明确仅步行进入';actual='不符合或未知';detail='未确认营地只允许步行进入。'
            if camp and camp.vehicle_access is True:status='MISMATCH';actual='允许车辆通行'
            suggestion='核对通达方式；如仅步行不是必要条件，可以修改后重新确认。'
    return {'field':field,'title':title,'status':status,'expected':expected,'actual':actual,'detail':detail,'suggestion':suggestion,'original_reason':reason}

def guidance(data, dataset=None, *, metadata_note=None):
    recommendation=(data.get('recommendations') or {}).get('result')
    if not recommendation or recommendation['search_outcome']!='NO_MATCH' or not data.get('confirmed_context'):
        return None
    confirmed=ConfirmedContext.model_validate(data['confirmed_context'])
    req,profile=confirmed.requirements,confirmed.profile_snapshot
    camps={camp.campsite_id:camp for camp in dataset.campsites} if dataset else {}
    items=[]
    for excluded in recommendation['excluded_candidates']:
        camp=camps.get(excluded['campsite_id'])
        # Enrichment must agree with this run's saved reasons. New rules/data
        # cannot silently rewrite the meaning of an old recommendation.
        if camp and violations(camp,req,profile)!=excluded['reasons']:
            camp=None
        reasons=list(dict.fromkeys(excluded['reasons']))
        issues=[problem(reason,camp,req,profile) for reason in reasons]
        matches=[];uncertainties=[]
        if camp:
            for preference in req.preferences:
                normalized=preference.strip().casefold()
                feature=SOFT_FEATURES.get(normalized)
                if normalized=='quiet':
                    if camp.quiet_environment is True:matches.append('安静环境（合成资料）')
                    else:uncertainties.append('安静环境未获确认')
                elif feature and getattr(camp,feature) is True:matches.append(FEATURES.get(feature,preference))
                elif feature:uncertainties.append('偏好 '+FEATURES.get(feature,preference)+' 未获确认')
        fee=camp.nightly_fee_cents if camp else None
        subtotal=fee*req.duration_nights if fee is not None else None
        items.append({'campsite_id':excluded['campsite_id'],'name':camp.name if camp else excluded['campsite_id'],
            'region':camp.region if camp else None,'mismatch_count':sum(i['status']=='MISMATCH' for i in issues),
            'unverified_count':sum(i['status']=='UNVERIFIED' for i in issues),'issues':issues,'matched_preferences':matches,
            'uncertainties':uncertainties,'nightly_fee_cents':fee,'campsite_subtotal_cents':subtotal,
            'budget_excess_cents':max(0,subtotal-req.budget_cents) if subtotal is not None else None,
            'source_ref':camp.source_ref.model_dump(mode='json') if camp else None})
    items.sort(key=lambda item:(len(item['issues']),item['unverified_count'],item['budget_excess_cents'] is None,
        item['budget_excess_cents'] or 0,-len(item['matched_preferences']),item['nightly_fee_cents'] is None,
        item['nightly_fee_cents'] or 0,item['campsite_id']))
    return {'near_matches':[dict(item,rank=rank) for rank,item in enumerate(items[:3],1)],'excluded_count':len(items),
        'ranking':'先按需处理的筛选条件数从少到多；同分优先信息明确、已知预算缺口小、偏好匹配多、营地费用低的营地。未知金额不当作零；最终同分按营地编号排序。',
        'metadata_note':metadata_note,'scope':'仅供调整需求比较，均未满足全部筛选条件；没有生成行程，也未通过道路、天气、营火和物流评估。'}
