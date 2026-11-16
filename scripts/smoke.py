"""Live local deployment check using an isolated DB and owned service processes.

Tests HTTP serving/proxy/persistence, not browser rendering or B business rules.
"""
import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import http.cookiejar
import json
from html.parser import HTMLParser
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
            content_type=response.headers.get('Content-Type','')
            if content_type.startswith('application/pdf'):
                return data
            return json.loads(data) if data and content_type.startswith('application/json') else data.decode()

    def login(self, username, password):
        data = self.call('/api/v1/auth/login','POST',{'username':username,'password':password})
        self.csrf = data['csrf_token']
        return data['user']


@contextmanager
def services(folder, backend_port, frontend_port, database):
    marker = folder / ('stop-'+uuid4().hex)
    environment = {key:value for key,value in os.environ.items()
                   if not key.startswith(('CAMPMATE_','ELEC5620_')) and key != 'PYTHONPATH'}
    environment.update(CAMPMATE_EXECUTION_MODE='deterministic_demo',CAMPMATE_PLANNING_ENABLED='true',
        CAMPMATE_LOGISTICS_EXECUTION='rules',CAMPMATE_SAFETY_EXECUTION='rules',
        CAMPMATE_CLOCK_MODE='fixed',CAMPMATE_DEMO_TODAY='2026-11-04',
        CAMPMATE_SYNTHETIC_EVIDENCE_MODE='rolling',CAMPMATE_DATABASE_PATH=str(database),
        CAMPMATE_SNAPSHOT_CACHE_PATH=str(folder/'snapshots'),
        CAMPMATE_DATASET_PATH=str(ROOT/'data/sydney_surrounds_v2_2'),
        CAMPMATE_DATASET_SCENARIO_FILES='[]',CAMPMATE_DATASET_SELECTION='{}',
        CAMPMATE_WORKFLOW_SAFETY_CASE_IDS='[]',CAMPMATE_SEED_DEMO_ACCOUNTS='true',CAMPMATE_SECURE_COOKIES='false')
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
                    if backend.call('/api/v1/health/ready')['status']=='ready' and has_app_root(frontend.call('/')):
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


def has_app_root(html):
    class RootParser(HTMLParser):
        found=False
        def handle_starttag(self,tag,attrs):
            if tag=='div' and dict(attrs).get('id')=='root':self.found=True
    parser=RootParser();parser.feed(html)
    return parser.found


def final_command(detail):
    return {'command_key':uuid4().hex,'version_context':detail['version']['version_context'],
        'assessment_ids':[a['assessment_id'] for a in detail['assessments']],
        'expected_review_id':detail['eligibility']['valid_review_id'],
        'expected_version_revision':detail['version']['revision'],
        'expected_run_revision':detail['run']['revision'],'acknowledged':True}


