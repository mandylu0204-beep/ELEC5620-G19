"""Static package checks. This does not run CampMate, its Agents, or its database."""
import copy
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from runtime_inputs import ROOT, load_csv, load_json, request_agent_input, safety_agent_input, evaluate, estimate_cost, required_gear
from release_files import seal_release, verify_release

results = []
def check(name, condition, detail=''):
    results.append(dict(check=name, passed=bool(condition), detail=detail))

def unique(rows, key):
    ids = [r[key] for r in rows]
    return len(ids)==len(set(ids)) and all(ids)

def scan_for_oracle(value):
    if isinstance(value, dict):
        return any(k.startswith('expected_') or k in ('missing_fields','severity','confidence') or scan_for_oracle(v) for k,v in value.items())
    if isinstance(value,list): return any(scan_for_oracle(x) for x in value)
    return False

BOOL_CAMP = ('booking_required','vehicle_access','public_transport_access','toilets','potable_water','showers','fire_allowed','pets_allowed','wheelchair_accessible','demo_only','walk_in_only','quiet_environment','step_free_path')
camps = load_csv('data/synthetic_campsites.csv',BOOL_CAMP,('max_group_size',),('latitude','longitude','nightly_fee_aud'),('supported_seasons','facilities','mandatory_restrictions','risk_tags'))
gear = load_csv('data/synthetic_gear_rules.csv',('essential','substitute_allowed','demo_only'),json_fields=('trigger_json','quantity_json'))
costs = load_csv('data/synthetic_cost_reference.csv',('demo_only',),number_fields=('low_aud','typical_aud','high_aud'),json_fields=('quantity_json',))
tests = load_csv('tests/synthetic_agent_test_cases.csv',('demo_only',))
profiles = load_json('data/synthetic_profiles.json')
requests = load_json('data/synthetic_requests.json')
safety = load_json('data/synthetic_safety_scenarios.json')
fixtures = load_json('tests/synthetic_test_fixtures.json')
oracles = load_json('tests/synthetic_oracles.json')
manifest = load_json('manifest.json')
P={x['profile_id']:x for x in profiles};R={x['request_id']:x for x in requests};S={x['safety_case_id']:x for x in safety};C={x['campsite_id']:x for x in camps};F={x['fixture_id']:x for x in fixtures}
for rows,key in [(camps,'campsite_id'),(gear,'gear_rule_id'),(costs,'cost_id'),(profiles,'profile_id'),(requests,'request_id'),(safety,'safety_case_id'),(tests,'test_id'),(fixtures,'fixture_id')]:
    check('Unique/nonempty '+key,unique(rows,key))

allrows=camps+gear+costs+profiles+requests+safety+tests+fixtures+oracles['request_oracles']+oracles['safety_oracles']+oracles['test_oracles']
check('Synthetic provenance on every data/test/oracle record',all(x.get('source_type')=='SYNTHETIC' and x.get('source_name')=='CampMate Synthetic Demo Dataset v2' and x.get('source_date')=='2026-10-07' and x.get('demo_only') is True and bool(x.get('notes')) for x in allrows))
check('Fixed manifest clock',manifest['default_demo_clock']=='2026-10-09T10:00:00+11:00')
check('Manifest counts match files',manifest['counts']==dict(campsites=len(camps),gear_rules=len(gear),cost_references=len(costs),profiles=len(profiles),requests=len(requests),safety_scenarios=len(safety),acceptance_specs=len(tests)))
check('Cost ranges ordered',all(0<=c['low_aud']<=c['typical_aud']<=c['high_aud'] for c in costs))
check('CSV false values converted to false',C['demo-fern-walk']['vehicle_access'] is False and isinstance(camps[0]['demo_only'],bool))
check('Profile child/adult counts reconcile',all(p['children_count']+p['adult_count']==p['group_size'] and p['has_children']==(p['children_count']>0) for p in profiles))
check('Unknown tent capacity/torch count preserved',next(e for e in P['profile-d']['normalized_equipment'] if e['item_key']=='tent')['capacity_persons'] is None and next(e for e in P['profile-a']['normalized_equipment'] if e['item_key']=='torch')['quantity'] is None)
check('Unconfirmed candidates do not imply confirmed equipment',all(not e['confirmed'] for p in profiles for e in p['normalized_equipment']))
check('Request ownership and snapshots',all(r['profile_id'] in P and r['profile_snapshot']==P[r['profile_id']] for r in requests))
check('No business request starts confirmed',all(r['confirmed'] is False for r in requests))
check('Two nights derive three days',R['request-01']['duration_nights']==2 and R['request-01']['duration_days']==3 and R['request-01']['end_date']=='2026-10-22')
check('All canonical durations/end dates reconcile',all((r['duration_days']==r['duration_nights']+1 if r['duration_nights'] is not None else r['duration_days'] is None) and (r['end_date']==str(date.fromisoformat(r['start_date'])+__import__('datetime').timedelta(days=r['duration_nights'])) if r['start_date'] and r['duration_nights'] else r['end_date'] is None) for r in requests))
ro={o['request_id']:o for o in oracles['request_oracles']}
check('request-03 missing date AND duration',ro['request-03']['missing_fields']==['start_date','duration_nights'] and R['request-03']['duration_nights'] is None)
check('Missing budget differs from invalid budget',R['request-04']['budget_aud'] is None and R['request-05']['budget_aud']==-50 and ro['request-05']['invalid_fields']==['budget_aud'])

