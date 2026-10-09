import asyncio

import pytest
from pydantic import ValidationError

from app.agents.stub import StubAgent
from app.contracts.dto import (
    ConfirmedRequirements, CostLine, DemoContext, Evidence, InterpretRequestInput,
    LogisticsResult, ProfileSnapshot, Provenance, SafetyResult, TripRequirements, VersionContext,
)
from app.contracts.enums import ExecutionMode, PlanVersionStatus
from app.contracts.errors import ContractFailure
from app.contracts.ports import AgentPort


def version_context():
    return VersionContext(plan_id='plan-1', plan_version_id='v1', run_id='run-1', input_fingerprint='a' * 64)


@pytest.mark.parametrize('value', [True, 0, -5, 5.5, '500'])
def test_budget_rejects_invalid_money(value):
    with pytest.raises(ValidationError):
        TripRequirements(budget_cents=value)


def test_two_nights_must_cover_three_days():
    fields = dict(destination='Demo Region', start_date='2026-10-20', duration_nights=2, end_date='2026-10-22', duration_days=3, budget_cents=25000)
    assert ConfirmedRequirements(**fields).duration_days == 3
    with pytest.raises(ValidationError):
        ConfirmedRequirements(**{**fields, 'end_date': '2026-10-21'})


def test_decimal_is_serialized_as_text_and_rounds_half_up():
    line = CostLine(category='TRANSPORT', item_key='distance', quantity='2.5', unit='km', unit_price_cents=101, subtotal_cents=253, source_ref=None)
    assert line.model_dump(mode='json')['quantity'] == '2.5'
    with pytest.raises(ValidationError):
        CostLine(**{**line.model_dump(), 'subtotal_cents': 252})


@pytest.mark.parametrize('value', [2.5, True, 'NaN', 'Infinity', '-1'])
def test_quantity_does_not_accept_float_nonfinite_or_negative(value):
    with pytest.raises(ValidationError):
        CostLine(category='TRANSPORT', item_key='distance', quantity=value, unit='km', unit_price_cents=100, subtotal_cents=250, source_ref=None)


def test_unknown_cost_cannot_be_given_a_fake_total_or_pass():
    line = CostLine(category='TRANSPORT', item_key='distance', quantity=None, unit='km', unit_price_cents=101, subtotal_cents=None, source_ref=None)
    fields = dict(execution_mode='deterministic_demo', version_context=version_context(), gear_checklist=[], transport_feasible=None, cost_breakdown=[line], total_cents=None, known_subtotal_cents=0, budget_difference_cents=None, outcome='REVIEW')
    assert LogisticsResult(**fields).total_cents is None
    for patch in [{'total_cents': 0}, {'outcome': 'PASSED'}]:
        with pytest.raises(ValidationError):
            LogisticsResult(**{**fields, **patch})


@pytest.mark.parametrize('quality', ['MISSING', 'STALE', 'CONFLICTING'])
def test_inadequate_evidence_cannot_pass(quality):
    evidence = Evidence(kind='WEATHER', summary='Synthetic fixture', source_date=None, status=quality, valid_from=None, valid_to=None, source_refs=[])
    with pytest.raises(ValidationError):
        SafetyResult(execution_mode='deterministic_demo', version_context=version_context(), depends_on_assessment_id='logistics-1', risk_level='LOW', confidence='HIGH', data_quality={'weather': quality}, evidence=[evidence], hazards=[], mandatory_blockers=[], recommended_actions=[], outcome='PASSED', requires_human_review=False)


def test_high_risk_cannot_omit_required_review():
    with pytest.raises(ValidationError):
        SafetyResult(execution_mode='deterministic_demo', version_context=version_context(), depends_on_assessment_id='logistics-1', risk_level='HIGH', confidence='MEDIUM', data_quality={}, evidence=[], hazards=[], mandatory_blockers=[], recommended_actions=[], outcome='REVISION', requires_human_review=False)


def test_input_does_not_accept_oracle_or_identity_fields():
    base = dict(raw_text='Two nights', demo_context=DemoContext(mode='stub', demo_today='2026-10-08'))
    for extra in [{'expected_request_status': 'CONFIRMED'}, {'owner_user_id': 'someone-else'}]:
        with pytest.raises(ValidationError):
            InterpretRequestInput(**base, **extra)


def test_zero_people_are_not_coerced_to_a_valid_group():
    with pytest.raises(ValidationError):
        ProfileSnapshot(group_size=0)


def test_human_approved_is_not_a_version_state():
    with pytest.raises(ValueError):
        PlanVersionStatus('HUMAN_APPROVED')


def test_provenance_requires_boolean_demo_only():
    with pytest.raises(ValidationError):
        Provenance(demo_only=1)


def test_stub_does_not_extract_fields_from_prose_or_claim_workflow_success():
    agent = StubAgent()
    assert isinstance(agent, AgentPort)
    result = asyncio.run(agent.interpret_request(InterpretRequestInput(raw_text='Demo Region, 2026-10-20, two nights, AUD 250', demo_context=DemoContext(mode='stub', demo_today='2026-10-08'))))
    assert result.execution_mode == ExecutionMode.STUB
    assert result.extracted_requirements.destination is None
    assert len(result.clarifications) == 4
    assert not result.source_refs
    with pytest.raises(ContractFailure):
        asyncio.run(agent.recommend_campsites(None))
