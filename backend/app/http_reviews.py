from fastapi import APIRouter, Depends, Request, Query
from typing import Literal

from .auth import User
from .http_accounts import current_user, writing_user
from .storage.reviews import ReviewInput
from .application.presentation import plan_response

router = APIRouter(prefix='/api/v1')


@router.get('/assistance-queue')
def assistance_queue(request: Request, user: User = Depends(current_user)):
    return {'plans': request.app.state.reviews.queue(user, assistance=True)}


@router.get('/review/{plan_id}')
def detail(plan_id: str, request: Request, run_id: str | None = None, user: User = Depends(current_user)):
    return plan_response(request.app.state.reviews.detail(user, plan_id, run_id), user)


@router.post('/review/{plan_id}')
def submit(plan_id: str, body: ReviewInput, request: Request, user: User = Depends(writing_user)):
    return request.app.state.reviews.submit(user, plan_id, body)


from .storage.review_assistance import AssistanceInput, ReviewAssistance

@router.post('/review/{plan_id}/assistance')
def assistance(plan_id:str,body:AssistanceInput,request:Request,user:User=Depends(writing_user)):
    return ReviewAssistance(request.app.state.database,context_guard=request.app.state.runtime.validate_scope).submit(user,plan_id,body)

@router.get('/review-history')
def history(request:Request,decision:Literal['APPROVE','REJECT','REQUEST_REVISION']|None=None,
            offset:int=Query(0,ge=0),limit:int=Query(30,ge=1,le=100),user:User=Depends(current_user)):
    from .storage.review_history import history as read_history
    return read_history(request.app.state.database,user,decision=decision,offset=offset,limit=limit)
