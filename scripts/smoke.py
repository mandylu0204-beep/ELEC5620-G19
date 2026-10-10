"""Live local deployment check using an isolated DB and owned service processes.

Tests HTTP serving/proxy/persistence, not browser rendering or B business rules.
"""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), urllib.request.ProxyHandler({}))
        self.csrf = None

    def call(self, path, method='GET', body=None, expected=200, headers=None):
        request_headers = {'Content-Type':'application/json', **(headers or {})}
        if method != 'GET':
            request_headers['X-CampMate-Client'] = '1'
            if self.csrf:
                request_headers['X-CSRF-Token'] = self.csrf
        request = urllib.request.Request(self.base+path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=request_headers)
        try:
            response = self.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                raise AssertionError(f'{method} {path}: expected {expected}, got {response.status}')
            data = response.read()
            return json.loads(data) if data and response.headers.get('Content-Type','').startswith('application/json') else data.decode()

    def login(self, username, password):
        data = self.call('/api/v1/auth/login','POST',{'username':username,'password':password})
        self.csrf = data['csrf_token']
        return data['user']


@contextmanager
def services(folder, backend_port, frontend_port, database):
    marker = folder / ('stop-'+uuid4().hex)
    environment = {key:value for key,value in os.environ.items() if not key.startswith('CAMPMATE_') and key != 'PYTHONPATH'}
    environment.update(CAMPMATE_EXECUTION_MODE='stub', CAMPMATE_DEMO_TODAY='2026-10-08', CAMPMATE_DATABASE_PATH=str(database), CAMPMATE_DATASET_PATH=str(ROOT/'data/synthetic_demo'), CAMPMATE_SEED_DEMO_ACCOUNTS='true', CAMPMATE_SECURE_COOKIES='false')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with (folder/'services.log').open('a', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable,str(ROOT/'scripts/dev.py'),'--backend-port',str(backend_port),'--frontend-port',str(frontend_port),'--stop-file',str(marker)],cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        try:
            deadline = time.monotonic()+45
            backend = Client(f'http://127.0.0.1:{backend_port}')
            frontend = Client(f'http://127.0.0.1:{frontend_port}')
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Startup failed; inspect services.log')
                try:
                    if backend.call('/api/v1/health/ready')['status']=='ready' and '<div id="root"></div>' in frontend.call('/'):
                        break
                except (OSError, ValueError, AssertionError):
                    pass
                if time.monotonic()>deadline:
                    raise RuntimeError('Services did not become ready within 45 seconds')
                time.sleep(0.25)
            yield backend, frontend
        finally:
            marker.touch()
            code = process.wait(timeout=20)
            if code != 0:
                raise RuntimeError(f'Supervisor exited with {code}; inspect services.log')


def run(args):
    folder = ROOT/'var'/('deployment-smoke-'+uuid4().hex)
    folder.mkdir(parents=True)
    database = folder/'campmate.sqlite3'
    passed = []
    report = {'scope':'A local HTTP deployment smoke; B workflow and browser rendering not tested',
        'root':str(ROOT),'python':sys.version.split()[0],'platform':platform.platform(),'steps':passed,'status':'RUNNING'}
    manifest = ROOT/'PACKAGE_MANIFEST.json'
    report['package_commit'] = json.loads(manifest.read_text(encoding='utf-8'))['commit'] if manifest.exists() else None
    try:
        assert Path(sys.prefix).resolve()==(ROOT/'.venv').resolve(), 'Run smoke using this project .venv interpreter'
        imported=subprocess.check_output([sys.executable,'-c','import app; print(app.__file__)'],cwd=ROOT/'backend',text=True).strip()
        assert Path(imported).resolve()==(ROOT/'backend/app/__init__.py').resolve(), 'Backend import points outside this package'
        passed.append('Fresh project interpreter and local backend import path')
        with services(folder,args.backend_port,args.frontend_port,database) as (backend,frontend):
            meta = frontend.call('/api/v1/meta')
            assert meta['execution_mode']=='stub' and not meta['features']['planning']
            assert '<div id="root"></div>' in frontend.call('/request')
            assert 'createRoot' in frontend.call('/src/main.tsx')
            passed.append('Frontend SPA/module serving and API proxy; stub scope retained')
            backend.call('/api/v1/plans',expected=401)
            user=backend.login('camper.a','CampMate-A-2026!')
            assert user['role']=='CAMPER'
            profile=backend.call('/api/v1/profile','PUT',{'profile':{'group_size':2},'expected_revision':0})
            assert profile['revision']==1
            context=backend.call('/api/v1/request-context')
            region=context['supported_destinations'][0]
            draft=backend.call('/api/v1/requests','POST',{'raw_text':'Independent clean-install smoke request; explicit fields only.','explicit_fields':{'destination':region,'start_date':'2026-10-20','duration_nights':2,'budget_cents':10000}},expected=201)
            path='/api/v1/requests/'+draft['request_id']
            summary=backend.call(path+'/interpret','POST',{'expected_revision':draft['revision']})
            assert summary['status']=='AWAITING_CONFIRMATION'
            command={'expected_revision':summary['revision'],'command_key':uuid4().hex,'acknowledged':True}
            confirmed=backend.call(path+'/confirm','POST',command)
            assert confirmed['status']=='CONFIRMED' and confirmed['confirmed_context']['requirements']['duration_days']==3
            assert backend.call(path+'/confirm','POST',command)==confirmed
            passed.append('Camper login, profile, request analysis/confirmation and same-key replay')
            unauthorized=Client(backend.base);unauthorized.login('camper.b','CampMate-B-2026!')
            unauthorized.call(path,expected=404)
            founder=Client(backend.base);founder.login('founder','CampMate-Founder-2026!')
            founder.call(path,expected=403)
            assert founder.call('/api/v1/review-queue')=={'reviews':[]}
            passed.append('Anonymous, other Camper and Founder request access guards')
            # The deployment check never seeds fake plans as real Agent outputs.
            assert backend.call('/api/v1/plans')=={'plans':[]}
        with closing(sqlite3.connect(database)) as connection:
            assert [row[0] for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')]==[1,2,3,4,5]
        with services(folder,args.backend_port,args.frontend_port,database) as (restarted,_):
            restarted.login('camper.a','CampMate-A-2026!')
            assert restarted.call(path)==confirmed
            assert restarted.call('/api/v1/profile')==profile
            passed.append('Service restart, migrations 1–5 and exact saved request/profile recovery')
            restarted.call('/api/v1/auth/logout','POST',expected=204)
            restarted.call('/api/v1/auth/me',expected=401)
            passed.append('Logout invalidates the session')
        for port in (args.backend_port,args.frontend_port):
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',port))
        passed.append('Owned services stopped and both ports released')
        report['status']='PASSED'
    except Exception as error:
        report.update(status='FAILED',error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['checked_at']=datetime.now(timezone.utc).isoformat()
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'status':report['status'],'report':str(folder/'report.json'),'passed_steps':len(passed)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend-port',type=int,default=18010)
    parser.add_argument('--frontend-port',type=int,default=15180)
    args=parser.parse_args()
    try:
        run(args)
    except Exception as error:
        print(f'Smoke failed: {error}',file=sys.stderr)
        raise SystemExit(1)
