"""Independent display fixtures. No B Agent, repaired demo data, or workflow runner."""
import asyncio
from datetime import datetime, timezone

from app.contracts.dto import ConfirmedContext, ConfirmedRequirements, DatasetContext, DemoContext, ProfileSnapshot, ItineraryResult, LogisticsResult, SafetyResult, RecommendCampsitesResult
from app.contracts.errors import ContractError


NOTICE = '独立 A-06 展示测试夹具；不是 B Agent 输出或真实业务场景。'


def call(coroutine):
    return asyncio.run(coroutine)


def create(repo, user, key, case='partial'):
    demo = DemoContext(mode='deterministic_demo', demo_today='2026-10-08')
    dataset = DatasetContext(dataset_version='a06-display-test-fixtures', file_digests={'display-test-only': 'a'*64}, rules_version='display-test-only')
    context = ConfirmedContext(request_id='a06-'+key, confirmed_at=datetime.now(timezone.utc), requirements=ConfirmedRequirements(destination='独立展示测试区域 · '+case, start_date='2026-10-20', end_date='2026-10-22', duration_nights=2, duration_days=3, budget_cents=10000), profile_snapshot=ProfileSnapshot(group_size=2), demo_context=demo, dataset_context=dataset)
    repo.record_confirmed_request(user, NOTICE, context)
    scope = repo.begin_run(user, context.request_id, demo, dataset)
    port = repo.bind_port(user, scope.run_id)
    call(port.report_stage('RECOMMENDING','RUNNING',None))
    recommend = RecommendCampsitesResult(execution_mode='deterministic_demo', search_outcome='NO_MATCH' if case=='no-match' else 'MATCHES', candidates=[] if case=='no-match' else [{'campsite_id':'display-camp','rank':1,'reasons':['独立夹具中的可访问营地'],'material_uncertainties':['测试营地，无真实可用性信息']}], excluded_candidates=[{'campsite_id':'excluded-display-camp','reasons':['独立夹具：容量不满足']}], assumptions=[NOTICE], source_refs=[{'dataset_file':'display-test-only.json','record_id':'display-camp'}])
    call(port.save_recommendations(recommend,scope.write_keys['recommendations']))
    if case=='no-match':
        call(port.report_stage('COMPLETED','SUCCEEDED',None))
        return scope, None
    if case=='failure':
        call(port.report_stage('GENERATING','FAILED',ContractError(code='AGENT_FAILURE',message='独立注入：解释器暂时不可用。',recoverable=True,allowed_actions=['RETRY'])))
        return scope, None
    call(port.report_stage('GENERATING','RUNNING',None))
    itinerary=ItineraryResult(execution_mode='deterministic_demo',itinerary_entries=[{'entry_kind':'CAMP','start_at':'2026-10-20T12:00:00+11:00','end_at':'2026-10-22T10:00:00+11:00','campsite_id':'display-camp','description':'展示测试：两晚露营安排'}],selected_campsite_ids=['display-camp'],revision_reason=NOTICE,assumptions=[NOTICE])
    call(port.report_stage('SAVING_VERSION','RUNNING',None))
    version=call(port.append_plan_version(None,itinerary,context.request_id,NOTICE,scope.write_keys['version']))
    call(port.report_stage('ASSESSING_LOGISTICS','RUNNING',None))
    partial=case=='partial'
    unknown=case=='unknown'
    subtotal=15152 if case=='overbudget' else 152
    prices=[{'category':kind,'item_key':kind,'quantity':None if unknown and kind=='WATER' else '1.5' if kind=='CAMPSITE' else '1','unit':'测试单位','unit_price_cents':None if unknown and kind=='WATER' else 10101 if case=='overbudget' and kind=='CAMPSITE' else 101 if kind=='CAMPSITE' else 0,'subtotal_cents':None if unknown and kind=='WATER' else subtotal if kind=='CAMPSITE' else 0,'source_ref':None} for kind in ('CAMPSITE','TRANSPORT','FOOD','WATER','ADDITIONAL_GEAR')]
    logistics=LogisticsResult(execution_mode='deterministic_demo',version_context=version.version_context,gear_checklist=[{'item_key':'tent','required_quantity':'2','available_quantity':None if unknown else '2','missing_quantity':None if unknown else '0','unit':'persons','capacity_requirement':2,'arrangement_status':'UNCONFIRMED' if unknown else 'OWNED','essential':True}],transport_feasible=None if unknown else True,cost_breakdown=prices,total_cents=None if unknown else subtotal,known_subtotal_cents=subtotal,budget_difference_cents=None if unknown else subtotal-10000,outcome='REVISION' if unknown or case=='overbudget' else 'PASSED',assumptions=[NOTICE],uncertainties=['水费未知，测试显示 null。'] if unknown else [])
    stored=call(port.save_assessment(version.version_context,'LOGISTICS',logistics,scope.write_keys['logistics']))
    if partial:
        return scope, version
    call(port.report_stage('ASSESSING_SAFETY','RUNNING',None))
    safety=SafetyResult(execution_mode='deterministic_demo',version_context=version.version_context,depends_on_assessment_id=stored.assessment_id,risk_level='LOW',confidence='HIGH',data_quality={kind:'AVAILABLE' for kind in ('WEATHER','FIRE','ROAD','RESTRICTION')},evidence=[{'kind':kind,'summary':NOTICE,'source_date':'2026-10-07','status':'AVAILABLE','valid_from':'2026-10-20','valid_to':'2026-10-22','road_state':'CLOSED' if case=='closed' and kind=='ROAD' else 'OPEN' if kind=='ROAD' else None,'source_refs':[{'dataset_file':'display-test-only.json','record_id':'display-camp'}]} for kind in ('WEATHER','FIRE','ROAD','RESTRICTION')],hazards=[],mandatory_blockers=[],recommended_actions=['测试建议：出发前核对来源。'],requires_human_review=False,outcome='PASSED',assumptions=[NOTICE])
    if case=='review':
        safety=SafetyResult.model_validate(safety.model_dump(mode='json')|{'risk_level':'HIGH','confidence':'LOW','requires_human_review':True,'outcome':'REVIEW','hazards':['独立夹具：高风险因素']})
    if case in {'missing','stale','conflict'}:
        state={'missing':'MISSING','stale':'STALE','conflict':'CONFLICTING'}[case]
        value=safety.model_dump(mode='json')
        value['data_quality']['WEATHER']=state
        value['evidence'][0]['status']=state
        if case=='missing':
            value['evidence'][0].update(summary=None,source_date=None,valid_from=None,valid_to=None,source_refs=[])
        value.update(outcome='REVIEW',requires_human_review=True,unresolved_conflicts=['独立夹具：天气来源冲突'] if case=='conflict' else [])
        safety=SafetyResult.model_validate(value)
    call(port.save_assessment(version.version_context,'SAFETY',safety,scope.write_keys['safety']))
    call(port.report_stage('ROUTING','RUNNING',None))
    call(port.route_assessed_version(version.version_context,'ELIGIBLE_FOR_FINALISATION',NOTICE,scope.write_keys['route']))
    call(port.report_stage('COMPLETED','SUCCEEDED',None))
    return scope, version
