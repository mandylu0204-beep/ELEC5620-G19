from fastapi import APIRouter, Depends, Request

from .auth import User
from .http_accounts import current_user

router = APIRouter(prefix='/api/v1')


@router.get('/plans/{plan_id}')
def plan_detail(plan_id: str, request: Request, run_id: str | None = None, user: User = Depends(current_user)):
    return request.app.state.plan_queries.detail(user, plan_id, run_id)


@router.get('/runs/{run_id}')
def run_detail(run_id: str, request: Request, user: User = Depends(current_user)):
    return request.app.state.plan_queries.run(user, run_id)
