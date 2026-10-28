from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, StrictInt, model_validator, field_validator

from .auth import COOKIE_NAME, User, fail
from .contracts.base import ContractModel
from .contracts.dto import ProfileSnapshot
from .contracts.enums import ErrorCode


class LoginInput(ContractModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class RegisterInput(ContractModel):
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=256)


class ProfileInput(ContractModel):
    profile: ProfileSnapshot
    expected_revision: StrictInt = Field(ge=0)

    @field_validator('profile')
    @classmethod
    def normalize_known_accessibility(cls,profile):
        from .application.requirement_choices import recognized
        return profile.model_copy(update={'accessibility_requirements':[recognized(value,'accessibility_requirements') or value for value in profile.accessibility_requirements]})

    @model_validator(mode='after')
    def meaningful_equipment(self):
        if any(not item.item_key.strip() or not item.label.strip() or not item.unit.strip() for item in self.profile.equipment):
            raise ValueError('装备类别、名称和单位不能留空。')
        if self.profile.has_children is True and self.profile.children_count == 0:
            raise ValueError('有儿童与儿童人数为零冲突，请修改。')
        return self


def write_header(request: Request):
    # Cross-origin forms cannot set this header. No CORS permission is granted.
    if request.headers.get('X-CampMate-Client') != '1':
        fail(ErrorCode.FORBIDDEN, '请通过 CampMate 页面提交请求。')


def current_user(request: Request) -> User:
    return request.app.state.auth.authenticate(request.cookies.get(COOKIE_NAME))


def writing_user(request: Request) -> User:
    write_header(request)
    return request.app.state.auth.authenticate(request.cookies.get(COOKIE_NAME), request.headers.get('X-CSRF-Token'), write=True)


router = APIRouter(prefix='/api/v1')


@router.post('/auth/register', status_code=201)
def register(body: RegisterInput, request: Request, response: Response):
    write_header(request)
    user = request.app.state.auth.register(body.username, body.display_name, body.password)
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user.public()}


@router.post('/auth/login')
def login(body: LoginInput, request: Request, response: Response):
    write_header(request)
    auth = request.app.state.auth
    user, token, csrf = auth.login(body.username, body.password, request.cookies.get(COOKIE_NAME))
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite='lax', secure=request.app.state.settings.secure_cookies, max_age=auth.session_seconds, path='/api/v1')
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user.public(), 'csrf_token': csrf}


@router.get('/auth/me')
def me(request: Request, response: Response, user: User = Depends(current_user)):
    response.headers['Cache-Control'] = 'no-store'
    return {'user': user.public(), 'csrf_token': request.app.state.auth.csrf_for(request.cookies[COOKIE_NAME])}


@router.post('/auth/logout', status_code=204)
def logout(request: Request, user: User = Depends(writing_user)):
    request.app.state.auth.logout(request.cookies[COOKIE_NAME])
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path='/api/v1', httponly=True, samesite='lax', secure=request.app.state.settings.secure_cookies)
    return response


@router.get('/profile')
def profile(request: Request, user: User = Depends(current_user)):
    return request.app.state.repository.get_profile(user)


@router.put('/profile')
def save_profile(body: ProfileInput, request: Request, user: User = Depends(writing_user)):
    # Canonicalize known UI aliases only when the owner explicitly saves a
    # profile. Historical confirmed snapshots are never rewritten.
    profile = body.profile
    experience = profile.experience_level
    transport = profile.transport.transport_type
    levels = {value.casefold(): value for value in ('BEGINNER', 'INTERMEDIATE', 'EXPERIENCED', 'ADVANCED')}
    modes = {value.casefold(): value for value in ('CAR', 'PUBLIC_TRANSPORT', 'WALKING', 'OTHER')}
    profile = profile.model_copy(update={
        'experience_level': levels.get(experience.strip().casefold(), experience) if experience else experience,
        'transport': profile.transport.model_copy(update={
            'transport_type': modes.get(transport.strip().casefold(), transport) if transport else transport}),
    })
    return request.app.state.repository.save_profile(user, profile, body.expected_revision)


@router.get('/plans')
def plans(request: Request, user: User = Depends(current_user)):
    return {'plans': request.app.state.plan_queries.list(user)}


@router.get('/plans/{plan_id}/versions')
def versions(plan_id: str, request: Request, user: User = Depends(current_user)):
    return {'versions': request.app.state.repository.history(user, plan_id)}


@router.get('/review-queue')
def reviews(request: Request, user: User = Depends(current_user)):
    return {'reviews': request.app.state.reviews.queue(user)}
