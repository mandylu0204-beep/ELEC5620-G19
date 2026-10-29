"""Offline fee preflight and authenticated preservation; no live campus calls."""
from datetime import timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.application.revision_preflight import require_cheaper_campsite
from app.contracts.errors import ContractFailure
from app.llm.planning_schema import validated_itinerary
from llm_fixtures import model_input
from test_model_logistics_wiring import application, mock_roles, launch, finalise
from test_plan_changes import change
from test_requests import sign_in


def preflight_input(previous='demo-moonlit-field', transform=lambda site: site):
    source, inputs = model_input()
    sites = {site.campsite_id: transform(site) for site in source.campsites}
    dataset = SimpleNamespace(campsites=list(sites.values()), get_campsite=sites.__getitem__,
        has_v2_policy=source.has_v2_policy)
    confirmed = SimpleNamespace(requirements=inputs.confirmed_requirements,
        profile_snapshot=inputs.profile_snapshot, demo_context=inputs.demo_context)
    proposal = dict(campsite_id=previous, decision_summary='Offline baseline.',
        nights=[inputs.confirmed_requirements.start_date + timedelta(days=i)
            for i in range(inputs.confirmed_requirements.duration_nights)])
    content = validated_itinerary(source, inputs, proposal,
        {candidate.campsite_id for candidate in inputs.recommendations.candidates})
    return dataset, confirmed, content


@pytest.mark.parametrize('kind', ['already_cheapest', 'same_fee', 'unknown_prices', 'free_site', 'cheaper_but_ineligible'])
def test_no_verified_cheaper_matching_site_is_a_normal_preserved_outcome(kind):
    def transform(site):
        if kind == 'same_fee':
            return site.model_copy(update={'nightly_fee_cents': 2000})
        if kind == 'unknown_prices' and site.campsite_id != 'demo-moonlit-field':
            return site.model_copy(update={'nightly_fee_cents': None})
        if kind == 'free_site' and site.campsite_id == 'demo-moonlit-field':
            return site.model_copy(update={'nightly_fee_cents': 0})
        if kind == 'cheaper_but_ineligible' and site.campsite_id != 'demo-moonlit-field':
            return site.model_copy(update={'nightly_fee_cents': 100, 'max_group_size': 1})
        return site
    dataset, confirmed, content = preflight_input(transform=transform)
    with pytest.raises(ContractFailure) as error:
        require_cheaper_campsite(dataset, confirmed, content)
    assert error.value.error.code == 'INPUT_INVALID'
    assert error.value.error.context == {'revision_outcome': 'NO_CHEAPER_CAMPSITE'}
    assert '原方案已保留' in error.value.error.message


def test_known_lower_fee_is_allowed_but_an_unknown_previous_fee_cannot_be_compared():
    dataset, confirmed, content = preflight_input(previous='demo-wattle-rest')
    assert require_cheaper_campsite(dataset, confirmed, content) is None
    dataset, confirmed, content = preflight_input(transform=lambda site: site.model_copy(
        update={'nightly_fee_cents': None}) if site.campsite_id == 'demo-moonlit-field' else site)
    with pytest.raises(ContractFailure) as error:
        require_cheaper_campsite(dataset, confirmed, content)
    assert error.value.error.context == {'revision_outcome': 'CAMPSITE_FEE_UNKNOWN'}


def business_rows(app):
    tables = ('plans', 'runs', 'versions', 'run_versions', 'recommendations', 'assessments',
        'gear_checklists', 'model_planning_traces', 'model_logistics_audits', 'model_safety_audits',
        'write_receipts', 'final_records', 'workflow_commands', 'run_events', 'run_leases',
        'revision_proposals','revision_choice_commands')
    with app.state.database.transaction(write=False) as db:
        return {table: [tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in tables}


def test_http_no_cheaper_preserves_current_and_final_records_and_never_dispatches(tmp_path, monkeypatch):
    requests, control = mock_roles(monkeypatch)
    control['site'] = 'demo-moonlit-field'
    app = application(tmp_path, 'budget_revision')
    with TestClient(app) as client:
        headers = sign_in(client)
        original = launch(client, headers, 'budget_revision')
        assert original['finalisation_available']
        final_path, _ = finalise(client, headers, original)
        final_record = client.get(final_path).json()['final_record']
        path = '/api/v1/plans/' + original['plan']['plan_id']
        original = client.get(path).json()
        before = business_rows(app)
        request_count = len(requests)

        def forbidden_dispatch(*args, **kwargs):
            raise AssertionError('No cheaper candidate must not enqueue a task')
        monkeypatch.setattr(app.state.dispatcher, 'enqueue', forbidden_dispatch)
        response = change(client, headers, original, 'revise', feedback='cheaper campsite')
        assert response.status_code == 422, response.text
        assert response.json()['error']['context'] == {'revision_outcome': 'NO_CHEAPER_CAMPSITE'}
        assert '原方案已保留' in response.json()['error']['message']
        from test_plan_changes import command
        proposal_response=client.post(path+'/revision-proposals',headers=headers,
            json=command(original,feedback='cheaper campsite'))
        assert proposal_response.status_code==422,proposal_response.text
        assert proposal_response.json()['error']['context']=={'revision_outcome':'NO_CHEAPER_CAMPSITE'}
        assert business_rows(app) == before
        assert len(requests) == request_count
        current = client.get(path).json()
        assert current['plan'] == original['plan']
        assert current['run'] == original['run']
        assert current['version'] == original['version']
        assert current['assessments'] == original['assessments']
        assert current['last_final'] == original['last_final']
        assert client.get(final_path).json()['final_record'] == final_record

        # Rejected retries remain read-only; stale inputs and other owners do
        # not get a fee-search result in place of the existing guards.
        assert change(client, headers, original, 'revise', feedback='cheaper campsite').status_code == 422
        from test_plan_changes import command
        stale = client.post(path+'/revise', headers=headers, json={**command(original,
            feedback='cheaper campsite'), 'expected_run_revision': 999})
        assert stale.status_code == 409
        assert 'revision_outcome' not in stale.json()['error']['context']
        other = sign_in(client, 'camper.b', 'CampMate-B-2026!')
        assert change(client, other, original, 'revise', feedback='cheaper campsite').status_code == 404
        assert business_rows(app) == before
        assert len(requests) == request_count