runtime_r=[request_agent_input(r) for r in requests];runtime_s=[safety_agent_input(s) for s in safety]
check('Business records contain no oracle labels',not scan_for_oracle(profiles+requests+safety))
check('Runtime inputs contain no oracle labels',not scan_for_oracle(runtime_r+runtime_s))
check('Runtime files match allowlist adapters',runtime_r==load_json('data/runtime_requests.json') and runtime_s==load_json('data/runtime_safety_evidence.json'))
contaminated=copy.deepcopy(R['request-01']);contaminated.update(expected_request_status='CONFIRMED',missing_fields=['invented'],duration_nights=99,confirmed=True)
dirty=copy.deepcopy(S['safety-02']);dirty.update(expected_outcome='PASSED',severity='LOW',confidence='HIGH',expected_actions=['finalize'])
check('Oracle/candidate contamination cannot change Agent inputs',request_agent_input(contaminated)==request_agent_input(R['request-01']) and safety_agent_input(dirty)==safety_agent_input(S['safety-02']))

mapping={**{i:'FR-02' for i in [1,2,3,5,6]},4:'FR-01;FR-02',**{i:'FR-03' for i in range(7,11)},11:'FR-02;FR-04',12:'FR-04;FR-10',**{i:'FR-05' for i in range(13,16)},**{i:'FR-06' for i in range(16,19)},**{i:'FR-07;FR-08' for i in [19,20,21,22,24]},23:'FR-04;FR-07;FR-08',25:'FR-08',26:'FR-09',27:'FR-09;FR-10',28:'FR-04;FR-09;FR-10',29:'FR-10',30:'FR-10'}
check('Original 30 tests semantically remapped to Stage 1',all(t['requirement_id']==mapping[int(t['test_id'][5:])] for t in tests[:30]))
check('FR-01 to FR-10 specification traceability',set(f'FR-{i:02}' for i in range(1,11)).issubset(set(k for t in tests for k in t['requirement_id'].split(';'))),'Traceability only; execution/coverage not claimed.')
check('All acceptance specifications explicitly NOT_RUN',all(t['execution_status']=='NOT_RUN' for t in tests) and manifest['application_tests_executed'] is False)
check('Every test has fixture and oracle',{t['test_id'] for t in tests}=={f['test_id'] for f in fixtures}=={o['test_id'] for o in oracles['test_oracles']})

