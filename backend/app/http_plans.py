from fastapi import APIRouter, Depends, Request

from .auth import User
from .http_accounts import current_user, writing_user
from .storage.finalisation import FinaliseInput

router = APIRouter(prefix='/api/v1')


@router.post('/plans/{plan_id}/finalise')
def finalise(plan_id: str, body: FinaliseInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.finalisation.submit(user, plan_id, body)


@router.get('/plans/{plan_id}/finals/{final_id}')
def final_snapshot(plan_id: str, final_id: str, request: Request, user: User = Depends(current_user)):
    return request.app.state.finalisation.detail(user, plan_id, final_id)


@router.get('/plans/{plan_id}')
def plan_detail(plan_id: str, request: Request, run_id: str | None = None, user: User = Depends(current_user)):
    return request.app.state.plan_queries.detail(user, plan_id, run_id)


@router.get('/runs/{run_id}')
def run_detail(run_id: str, request: Request, user: User = Depends(current_user)):
    return request.app.state.plan_queries.run(user, run_id)
