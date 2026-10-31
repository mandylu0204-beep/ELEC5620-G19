"""Read-only campsite tool bound to confirmed input and saved recommendations."""
from ..contracts.dto import RecommendCampsitesInput
from ..contracts.enums import ExecutionMode, ErrorCode
from ..agents.rules.planning import recommend, validate_constraints, violations, match_facts
from .client import model_failure

TOOL_VERSION = 'b04-campsite-tool-1'
DETAILED_TOOL_VERSION = 'campsite-tool-daily-1'


def recommend_for_model(dataset, input: RecommendCampsitesInput):
    if input.demo_context.mode != ExecutionMode.AGENT:
        raise model_failure('Campus model tools only accept  agent mode.', code=ErrorCode.CONTRACT_INVALID)
    if dataset.context.dataset_version != input.demo_context.dataset_version:
        raise model_failure('Model tool and confirmed data versions differ.', code=ErrorCode.STALE_CONTEXT)
    if input.confirmed_requirements.start_date < input.demo_context.demo_today:
        raise model_failure('The confirmed trip starts before the fixed demonstration date.', code=ErrorCode.INPUT_INVALID)
    return recommend(dataset, input)


class CampsiteToolset:
    def __init__(self, dataset, input):
        self.dataset, self.input = dataset, input
        if (input.demo_context.mode != ExecutionMode.AGENT
                or input.recommendations.execution_mode != ExecutionMode.AGENT):
            raise model_failure('The campsite tool must bind confirmation and recommendations in  agent  mode.', code=ErrorCode.CONTRACT_INVALID)
        if input.demo_context.dataset_version != dataset.context.dataset_version:
            raise model_failure('Campsite tool data snapshot versions differ.', code=ErrorCode.STALE_CONTEXT)
        if input.confirmed_requirements.start_date < input.demo_context.demo_today:
            raise model_failure('The campsite tool cannot plan past trips.', code=ErrorCode.INPUT_INVALID)
        validate_constraints(input.confirmed_requirements)
        supplied = input.recommendations.candidates
        ids = [item.campsite_id for item in supplied]
        ranks = [item.rank for item in supplied]
        if (input.recommendations.search_outcome != 'MATCHES' or not ids
                or len(ids) != len(set(ids)) or len(ranks) != len(set(ranks))):
            raise model_failure('Model planning needs registered, unique matching candidates.', code=ErrorCode.INPUT_INVALID)
        # The model cannot add candidates absent from A's saved recommendation.
        self._records = []
        for item in sorted(supplied, key=lambda value: value.rank):
            campsite = dataset.get_campsite(item.campsite_id)
            if not violations(campsite, input.confirmed_requirements, input.profile_snapshot):
                self._records.append((item, campsite))
        if not self._records:
            raise model_failure('No registered candidate meets the confirmed hard conditions.', code=ErrorCode.INPUT_INVALID)

    @property
    def exposed_ids(self):
        return tuple(campsite.campsite_id for _, campsite in self._records)

    def search_campsites(self):
        value = {'tool': 'search_campsites', 'read_only': True, 'source_type': 'SYNTHETIC',
            'demo_only': True, 'dataset_version': self.dataset.context.dataset_version,
            'scope': 'Only currently viable candidates from the saved recommendation; no booking or safety clearance.',
            'candidates': [{
                'campsite_id': campsite.campsite_id, 'rank': item.rank,
                'name': campsite.name, 'region': campsite.region,
                'nightly_fee_cents': campsite.nightly_fee_cents,
                'currency': 'AUD', 'fee_unit': campsite.fee_unit,
                'facilities': list(campsite.facilities),
                'quiet_environment': campsite.quiet_environment,
                'step_free_path': campsite.step_free_path,
                'mandatory_restrictions': list(campsite.mandatory_restrictions),
                'source_ref': campsite.source_ref.model_dump(mode='json'),
            } for item, campsite in self._records]}

        if getattr(self.dataset, 'planning_reference', None) is not None:
            from ..adapters.planning_reference import available_activities
            for item, (_, campsite) in zip(value['candidates'], self._records):
                item.update(max_group_size=campsite.max_group_size,
                    vehicle_access=campsite.vehicle_access,
                    public_transport_access=campsite.public_transport_access,
                    toilets=campsite.toilets, showers=campsite.showers, potable_water=campsite.potable_water,
                    match_facts=[{key:value for key,value in fact.items() if key not in {'source_ref','text'}}
                        for fact in match_facts(campsite, self.input.confirmed_requirements, self.input.profile_snapshot)],
                    onsite_activities=[row.model_dump(mode='json') for row in available_activities(
                        self.dataset, campsite.campsite_id, self.input.confirmed_requirements)])
            value['daily_scope'] = 'Only listed synthetic onsite suggestions; times are host suggestions, not verified schedules.'
        return value