badrefs=[];badsemantics=[];badfixture=[];badtime=[]
for t in tests:
    for key,index in [('profile_id',P),('request_id',R),('campsite_id',C),('safety_case_id',S)]:
        if t[key] and t[key] not in index:badrefs.append(t['test_id']+':'+key)
    f=F[t['fixture_id']]
    if t['request_id'] and R[t['request_id']]['profile_id']!=t['profile_id']:badsemantics.append(t['test_id']+':owner')
    if t['safety_case_id'] and S[t['safety_case_id']]['campsite_id']!=t['campsite_id']:badsemantics.append(t['test_id']+':campsite')
    if t['request_id'] and t['safety_case_id']:
        r,s=R[t['request_id']],S[t['safety_case_id']]
        if t['test_mode']!='INTEGRATION' or not(s['valid_from']<=r['start_date'] and s['valid_until']>=r['end_date']):badsemantics.append(t['test_id']+':trip_range')
    setup=f['setup']
    seeded={p['plan_version_id'] for p in setup['plans']}
    creates={a['parameters'][key] for a in f['actions'] for key in ['new_plan_version_id','plan_version_id'] if key in a['parameters'] and a['action'] in ['REVISE_PLAN','GENERATE_PLAN']}
    if t['plan_version_id'] and t['plan_version_id'] not in seeded|creates:badfixture.append(t['test_id']+':plan')
    if setup['latest_version_id'] and setup['latest_version_id'] not in seeded:badfixture.append(t['test_id']+':latest')
    for p in setup['plans']:
        if p['predecessor_id'] and p['predecessor_id'] not in seeded:badfixture.append(t['test_id']+':predecessor')
        for key,records,idkey in [('assessment_refs',setup['assessments'],'assessment_id'),('review_refs',setup['reviews'],'review_id')]:
            ids={x[idkey] for x in records if x['plan_version_id']==p['plan_version_id']}
            if not set(p[key]).issubset(ids):badfixture.append(t['test_id']+':'+key)
    if t['safety_case_id']:
        s=S[t['safety_case_id']]
        clock=datetime.fromisoformat(f['demo_clock'])
        for a in f['actions']:
            if a['action']=='ADVANCE_DEMO_CLOCK':clock=datetime.fromisoformat(a['parameters']['value'])
        for key in ['weather','fire','road_access']:
            e=s[key]
            if e['observed_at'] and datetime.fromisoformat(e['observed_at'])>clock:badtime.append(t['test_id']+':future_observation')
    if not f['actor']['authenticated'] or not f['actor']['role'] or not f['actions']:badfixture.append(t['test_id']+':actor/actions')
check('All nonempty cross-file IDs resolve',not badrefs,str(badrefs))
check('Test user/campsite/trip scope consistency',not badsemantics,str(badsemantics))
check('Plan versions, links, actors, actions and isolated fixtures',not badfixture and all(a.get('actor',f['actor'])['authenticated'] and a.get('actor',f['actor'])['role'] for f in fixtures for a in f['actions']),str(badfixture))
check('Observations do not come from future fixture clocks',not badtime,str(badtime))
check('Known mismatched safety references removed',all(not t['safety_case_id'] for t in tests if t['test_id'] in ['test-09','test-10','test-12','test-27','test-28']))
check('Impossible constraints and reversed dates are explicit',F['fixture-test-08']['setup']['requests'][0]['user_supplements']['mandatory_constraints']=={'wheelchair_accessible':True,'walk_in_only':True,'fire_allowed':False} and F['fixture-test-11']['actions'][0]['parameters']['end_date']=='2026-10-19')
check('Impossible accessible/walk-in/no-fire filter yields no record',not any(c['wheelchair_accessible'] and c['walk_in_only'] and c['fire_allowed'] is False for c in camps))

so={o['safety_case_id']:o for o in oracles['safety_oracles']}
badpolicy=[]
for s in safety:
    oracle=so[s['safety_case_id']]
    uncertain=any(s[k]['data_status']!='AVAILABLE' for k in ['weather','fire','road_access'])
    blocked=bool(s['mandatory_blockers']) or s['road_access']['status']=='CLOSED' or not s['evidence_facts']['campsite_open']
    if (uncertain or blocked) and oracle['expected_outcome']=='PASSED':badpolicy.append(s['safety_case_id'])
    if (uncertain or blocked or oracle['expected_severity'] in ['HIGH','CRITICAL']) and oracle['finalization_eligible']:badpolicy.append(s['safety_case_id']+':eligible')
    if oracle['expected_severity'] in ['HIGH','CRITICAL'] and not oracle['requires_human_review']:badpolicy.append(s['safety_case_id']+':escalation')
