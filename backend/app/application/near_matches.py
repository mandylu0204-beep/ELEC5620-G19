"""A-owned read model for saved exclusions; never supplies Agent candidates."""
import re

from ..contracts.dto import ConfirmedContext
from ..agents.rules.planning import SOFT_FEATURES, violations

FEATURES = {'toilets':'Toilets','potable_water':'Drinking water','showers':'Showers','fire_allowed':'Campfires allowed',
    'campfire':'Campfires allowed','pets_allowed':'Pets allowed','wheelchair_accessible':'Wheelchair access',
    'vehicle_access':'Vehicle access','public_transport_access':'Public transport access'}
SEASONS = {'spring':'Spring (September–November)','summer':'Summer (December–February)','autumn':'Autumn (March–May)','winter':'Winter (June–August)','all':'Year-round'}

def money(cents):
    return 'Unknown' if cents is None else f'AUD {cents // 100}.{cents % 100:02d}'

def problem(reason, camp, requirements, profile):
    expected, actual, suggestion = None, None, 'Review this condition, adjust requirements and reconfirm.'
    status = 'UNVERIFIED'
    field, title = 'other', 'Other unmet conditions'
    detail = reason
    if reason == 'Destination does not match.':
        field,title='destination','Destination'
        expected=requirements.destination;actual=camp.region if camp else 'Original region unknown'
        status='MISMATCH';detail='Campsite region differs from the confirmed destination.'
        suggestion='Choose a campsite in the target region. Change the destination only if you agree to change region.'
    elif reason == 'Group capacity is insufficient or unknown.':
        field,title='profile.group_size','Group size and campsite capacity'
        expected=f'{profile.group_size} people';capacity=camp.max_group_size if camp else None
        actual=f'Up to  {capacity} people' if capacity is not None else 'Capacity unknown'
        status='MISMATCH' if capacity is not None else 'UNVERIFIED'
        detail=f'Capacity shortfall:  {profile.group_size-capacity} people.' if capacity is not None else 'No information establishes capacity for the whole group.'
        suggestion=f'Choose a campsite for at least  {profile.group_size}  people. Update your profile only if actual group size changes.'
    elif reason == 'Trip season is unsupported or unknown.':
        field,title='start_date','Trip season'
        expected=f'{requirements.start_date} to {requirements.end_date}'
        seasons=camp.supported_seasons if camp else []
        actual=', '.join(SEASONS.get(s,s) for s in seasons) if seasons else 'Opening season unknown'
        status='MISMATCH' if seasons else 'UNVERIFIED';detail='Known supported seasons do not cover the entire trip.'
        suggestion='Choose a campsite supporting the whole trip season, or verify opening information and change dates.'
    elif reason == 'Campsite fee alone exceeds the confirmed group budget.':
        field,title='budget_cents','Campsite fees and group budget'
        expected=f'Total group budget {money(requirements.budget_cents)}'
        fee=camp.nightly_fee_cents if camp else None
        subtotal=fee*requirements.duration_nights if fee is not None else None
        actual=f'{requirements.duration_nights} -night campsite fees {money(subtotal)}'
        status='MISMATCH'
        detail=f'Campsite fees alone exceed budget {money(subtotal-requirements.budget_cents)}, Transport, food, water and equipment are additional.' if subtotal is not None else 'Saved filtering shows campsite fees alone exceed budget. The original quote cannot currently be verified.'
        suggestion=f'Increase the budget to at least  {money(subtotal)}( (campsite fees only), with other costs additional; or reduce nights or compare cheaper campsites.' if subtotal is not None else 'Check campsite prices, increase the budget, reduce nights or compare cheaper campsites.'
    else:
        feature=None
        match=re.fullmatch(r'Mandatory feature (.+) is unavailable or unknown\.',reason)
        if match:
            feature=match[1];field='mandatory_constraints';title='Required condition:'+FEATURES.get(feature,feature)
            expected='Explicitly provided '+FEATURES.get(feature,feature)
            feature='fire_allowed' if feature=='campfire' else feature
        elif reason == 'Vehicle access is unavailable or unknown.':
            field,title,feature,expected='profile.transport','Car access','vehicle_access','Accessible by car'
        elif reason == 'Public transport access is unavailable or unknown.':
            field,title,feature,expected='profile.transport','Public transport access','public_transport_access','Accessible by public transport'
        if feature:
            supplied=getattr(camp,feature,None) if camp else None
            actual='Explicitly not provided' if supplied is False else 'No verifiable information provided'
            status='MISMATCH' if supplied is False else 'UNVERIFIED'
            detail='This campsite does not meet this condition.' if supplied is False else 'Unknown information cannot be treated as a match.'
            suggestion='If truly optional, change the required condition. Otherwise choose a verified matching campsite or obtain sources.'
            if feature=='fire_allowed':suggestion='Choose a campsite explicitly allowing campfires, or plan without a campfire. Editing a form cannot override actual fire restrictions.'
            if field=='profile.transport':suggestion='Choose a campsite accessible by your actual transport. Update your profile only after arrangements really change.'
            if feature=='wheelchair_accessible':suggestion='Keep actual accessibility needs and choose a verified supported campsite. Unknown information needs verification.'
        elif reason.startswith('Accessible requirement '):
            field,title='profile.accessibility_requirements','Accessibility requirements'
            expected=reason.removeprefix('Accessible requirement ').removesuffix(' is unavailable or unverified.').strip("'")
            actual='Unavailable or unverified';detail='Saved filtering did not confirm this accessibility requirement.'
            if camp:
                normalized=expected.casefold()
                unavailable=(normalized=='wheelchair access' and camp.wheelchair_accessible is False) or (
                    normalized=='wheelchair-accessible toilet' and (camp.wheelchair_accessible is False or camp.toilets is False)) or (
                    normalized=='step-free path' and camp.step_free_path is False)
                if unavailable:
                    status='MISMATCH';actual='Explicitly not provided';detail='The campsite explicitly does not meet this accessibility requirement.'
            suggestion='Keep actual accessibility needs. Choose an explicitly supported campsite or obtain verifiable facility information.'
        elif reason == 'Walk-in-only access is not established.':
            field,title='mandatory_constraints','Walk-in only'
            expected='Explicitly walk-in only';actual='Does not match or unknown';detail='Walk-in-only access is unconfirmed.'
            if camp and camp.vehicle_access is True:status='MISMATCH';actual='Vehicle access permitted'
            suggestion='Verify access. If walk-in-only is not required, change it and reconfirm.'
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
                    if camp.quiet_environment is True:matches.append('Quiet environment (synthetic data)')
                    else:uncertainties.append('Quiet environment unconfirmed')
                elif feature and getattr(camp,feature) is True:matches.append(FEATURES.get(feature,preference))
                elif feature:uncertainties.append('Preferences '+FEATURES.get(feature,preference)+' Unconfirmed')
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
        'ranking':'Ranked by fewest conditions to address, then clearer information, smaller known budget gap, more preference matches and lower campsite fees. Unknown amounts are not zero. Final ties use campsite ID.',
        'metadata_note':metadata_note,'scope':'For requirement-adjustment comparison only. None meet all filters. No itinerary was generated or road, weather, fire and logistics assessment passed.'}