def run(args):
    # Hash-named snapshots already add substantial depth. Keep the diagnostic
    # prefix short enough for extracted projects on Windows with MAX_PATH.
    folder = ROOT/'var'/('smoke-'+uuid4().hex[:12])
    folder.mkdir(parents=True,exist_ok=False)
    database = folder/'campmate.sqlite3'
    passed = []
    report = {'scope':'Isolated Sydney 2.2 rules HTTP workflow; no browser JavaScript or model acceptance',
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
            assert meta['execution_mode']=='deterministic_demo' and meta['features']['planning']
            assert meta['dataset_version']=='2.2.0'
            assert has_app_root(frontend.call('/request'))
            assert 'createRoot' in frontend.call('/src/main.tsx')
            passed.append('Frontend SPA/module serving and API proxy; Sydney rules configuration')
            backend.call('/api/v1/plans',expected=401)
            user=backend.login('camper.a','CampMate-A-2026!')
            assert user['role']=='CAMPER'
            inputs=json.loads((ROOT/'docs/demo/bonnie_vale_inputs.json').read_text(encoding='utf-8'))
            profile=backend.call('/api/v1/profile','PUT',{'profile':inputs['profile'],'expected_revision':0})
            assert profile['revision']==1
            context=backend.call('/api/v1/request-context')
            assert context['demo_today']==inputs['checking_date']
            draft=backend.call('/api/v1/requests','POST',inputs['request'],expected=201)
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
            started=backend.call(path+'/plan','POST',{'expected_request_revision':confirmed['revision'],
                'command_key':uuid4().hex},expected=202)
            plan_path='/api/v1/plans/'+started['plan_id']
            deadline=time.monotonic()+30
            while True:
                detail=backend.call(plan_path)
                if detail.get('run',{}).get('status') in {'SUCCEEDED','FAILED','CANCELLED'}:break
                if time.monotonic()>deadline:raise AssertionError('Rules planning did not reach a terminal state within 30 seconds')
                time.sleep(.2)
            assert detail['run']['status']=='SUCCEEDED'
            assert detail['version']['content']['selected_campsite_ids']==['bonnie-vale']
            by_kind={a['kind']:a['result'] for a in detail['assessments']}
            assert by_kind['LOGISTICS']['outcome']=='PASSED' and not by_kind['LOGISTICS']['clarifications']
            assert by_kind['SAFETY']['outcome']=='REVIEW' and by_kind['SAFETY']['risk_level']=='HIGH'
            assert set(by_kind['SAFETY']['data_quality'].values())=={'AVAILABLE'}
            assert {b['code'] for b in detail['eligibility']['blocking_reasons']}=={'REVIEW_REQUIRED'}
            assert not detail['finalisation_available']
            backend.call(plan_path+'/finalise','POST',final_command(detail),expected=409)
            passed.append('Rules plan, complete weather/equipment, high-risk review and preapproval save guard')
            review=founder.call('/api/v1/review/'+started['plan_id'])
            approval=founder.call('/api/v1/review/'+started['plan_id'],'POST',{
                'command_key':uuid4().hex,'version_context':review['version']['version_context'],
                'assessment_ids':[a['assessment_id'] for a in review['assessments']],
                'expected_version_revision':review['version']['revision'],'expected_run_revision':review['run']['revision'],
                'decision':'APPROVE','reason':'Isolated synthetic HTTP deployment check: current evidence and risks reviewed.'})
            assert approval['eligibility']['eligible']
            detail=backend.call(plan_path);assert detail['finalisation_available']
            final=backend.call(plan_path+'/finalise','POST',final_command(detail))
            final_path=plan_path+'/finals/'+final['final_id']
            snapshot=backend.call(final_path)
            assert backend.call(final_path+'/pdf').startswith(b'%PDF-')
            unauthorized.call(plan_path,expected=404);unauthorized.call(final_path,expected=404)
            Client(backend.base).call(final_path,expected=401)
            passed.append('Founder approval, Camper final save/PDF and final record owner isolation')
        with closing(sqlite3.connect(database)) as connection:
            assert [row[0] for row in connection.execute('SELECT version FROM schema_migrations ORDER BY version')]==list(range(1,15))
            assert connection.execute('PRAGMA quick_check').fetchone()[0]=='ok'
            assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        with services(folder,args.backend_port,args.frontend_port,database) as (restarted,_):
            restarted.login('camper.a','CampMate-A-2026!')
            assert restarted.call(path)['confirmed_context']==confirmed['confirmed_context']
            assert restarted.call('/api/v1/profile')==profile
            assert restarted.call(final_path)==snapshot
            passed.append('Service restart, migrations 1–14 and exact final/profile/confirmation readback')
            restarted.call('/api/v1/auth/logout','POST',expected=204)
            restarted.call('/api/v1/auth/me',expected=401)
            passed.append('Logout invalidates the session')
        for port in (args.backend_port,args.frontend_port):
            with socket.socket() as probe:
                if os.name != 'nt':
                    # TIME_WAIT connections do not mean a server is still running.
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