check('Oracle policy prevents unsafe automatic eligibility',not badpolicy,str(badpolicy)+'; validates expected outputs only, not application enforcement.')
check('Fixable blocker and escalation modeled independently',so['safety-05']['expected_outcome']=='REVISION' and so['safety-05']['requires_human_review'] and not so['safety-05']['finalization_eligible'])
check('Approval blocker case isolates FINALISATION_BLOCKED cause and owner actor',next(o for o in oracles['test_oracles'] if o['test_id']=='test-43')['assertions']=={'result':'FINALISATION_BLOCKED','final_record_count':0,'finalization_eligible':False,'blocker_codes':['campfire at no-fire site'],'review_actor':'founder-demo','finalize_actor':'camper-a'} and [a.get('actor',{}).get('role') for a in F['fixture-test-43']['actions']]==['FOUNDER','CAMPER'] and len(F['fixture-test-43']['setup']['assessments'])==3)
check('Missing safety evidence case isolates FINALISATION_BLOCKED cause',next(o for o in oracles['test_oracles'] if o['test_id']=='test-56')['assertions']['blocker_codes']==['SAFETY_EVIDENCE_INCOMPLETE'] and len(F['fixture-test-56']['setup']['assessments'])==3 and F['fixture-test-56']['setup']['assessments'][-1]['evidence_complete'] is False)
check('Target conditions have paired resolving controls',F['fixture-test-57']['setup']['plans'][0]['mandatory_blockers']==[] and F['fixture-test-58']['setup']['assessments'][-1]['evidence_complete'] is True and all(next(o for o in oracles['test_oracles'] if o['test_id']==tid)['assertions']['result']=='FINALIZED' for tid in ['test-57','test-58']))
check('High heat escalates for human review',so['safety-09']['expected_outcome']=='REVIEW' and so['safety-09']['requires_human_review'])
check('Stale evidence has computable expiry',S['safety-03']['weather']['valid_until']<S['safety-03']['scenario_date'])
check('Missing evidence is null, not fabricated weather',S['safety-02']['weather']['observed_at'] is None and S['safety-02']['evidence_facts']['temperature_max_c'] is None)
check('Context copies retain source and dates',S['safety-11']['template_source_id']=='safety-01' and S['safety-12']['template_source_id']=='safety-05' and S['safety-05']['scenario_date']=='2026-10-24')

ctx={'group_size':2,'duration_nights':2,'duration_days':3,'adult_count':2,'children_count':0,'tent_count':1,'tent_capacity_persons':2,'sleeping_bag_count':2,'stove_count':0,'potable_water':True,'toilets':True,'remote':False,'vehicle_count':1,'temperature_min_c':5,'temperature_max_c':20,'forecast_rain_mm':0,'wind_kph':10,'fire_prohibited':False,'meal_mode':'READY_TO_EAT','experience_level':'BEGINNER','transport_type':'CAR'}
req,missing=required_gear(gear,ctx)
check('Executable gear rules evaluate without missing inputs',not missing)
check('Gear overlap does not double-count tents/bags',req[('tent','person_capacity')]==2 and req[('sleeping_bag','item')]==2)
selfcatered,missing=required_gear(gear,dict(ctx,meal_mode='SELF_CATERED',fire_prohibited=True))
ready,ready_missing=required_gear(gear,dict(ctx,meal_mode='READY_TO_EAT',fire_prohibited=True))
check('Self-catered fire-ban requires stove and pot',not missing and selfcatered[('camping_stove','item')]==1 and selfcatered[('cooking_pot','item')]==1)
check('Ready-to-eat mode does not require stove or pot',not ready_missing and ('camping_stove','item') not in ready and ('cooking_pot','item') not in ready)
check('Potable-site water uses 3 days',req[('drinking_water','litre')]==12)
dry=dict(ctx,potable_water=False);reqdry,_=required_gear(gear,dry)
check('No-water site includes emergency day',reqdry[('drinking_water','litre')]==16)
value,missing=evaluate({'mul':[{'var':'vehicle_count'},12]}, {'vehicle_count':None})
check('Missing expression input never becomes numeric zero',value is None and missing=={'vehicle_count'})
zeroctx={k:0 for k in ['hire_tent_count','hire_sleeping_bag_count','hire_stove_count','purchase_first_aid_count','purchase_torch_count','purchase_rain_jacket_count','hire_sleeping_mat_count','purchase_power_bank_count','purchase_map_count']}
budgetctx=dict(ctx,**zeroctx,estimated_total_vehicle_km=100,water_equivalent_person_days=6)
calculated=estimate_cost(costs,C['demo-pine-camp'],budgetctx)
check('Success fixture arithmetic independently reconciles',calculated['total_aud']==261 and not calculated['missing_inputs'],json.dumps(calculated))
check('Food alternatives not double-charged',len([x for x in calculated['lines'] if x['cost_id'] in ['cost-04','cost-14']])==1)
half_cent=estimate_cost(costs,C['demo-pine-camp'],dict(budgetctx,estimated_total_vehicle_km=Decimal('3.5'),transport_type='CAR'))
transport_line=next(x for x in half_cent['lines'] if x['cost_id']=='cost-02')
check('Half-cent money rounds per line using HALF_UP',transport_line['amount_cents']==123 and half_cent['total_cents'] is not None)
check('Water cost uses equivalent person-days, not litres',next(x for x in calculated['lines'] if x['cost_id']=='cost-05')['amount_aud']==36)
budgetmissing=dict(budgetctx,vehicle_count=None,estimated_total_vehicle_km=None)
partial=estimate_cost(costs,C['demo-pine-camp'],budgetmissing)
check('Missing distance/vehicle gives incomplete estimate',partial['total_aud'] is None and partial['missing_inputs']==['estimated_total_vehicle_km','vehicle_count'])
check('test-17 campsite subtotal already exceeds budget',C['demo-lake-meadow']['nightly_fee_aud']*R['request-08']['duration_nights']==110>R['request-08']['budget_aud'])
check('Success fixture uses one fixed clock and orders confirmation/all checks/save/read', F['fixture-test-34']['demo_clock']=='2026-11-06T08:00:00+11:00' and [a['action'] for a in F['fixture-test-34']['actions']]==['SUBMIT_REQUEST','ADD_USER_SUPPLEMENT','CONFIRM_REQUEST','RECOMMEND_CAMPSITES','GENERATE_PLAN','ASSESS_GEAR','ASSESS_LOGISTICS','ASSESS_SAFETY','FINALIZE_PLAN','GET_FINAL_PLAN'])

