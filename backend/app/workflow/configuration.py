"""Immutable, fingerprinted workflow choices. Never infer evidence coverage."""
import hashlib
import json

from ..adapters import ADAPTER_VERSION, SyntheticDataset
from ..contracts.dto import DatasetContext, ScenarioContext
from ..contracts.enums import AllowedAction, ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..agents.rules.common import RULES_VERSION

WORKFLOW_VERSION = 'b03-checkpoint-1'


def failure(code, message, *, recoverable=False):
    action = AllowedAction.CONTACT_OPERATOR
    if code in {ErrorCode.INPUT_INVALID, ErrorCode.REQUEST_NOT_CONFIRMED}:
        action = AllowedAction.EDIT_INPUT
    elif code in {ErrorCode.STALE_CONTEXT, ErrorCode.VERSION_CONFLICT}:
        action = AllowedAction.REFRESH
    return ContractFailure(ContractError(
        code=code, message=message, recoverable=recoverable,
        allowed_actions=[AllowedAction.RETRY] if recoverable else [action],
    ))


class WorkflowConfiguration:
    """A registers context BEFORE starting a run; B cannot alter that scope.

    Optional explicit ScenarioContext supplements are snapshotted and hashed as
    canonical DTO bytes (not claimed to be the hash of an original source file).
    No test files, expected labels or implicit fixture loader are involved.
    """
    def __init__(self, dataset: SyntheticDataset, *, safety_case_ids=(), feedback=None, scenarios=()):
        ids = tuple(safety_case_ids)
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise failure(ErrorCode.INPUT_INVALID, 'Safety case IDs must be unique, explicit strings.')
        if feedback is not None and (not isinstance(feedback, str) or not feedback.strip()):
            raise failure(ErrorCode.INPUT_INVALID, 'Revision feedback must be nonblank text or null.')
        selected = [dataset.get_safety(key).scenario_context for key in ids]
        supplements = [ScenarioContext.model_validate(value).model_copy(deep=True) for value in scenarios]
        selected.extend(supplements)
        if len({value.scenario_id for value in selected}) != len(selected):
            raise failure(ErrorCode.INPUT_INVALID, 'Scenario IDs must be unique across sources.')
        for value in selected:
            if not value.campsite_ids or len(set(value.campsite_ids)) != len(value.campsite_ids):
                raise failure(ErrorCode.INPUT_INVALID, 'Scenario campsite coverage must be explicit and unique.')
            for key in value.campsite_ids:
                dataset.get_campsite(key)
        fixture_digests = {}
        if supplements:
            payload = json.dumps([item.model_dump(mode='json') for item in supplements], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            fixture_digests['b03-explicit-scenarios.canonical.json'] = hashlib.sha256(payload).hexdigest()
        base = dataset.context
        self._context = DatasetContext(
            dataset_version=base.dataset_version, file_digests=base.file_digests,
            fixture_digests=fixture_digests,
            selection_config={
                'safety_case_ids': json.dumps(ids, separators=(',', ':')),
                'supplement_scenario_ids': json.dumps([item.scenario_id for item in supplements], separators=(',', ':')),
                'revision_feedback': feedback or '',
            },
            rules_version=f'{base.rules_version}/{ADAPTER_VERSION}/{RULES_VERSION}/{WORKFLOW_VERSION}',
        )
        self._scenarios = tuple(selected)
        self._feedback = feedback

    @property
    def context(self):
        return self._context.model_copy(deep=True)

    @property
    def feedback(self):
        return self._feedback

    def scenario_for(self, campsite_ids):
        selected = set(campsite_ids)
        relevant = [value for value in self._scenarios if selected.intersection(value.campsite_ids)]
        # Each Evidence retains its own interval. The enclosing interval is the
        # conservative intersection, NOT an invented trip-duration template.
        start = max(value.valid_from for value in relevant) if relevant and all(value.valid_from is not None for value in relevant) else None
        end = min(value.valid_to for value in relevant) if relevant and all(value.valid_to is not None for value in relevant) else None
        evidence = [item.model_copy(deep=True) for value in relevant for item in value.evidence if any(ref.record_id in selected for ref in item.source_refs)]
        return ScenarioContext(
            scenario_id='b03-selected-safety', campsite_ids=list(campsite_ids),
            valid_from=start, valid_to=end, evidence=evidence,
            template_id=relevant[0].scenario_id if len(relevant) == 1 else None,
        )
