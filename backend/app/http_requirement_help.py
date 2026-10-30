from fastapi import APIRouter, Depends, Request
from .auth import User
from .http_accounts import current_user, writing_user
from .storage.requirement_help import RequirementHelp, HelpCreate, HelpDecision, HelpAdopt

router=APIRouter(prefix='/api/v1')

def service(request):return RequirementHelp(request.app.state.database)

@router.post('/requests/{request_id}/requirement-help',status_code=201)
def create(request_id:str,body:HelpCreate,request:Request,user:User=Depends(writing_user)):
    return service(request).create(user,request_id,body)

@router.get('/requirement-help')
def queue(request:Request,history:bool=False,user:User=Depends(current_user)):
    return {'tasks':service(request).queue(user,history=history)}

@router.get('/requirement-help/{task_id}')
def read(task_id:str,request:Request,user:User=Depends(current_user)):
    return service(request).get(user,task_id)

@router.post('/requirement-help/{task_id}/decision')
def decide(task_id:str,body:HelpDecision,request:Request,user:User=Depends(writing_user)):
    return service(request).decide(user,task_id,body)

@router.post('/requirement-help/{task_id}/adopt')
def adopt(task_id:str,body:HelpAdopt,request:Request,user:User=Depends(writing_user)):
    return service(request).adopt(user,task_id,body)