# Derive a second calculation from the actual fixture records, not hardcoded totals.
sf=F['fixture-test-34'];sr=sf['setup']['requests'][0];sp=sr['profile_snapshot']
inventory=next(a['parameters']['normalized_equipment'] for a in sf['actions'] if a['action']=='ADD_USER_SUPPLEMENT')
supplies={x['item_key']:x for x in inventory}
evidence=S['safety-11']['evidence_facts']
actualctx=dict(ctx,group_size=sp['group_size'],adult_count=sp['adult_count'],children_count=sp['children_count'],duration_days=sr['duration_days'],duration_nights=sr['duration_nights'],vehicle_count=sr['user_supplements']['vehicle_count'],meal_mode=sr['user_supplements']['meal_mode'],tent_count=supplies['tent']['quantity'],tent_capacity_persons=supplies['tent']['quantity']*supplies['tent']['capacity_persons'],sleeping_bag_count=supplies['sleeping_bag']['quantity'],**{k:evidence[k] for k in ['temperature_min_c','temperature_max_c','forecast_rain_mm','wind_kph']})
actualreq,actualmissing=required_gear(gear,actualctx)
shortages=[]
for (key,unit),quantity in actualreq.items():
    owned=actualctx['tent_capacity_persons'] if unit=='person_capacity' else supplies.get(key,{}).get('quantity',0)
    if owned<quantity:shortages.append(key)
actualcost=estimate_cost(costs,C['demo-pine-camp'],dict(actualctx,**zeroctx,estimated_total_vehicle_km=sr['user_supplements']['estimated_total_vehicle_km'],water_equivalent_person_days=supplies['drinking_water']['quantity']/2))
successoracle=next(x['assertions'] for x in oracles['test_oracles'] if x['test_id']=='test-34')
check('Actual success fixture supplies satisfy every triggered rule',not shortages and not actualmissing,str(shortages+actualmissing))
check('Actual fixture-derived total matches isolated oracle',actualcost['total_aud']==successoracle['total_typical_aud']==261 and not actualcost['missing_inputs'])
check('Success request starts unconfirmed with explicit priced inputs',sr['confirmed'] is False and all(x['confirmed'] for x in inventory) and actualcost['total_aud']<=sr['budget_aud'])

validplan={'DRAFT','EVALUATING','NEEDS_REVISION','AWAITING_REVIEW','READY_TO_FINALIZE','FINALIZED','REJECTED','BLOCKED'}
check('Fixtures use defined PlanVersion status enum',all(p['status'] in validplan for f in fixtures for p in f['setup']['plans']))
check('Safety oracle enums are distinct and controlled',all(o['expected_outcome'] in {'PASSED','REVIEW','REVISION','BLOCKED'} and o['expected_severity'] in {'LOW','MEDIUM','HIGH','CRITICAL'} and o['expected_confidence'] in {'LOW','MEDIUM','HIGH'} for o in oracles['safety_oracles']))
check('Evidence status and source date formats',all(s[k]['data_status'] in {'AVAILABLE','MISSING','STALE','CONFLICTING'} and (s[k]['source_date']=='unknown' or re.fullmatch(r'\d{4}-\d{2}-\d{2}',s[k]['source_date'])) for s in safety for k in ['weather','fire','road_access']))

