"""Candidate-only deterministic preparation checks; no dispatcher or writes."""
import json

from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator

from .application.cooking_preparation import preview
from .auth import User, fail, require_role
from .contracts.base import ContractModel, Identifier
from .contracts.dto import EquipmentItem, RunScope
from .contracts.enums import ErrorCode
from .http_accounts import writing_user
from .storage.repository import Repository
from .storage.requests import RequestRepository
from .storage.trip_series import require_current, validate_successor


class CookingPreviewInput(ContractModel):
    plan_id: Identifier | None = None
    request_id: Identifier | None = None
    equipment: list[EquipmentItem] = Field(max_length=200)

    @model_validator(mode='after')
    def one_origin(self):
        if (self.plan_id is None) == (self.request_id is None):
            raise ValueError('Exactly one owned plan or request is required.')
        return self


router = APIRouter(prefix='/api/v1')


@router.post('/preparation/cooking')
def cooking_preview(body: CookingPreviewInput, request: Request, user: User = Depends(writing_user)):
    require_role(user, 'CAMPER')
    scope = None
    with request.app.state.database.transaction(write=False) as connection:
        if body.plan_id:
            plan = Repository.own_plan(connection, user, body.plan_id)
            require_current(connection, plan)
            run = connection.execute('SELECT scope,confirmed_context FROM runs WHERE id=? AND plan_id=?',
                (plan['active_run_id'], plan['id'])).fetchone()
            if not run:
                fail(ErrorCode.INVALID_STATE, 'No confirmed requirements available for preparation review.')
            scope = RunScope.model_validate_json(run['scope'])
            requirements = json.loads(run['confirmed_context'])['requirements']
        else:
            row = RequestRepository.own(connection, user, body.request_id)
            validate_successor(connection, user, body.request_id)
            summary = connection.execute('SELECT result FROM request_summaries WHERE request_id=?', (body.request_id,)).fetchone()
            requirements = (json.loads(row['confirmed_context'])['requirements'] if row['confirmed_context']
                else (json.loads(summary['result'])['extracted_requirements'] if summary and summary['result'] else json.loads(row['payload'])))
    runtime = request.app.state.runtime
    snapshot = runtime.for_scope(scope) if scope else runtime.resolve()
    if scope and snapshot.dataset != scope.dataset_context:
        fail(ErrorCode.STALE_CONTEXT, 'Could not read the source plan rules. Review the current trip.')
    dataset = getattr(snapshot.agent, 'dataset', None)
    if dataset is None:
        fail(ErrorCode.INVALID_STATE, 'This mode does not provide a preparation rules precheck.')
    return preview(dataset, requirements, [item.model_dump(mode='json') for item in body.equipment])
