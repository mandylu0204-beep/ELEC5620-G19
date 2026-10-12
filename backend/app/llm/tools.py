"""Read-only campsite tool bound to confirmed input and saved recommendations."""
from ..contracts.dto import RecommendCampsitesInput
from ..contracts.enums import ExecutionMode, ErrorCode
from ..agents.rules.planning import recommend, validate_constraints, violations
from .client import model_failure

TOOL_VERSION = 'b04-campsite-tool-1'


def recommend_for_model(dataset, input: RecommendCampsitesInput):
    if input.demo_context.mode != ExecutionMode.AGENT:
        raise model_failure('校园模型工具只接受 agent 模式。', code=ErrorCode.CONTRACT_INVALID)
    if dataset.context.dataset_version != input.demo_context.dataset_version:
        raise model_failure('模型工具与确认数据版本不一致。', code=ErrorCode.STALE_CONTEXT)
    if input.confirmed_requirements.start_date < input.demo_context.demo_today:
        raise model_failure('确认行程早于固定演示日期。', code=ErrorCode.INPUT_INVALID)
    return recommend(dataset, input)


class CampsiteToolset:
    def __init__(self, dataset, input):
        self.dataset, self.input = dataset, input
        if (input.demo_context.mode != ExecutionMode.AGENT
                or input.recommendations.execution_mode != ExecutionMode.AGENT):
            raise model_failure('营地工具必须绑定 agent 模式的确认与推荐。', code=ErrorCode.CONTRACT_INVALID)
        if input.demo_context.dataset_version != dataset.context.dataset_version:
            raise model_failure('营地工具的数据快照版本不一致。', code=ErrorCode.STALE_CONTEXT)
        if input.confirmed_requirements.start_date < input.demo_context.demo_today:
            raise model_failure('营地工具不能规划过去的行程。', code=ErrorCode.INPUT_INVALID)
        validate_constraints(input.confirmed_requirements)
        supplied = input.recommendations.candidates
        ids = [item.campsite_id for item in supplied]
        ranks = [item.rank for item in supplied]
        if (input.recommendations.search_outcome != 'MATCHES' or not ids
                or len(ids) != len(set(ids)) or len(ranks) != len(set(ranks))):
            raise model_failure('模型规划需要已登记且唯一的匹配候选。', code=ErrorCode.INPUT_INVALID)
        # The model cannot add candidates absent from A's saved recommendation.
        self._records = []
        for item in sorted(supplied, key=lambda value: value.rank):
            campsite = dataset.get_campsite(item.campsite_id)
            if not violations(campsite, input.confirmed_requirements, input.profile_snapshot):
                self._records.append((item, campsite))
        if not self._records:
            raise model_failure('已登记候选没有满足确认硬条件的营地。', code=ErrorCode.INPUT_INVALID)

    @property
    def exposed_ids(self):
        return tuple(campsite.campsite_id for _, campsite in self._records)

    def search_campsites(self):
        return {'tool': 'search_campsites', 'read_only': True, 'source_type': 'SYNTHETIC',
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