# Apply the documented JSON Schema subset without external packages.
def schema_errors(value,schema,path='$'):
    errors=[]
    if 'anyOf' in schema:
        return [] if any(not schema_errors(value,s,path) for s in schema['anyOf']) else [path+': no matching type']
    typename='null' if value is None else 'boolean' if isinstance(value,bool) else 'integer' if isinstance(value,int) else 'number' if isinstance(value,(float,Decimal)) else 'string' if isinstance(value,str) else 'array' if isinstance(value,list) else 'object'
    if 'type' in schema and typename!=schema['type'] and not (schema['type']=='number' and typename=='integer'):return [path+': wrong type']
    if 'enum' in schema and value not in schema['enum']:errors.append(path+': enum')
    if isinstance(value,dict):
        for key in schema.get('required',[]):
            if key not in value:errors.append(path+': missing '+key)
        properties=schema.get('properties',{})
        if schema.get('additionalProperties') is False:
            errors += [path+': extra '+k for k in value if k not in properties]
        for k,s in properties.items():
            if k in value:errors+=schema_errors(value[k],s,path+'.'+k)
    if isinstance(value,list):
        for i,v in enumerate(value):errors+=schema_errors(v,schema.get('items',{}),path+f'[{i}]')
    return errors

errors=[]
for schemafile in sorted((ROOT/'schemas').glob('*.json')):
    schema=json.loads(schemafile.read_text(encoding='utf-8'))
    data=load_json(schema['x-data-file'])
    errors+=schema_errors(data,schema,schema['x-data-file'])
check('JSON record schemas validate complete files',bool(list((ROOT/'schemas').glob('*.json'))) and not errors,str(errors[:20]))

bad=verify_release(ROOT)
check('Release manifest checksums',not bad,str(bad))

summary={'validation_date':date.today().isoformat(),'kind':'STATIC_DATA_AND_IMPORT_ADAPTER_CHECKS','passed':sum(r['passed'] for r in results),'failed':sum(not r['passed'] for r in results),'acceptance_specs':len(tests),'application_tests_executed':False,'checks':results}
if '--write-report' in sys.argv:
    (ROOT/'tests/static_validation_results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n', encoding='utf-8', newline='\n')
    table='\n'.join(f"| {r['check']} | {'PASS' if r['passed'] else 'FAIL'} |" for r in results)
    report=f'''# CampMate v2 静态验证报告

验证日期：{summary['validation_date']}。共 {len(results)} 项检查，{summary['passed']} 项通过，{summary['failed']} 项失败。

业务数据：10 个营地、30 条装备规则、16 条费用参考、5 个资料、13 个请求、{len(safety)} 个安全场景。
测试规格：{len(tests)} 条，每条都有独立 fixture、身份、动作与预期，全部为 NOT_RUN。

## 验证范围

本次执行 JSON/CSV 解析、唯一性、类型转换、来源标记、FR 追踪、身份/营地/日期语义、fixture 对象与版本引用、场景有效期、输入隔离以及示例装备/费用公式计算。
成功 fixture 的典型费用为 AUD 261；这是输入与预期的算术复核，不是 Agent 运行结果。
request-08 在 demo-lake-meadow 的两晚营地费为 AUD 110，已超过 AUD 50 预算。

## 尚未验证

没有运行 React/FastAPI、三个业务 Agent、数据库、身份认证或完整应用测试。
审批、阻止最终化、事务回滚、重试、资料 snapshot、适配器替换及干净环境启动目前均为待执行验收规格。
test-17、test-19、test-21 仍是组件级规格，不等同于完整低成本重规划、缺失证据或封路行程集成演示；应用接线后仍需补齐这些场景的端到端步骤。
FR 编号与正式 Stage 1 语义已对齐；这不等于需求实现已覆盖或通过。
A/B 仍需采用 docs/integration_contract.md 中的 v2 接口及路由约定。

## 检查结果

| 静态检查 | 结果 |
| --- | --- |
{table}

完整机器可读结果见 tests/static_validation_results.json。
'''
    (ROOT/'FINAL_VALIDATION_REPORT.md').write_text(report, encoding='utf-8', newline='\n')
    if summary['failed'] == 0:
        # The prior seal was valid. Only the generated report bytes changed;
        # record them together so --write-report does not invalidate the release.
        seal_release(ROOT)
        if verify_release(ROOT):
            raise RuntimeError('Generated release reports failed seal verification')
print(json.dumps({k:v for k,v in summary.items() if k!='checks'},ensure_ascii=False))
for r in results:
    if not r['passed']:print('FAIL:',r['check'],r['detail'])
sys.exit(1 if summary['failed'] else 0)
