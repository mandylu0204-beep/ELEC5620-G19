from fastapi import APIRouter, Depends, Request

from .auth import User
from .http_accounts import current_user, writing_user
from .storage.reviews import ReviewInput
from .application.presentation import plan_response

router = APIRouter(prefix='/api/v1')


@router.get('/review/{plan_id}')
def detail(plan_id: str, request: Request, user: User = Depends(current_user)):
    return plan_response(request.app.state.reviews.detail(user, plan_id), user)


@router.post('/review/{plan_id}')
def submit(plan_id: str, body: ReviewInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.reviews.submit(user, plan_id, body)
