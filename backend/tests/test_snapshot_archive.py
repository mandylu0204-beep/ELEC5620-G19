"""Safety archive equivalence, field explicitness and mutation boundaries."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.synthetic_dataset import SyntheticDataset
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.adapters.snapshot_archive import (SafetyArchive, RawSafetyArchive, FrozenMap,
    FrozenList, UnsupportedArchive, model_shape)
from app.application.parsed_snapshots import ParsedSnapshots
from app.contracts.dto import ConfirmedRequirements, DemoContext, ScenarioContext
from app.contracts.errors import ContractFailure

ROOT=Path(__file__).resolve().parents[2]/'data'

@pytest.fixture(scope='module',params=['synthetic_demo_v2','synthetic_demo_v2_1'])
def dataset(request):
    return SyntheticDatasetV2Adapter(ROOT/request.param).load()

def cache_for(dataset):
    cache=ParsedSnapshots()
    with cache.transaction():cache.stage('source',dataset)
    return cache

def fresh(dataset,records,policy=None,cls=SyntheticDataset):
    return cls(dataset.context,dataset._campsites,dataset._gear_rules,dataset._costs,
        dataset._profiles,dataset._requests,records,
        v2_policy=dataset.v2_policy if policy is None else policy,
        runtime_requests=dataset.runtime_requests,safety_facts=dataset.safety_facts,
        runtime_profiles=dataset.runtime_profiles)


def test_all_source_records_keep_values_types_fields_sets_and_both_serializations(dataset):
    cache=cache_for(dataset);warm=cache.get('source')
    assert type(warm._safety) is SafetyArchive
    assert type(warm._v2_policy['safety']) is RawSafetyArchive
    assert type(warm.safety_cases) is tuple
    assert [r.safety_case_id for r in dataset.safety_cases]==[r.safety_case_id for r in warm.safety_cases]
    for original in dataset.safety_cases:
        restored=warm.get_safety(original.safety_case_id)
        assert type(restored) is type(original)
        assert model_shape(restored)==model_shape(original)
        assert restored==original
        assert restored.model_dump_json()==original.model_dump_json()
        assert restored.model_dump_json(exclude_unset=True)==original.model_dump_json(exclude_unset=True)
    assert warm.context==dataset.context and warm.v2_policy==dataset.v2_policy


def test_explicit_defaults_and_unset_nested_defaults_remain_distinct(dataset):
    original=dataset.safety_cases[0]
    implicit=original.model_copy(update={'scenario_context':ScenarioContext.model_validate(
        original.scenario_context.model_dump(exclude={'template_id'}))})
    explicit=implicit.model_copy(update={'scenario_context':implicit.scenario_context.model_copy(update={'template_id':None})})
    assert implicit.scenario_context.model_fields_set!=explicit.scenario_context.model_fields_set
    image=SafetyArchive.capture({'implicit':implicit,'explicit':explicit})
    for key,source in [('implicit',implicit),('explicit',explicit)]:
        assert model_shape(image[key])==model_shape(source)
        assert image[key].model_dump_json(exclude_unset=True)==source.model_dump_json(exclude_unset=True)


def test_mutating_cold_source_and_materialized_results_cannot_pollute_archive(dataset):
    cold=deepcopy(dataset);cache=cache_for(cold);first=cache.get('source')
    key=next(iter(cold._safety));original=dataset.get_safety(key)
    cold._safety[key].uncertainties.append('cold mutation')
    cold._v2_policy['safety'].clear()
    exported=first.get_safety(key);exported.uncertainties.append('returned mutation')
    exported.scenario_context.evidence[0].source_refs.clear()
    view=first.v2_policy;view['safety'].clear()
    assert cache.get('source').get_safety(key).model_dump_json()==original.model_dump_json()
    assert cache.get('source').v2_policy==dataset.v2_policy
    assert type(first.v2_policy) is dict and type(first.v2_policy['safety']) is dict
    assert first.v2_policy is not first.v2_policy


def test_cold_constructor_owns_safety_inputs_before_any_cache(dataset):
    records=deepcopy(dataset._safety);policy=dataset.v2_policy
    cold=fresh(dataset,records,policy);key=next(iter(records))
    expected=cold.get_safety(key).model_dump_json()
    records[key].uncertainties.append('constructor alias')
    policy['safety'].clear()
    assert cold.get_safety(key).model_dump_json()==expected
    assert cold.v2_policy['safety']


@pytest.mark.parametrize('mutation',['private','extra','subclass'])
def test_unknown_dto_state_uses_conservative_copy_without_losing_state(dataset,mutation):
    records=deepcopy(dataset._safety);key=next(iter(records));record=records[key]
    if mutation=='private':object.__setattr__(record,'__pydantic_private__',{'extra':['kept']})
    elif mutation=='extra':object.__setattr__(record,'extra_instance_state',{'rows':['kept']})
    else:
        class FutureScenario(ScenarioContext):pass
        record=record.model_copy(update={'scenario_context':FutureScenario.model_validate(record.scenario_context.model_dump())})
        records[key]=record
    cache=cache_for(fresh(dataset,records));warm=cache.get('source')
    assert type(warm._safety) is dict
    got=warm.get_safety(key)
    if mutation=='private':assert got.__pydantic_private__=={'extra':['kept']}
    elif mutation=='extra':assert got.extra_instance_state=={'rows':['kept']}
    else:assert type(got.scenario_context) is type(record.scenario_context)
    got.uncertainties.append('detached')
    assert 'detached' not in cache.get('source').get_safety(key).uncertainties


def test_unknown_dataset_attributes_are_preserved_and_detached(dataset):
    cold=deepcopy(dataset);cold.extra_state={'rows':[]}
    cache=cache_for(cold);one=cache.get('source');one.extra_state['rows'].append(1)
    assert cache.get('source').extra_state=={'rows':[]}


def test_unknown_dataset_subclass_stays_on_original_copy_path(dataset):
    class FutureDataset(SyntheticDataset):pass
    cold=fresh(dataset,deepcopy(dataset._safety),cls=FutureDataset)
    warm=cache_for(cold).get('source')
    assert type(warm) is FutureDataset and type(warm._safety) is dict


def test_missing_and_campsite_mismatch_errors_are_unchanged(dataset):
    warm=cache_for(dataset).get('source')
    for source in [dataset,warm]:
        with pytest.raises(ContractFailure) as missing:source.get_safety('missing-source-id')
        assert missing.value.error.code=='ADAPTER_FAILURE'
        with pytest.raises(ContractFailure) as mismatch:source.get_safety(source.safety_cases[0].safety_case_id,campsite_id='wrong-camp')
        assert mismatch.value.error.code=='ADAPTER_FAILURE'


def test_concurrent_materializations_and_exports_do_not_share_mutable_values(dataset):
    cache=cache_for(dataset);key=dataset.safety_cases[0].safety_case_id
    def worker(_):
        warm=cache.get('source');record=warm.get_safety(key);record.uncertainties.append('local')
        warm.v2_policy['safety'].clear()
        return warm.get_safety(key)==dataset.get_safety(key)
    with ThreadPoolExecutor(max_workers=4) as pool:assert all(pool.map(worker,range(8)))


def test_raw_archive_keeps_decimal_bool_null_order_and_container_types():
    source={'row':{'decimal':Decimal('1.20'),'int':1,'bool':True,'null':None,'list':[{'x':2}],'tuple':(Decimal('3.40'),)}}
    image=RawSafetyArchive.capture(source);result=image['row']
    assert list(result)==list(source['row'])
    assert type(result['decimal']) is Decimal and result['decimal'].as_tuple()==Decimal('1.20').as_tuple()
    assert type(result['int']) is int and type(result['bool']) is bool
    assert result['null'] is None and type(result['list']) is list and type(result['tuple']) is tuple
    source['row']['list'].clear();result['list'][0]['x']=999
    assert image['row']['list']==[{'x':2}]
    assert deepcopy(image) is image
    with pytest.raises((FrozenInstanceError,TypeError,AttributeError)):image.entries=()
    with pytest.raises(TypeError):image._index['row']='changed'


def test_archive_rejects_mutable_or_unknown_nodes_and_raw_values():
    with pytest.raises(UnsupportedArchive):FrozenMap((('bad',[]),))
    with pytest.raises(UnsupportedArchive):FrozenList([1])
    with pytest.raises(UnsupportedArchive):RawSafetyArchive.capture({'row':{'unknown':set([1])}})


def test_unknown_raw_policy_is_deepcopied_not_discarded(dataset):
    cold=deepcopy(dataset);cold._v2_policy['safety']['custom']={'future':{1,2}}
    cache=cache_for(cold);warm=cache.get('source')
    assert type(warm._v2_policy['safety']) is dict
    warm._v2_policy['safety']['custom']['future'].clear()
    assert cache.get('source')._v2_policy['safety']['custom']['future']=={1,2}


def test_selector_wrapper_and_each_returned_query_are_independent():
    source=SyntheticDatasetV2Adapter(ROOT/'synthetic_demo_v2_1').load();cache=cache_for(source)
    one,two=cache.get('source'),cache.get('source')
    assert one.trip_evidence_selector is not two.trip_evidence_selector
    req=ConfirmedRequirements(destination='CampMate Demo Region',start_date='2026-10-27',end_date='2026-10-29',duration_nights=2,duration_days=3,budget_cents=50000)
    demo=DemoContext(mode='deterministic_demo',demo_today='2026-10-26',dataset_version='2.1.0')
    def query(dataset):return dataset.trip_evidence_selector.resolve_trip_evidence(req,['demo-lake-meadow'],demo)
    expected=query(source).model_dump_json();result=query(one)
    assert result.model_dump_json()==expected
    result.scenario_context.evidence[0].source_refs.clear()
    one.trip_evidence_selector._entries=();one.trip_evidence_selector.index_digest='modified'
    assert query(two).model_dump_json()==expected and query(cache.get('source')).model_dump_json()==expected

@pytest.mark.parametrize('logistics_mode,safety_mode',[('rules','rules'),('model','rules'),('rules','model'),('model','model')])
def test_cold_and_warm_model_registration_contexts_are_identical(tmp_path,monkeypatch,logistics_mode,safety_mode):
    from campus_http_fixtures import mock_campus
    from test_safety_runtime_registration import settings
    from app.application.agent_runtime import build_v2_hybrid_binding
    from app.application.datasets import inspect_dataset
    calls,_=mock_campus(monkeypatch)
    cfg=settings(tmp_path,logistics_execution=logistics_mode,safety_execution=safety_mode)
    descriptor=inspect_dataset(cfg);cold=build_v2_hybrid_binding(cfg,descriptor)
    cache=ParsedSnapshots()
    with cache.transaction():build_v2_hybrid_binding(cfg,descriptor,parsed_snapshots=cache)
    with cache.transaction():warm=build_v2_hybrid_binding(cfg,descriptor,parsed_snapshots=cache)
    assert warm.context==cold.context and type(warm.agent.dataset._safety) is SafetyArchive
    assert calls==[]


def test_offline_logistics_requests_outputs_and_trace_match_cold_copy():
    import asyncio
    from test_llm_logistics_agent import input_fixture,agent_fixture,baseline
    from app.workflow import WorkflowConfiguration
    cold,input,config=input_fixture();warm=cache_for(cold).get('source')
    warm_config=WorkflowConfiguration(warm,safety_case_ids=['safety-15'])
    assert warm_config.context==config.context
    assert baseline(warm,input,warm_config).model_dump_json()==baseline(cold,input,config).model_dump_json()
    one,requests_one=agent_fixture(cold,config);two,requests_two=agent_fixture(warm,warm_config)
    first=asyncio.run(one.assess_with_trace(input));second=asyncio.run(two.assess_with_trace(input))
    assert requests_one==requests_two
    a,b=({name:getattr(outcome,name).model_dump() for name in ('assessment','plan','trace')} for outcome in (first,second))
    a['trace'].pop('elapsed_ms',None);b['trace'].pop('elapsed_ms',None)
    assert a==b


def test_offline_safety_requests_outputs_trace_and_selection_match_cold_copy():
    import asyncio
    from safety_fixtures import safety_fixture,safety_agent_fixture
    cold,input,config,baseline,selection=safety_fixture();warm=cache_for(cold).get('source')
    _,warm_input,warm_config,warm_baseline,warm_selection=safety_fixture(dataset=warm)
    assert warm_config.context==config.context and model_shape(input.scenario_context)==model_shape(warm_input.scenario_context)
    assert warm_input.model_dump_json()==input.model_dump_json()
    assert warm_baseline.model_dump_json()==baseline.model_dump_json()
    assert warm_selection.model_dump_json()==selection.model_dump_json()
    one,requests_one=safety_agent_fixture(cold,config);two,requests_two=safety_agent_fixture(warm,warm_config)
    first=asyncio.run(one.assess_safety_with_trace(input));second=asyncio.run(two.assess_safety_with_trace(warm_input))
    assert requests_one==requests_two
    a,b=({name:getattr(outcome,name).model_dump() for name in ('assessment','plan','trace')} for outcome in (first,second))
    a['trace'].pop('elapsed_ms',None);b['trace'].pop('elapsed_ms',None)
    assert a==b


def test_cancelled_registration_never_publishes_source_image(dataset):
    import asyncio
    cache=cache_for(dataset)
    with pytest.raises(asyncio.CancelledError):
        with cache.transaction():
            cache.stage('cancelled',dataset)
            raise asyncio.CancelledError()
    assert cache.get('cancelled') is None
    assert cache.get('source').safety_cases[0].model_dump_json()==dataset.safety_cases[0].model_dump_json()
