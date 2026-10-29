"""Read-only checks before replacing an active run; never invoke model roles."""
from ..agents.rules.planning import recommend
from ..contracts.dto import ItineraryResult, RecommendCampsitesInput
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure

CHEAPER_GOALS = frozenset({'cheaper campsite', '更便宜的营地', 'lower campsite fee'})


def require_cheaper_campsite(dataset, confirmed, previous_content):
    previous = ItineraryResult.model_validate(previous_content)
    selected = previous.selected_campsite_ids
    fees = [dataset.get_campsite(key).nightly_fee_cents for key in selected]
    if len(fees) != 1 or fees[0] is None:
        raise ContractFailure(ContractError(code=ErrorCode.INPUT_INVALID,
            message='当前营地费用无法比较，原方案已保留。',
            context={'revision_outcome': 'CAMPSITE_FEE_UNKNOWN'}))
    candidates = recommend(dataset, RecommendCampsitesInput(
        confirmed_requirements=confirmed.requirements,
        profile_snapshot=confirmed.profile_snapshot, demo_context=confirmed.demo_context))
    for candidate in candidates.candidates:
        site = dataset.get_campsite(candidate.campsite_id)
        if (candidate.campsite_id not in selected and site.nightly_fee_cents is not None
                and site.nightly_fee_cents < fees[0]):
            return
    raise ContractFailure(ContractError(code=ErrorCode.INPUT_INVALID,
        message='未找到符合当前条件的更便宜营地，原方案已保留。',
        context={'revision_outcome': 'NO_CHEAPER_CAMPSITE'}))
