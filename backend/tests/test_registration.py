from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.config import Settings
from app.auth import verify_password

HEADERS={'X-CampMate-Client':'1'}
INPUT={'username':'New.Camper','display_name':'New camper','password':'A-test-password-2026'}


def test_registration_login_storage_isolation_and_restart(tmp_path):
    settings=Settings(_env_file=None,database_path=tmp_path/'registration.sqlite3')
    app=create_app(settings)
    with TestClient(app) as client:
        result=client.post('/api/v1/auth/register',headers=HEADERS,json=INPUT)
        assert result.status_code==201
        assert result.headers['cache-control']=='no-store'
        user=result.json()['user']
        assert user['role']=='CAMPER' and user['username']=='new.camper'
        assert 'set-cookie' not in result.headers
        assert INPUT['password'] not in result.text and 'password_hash' not in result.text
        with app.state.database.transaction(write=False) as connection:
            row=connection.execute('SELECT * FROM users WHERE id=?',(user['user_id'],)).fetchone()
            assert row['password_hash']!=INPUT['password'] and verify_password(INPUT['password'],row['password_hash'])
        assert client.get('/api/v1/auth/me').status_code==401
        session=client.post('/api/v1/auth/login',headers=HEADERS,json={'username':'NEW.CAMPER','password':INPUT['password']})
        assert session.status_code==200
        assert client.get('/api/v1/profile').json()=={'profile':None,'revision':0}
        assert client.get('/api/v1/plans').json()=={'plans':[]}
        assert client.get('/api/v1/review-queue').status_code==403
        csrf={**HEADERS,'X-CSRF-Token':session.json()['csrf_token']}
        assert client.put('/api/v1/profile',headers=csrf,json={'expected_revision':0,'profile':{'group_size':2}}).status_code==200
        client.post('/api/v1/auth/login',headers=HEADERS,json={'username':'camper.a','password':'CampMate-A-2026!'})
        assert client.get('/api/v1/profile').json()=={'profile':None,'revision':0}
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/v1/auth/login',headers=HEADERS,json={'username':INPUT['username'],'password':INPUT['password']}).status_code==200
        assert client.get('/api/v1/profile').json()['profile']['group_size']==2


def test_registration_rejects_duplicates_headers_and_privilege_fields(tmp_path):
    with TestClient(create_app(Settings(_env_file=None,database_path=tmp_path/'registration.sqlite3'))) as client:
        assert client.post('/api/v1/auth/register',json=INPUT).status_code==403
        assert client.post('/api/v1/auth/register',headers=HEADERS,json={**INPUT,'role':'FOUNDER'}).status_code==422
        assert client.post('/api/v1/auth/register',headers=HEADERS,json=INPUT).status_code==201
        assert client.post('/api/v1/auth/register',headers=HEADERS,json={**INPUT,'username':' new.CAMPER '}).status_code==409
        assert client.post('/api/v1/auth/register',headers=HEADERS,json={**INPUT,'username':'founder'}).status_code==409


@pytest.mark.parametrize('patch',[
    {'username':'ab'}, {'username':'has space'}, {'username':'../camper'},
    {'username':'x'*33}, {'password':'short'}, {'password':' '*8},
    {'password':'abcdef1!'}, {'password':'ABCDEF1!'}, {'password':'Abcdefg!'},
    {'password':'Abcdef12'}, {'password':'Abcdef1 '}, {'password':'Abcdef1💡'},
    {'password':'Abcde1!'}, {'password':'A'+'a'*254+'1!'},
    {'display_name':' '}, {'display_name':'bad\nname'},
])
def test_registration_rejects_invalid_inputs(tmp_path,patch):
    with TestClient(create_app(Settings(_env_file=None,database_path=tmp_path/'registration.sqlite3',seed_demo_accounts=False))) as client:
        result=client.post('/api/v1/auth/register',headers=HEADERS,json=INPUT|patch)
        assert result.status_code in {400,422}
        with client.app.state.database.transaction(write=False) as connection:
            assert connection.execute('SELECT count(*) FROM users').fetchone()[0]==0


@pytest.mark.parametrize('password',['Abcdef1!','A'+'a'*253+'1!'])
def test_registration_accepts_password_length_boundaries(tmp_path,password):
    with TestClient(create_app(Settings(_env_file=None,database_path=tmp_path/'registration.sqlite3',seed_demo_accounts=False))) as client:
        assert client.post('/api/v1/auth/register',headers=HEADERS,json=INPUT|{'password':password}).status_code==201
        assert client.post('/api/v1/auth/login',headers=HEADERS,json={'username':INPUT['username'],'password':password}).status_code==200
