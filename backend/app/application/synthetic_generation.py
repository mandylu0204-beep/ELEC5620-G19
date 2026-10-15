"""Deterministic synthetic snapshot builder shared by CLI and daily runtime.

No user input or model output participates in source generation.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from ..adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter, BUSINESS_FILES, RUNTIME_FILES
from ..agents.rules.trip_evidence import POLICY_VERSION
from ..dataset_paths import data_file_path, manifest_file_path

PROVENANCE = {'source_type':'SYNTHETIC','source_name':'CampMate Synthetic Demo Dataset v2',
              'source_date':'2026-10-07','demo_only':True}
ZONE = ZoneInfo('Australia/Sydney')

def encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()


def timestamp(day):
    return datetime.combine(day,time(0),ZONE).isoformat()


def build(original, periods, *, rolling_day=None):
    dataset = SyntheticDatasetV2Adapter(original).load()
    old_rows = json.loads(data_file_path(original,'runtime_safety_evidence.json').read_bytes())
    events = []
    for row in old_rows:
        for kind,field in [('ROAD','road_access'),('FIRE','fire')]:
            item=row[field]
            limited=(kind=='ROAD' and item['status']=='CLOSED') or (kind=='FIRE' and item['summary']=='Synthetic comprehensive no-fire restriction.')
            if limited and item['data_status']=='AVAILABLE' and item['valid_from'] and item['valid_until']:
                events.append({'kind':kind,'campsite_id':row['campsite_id'],'start':date.fromisoformat(item['valid_from']),
                    'end':date.fromisoformat(item['valid_until']),'observed_at':item['observed_at'],'origin_id':row['safety_case_id']})
        if any(any(word in text.lower() for word in ('campsite closure','campsite closed','closed campsite')) for text in row['campsite_restrictions']):
            events.append({'kind':'RESTRICTION','campsite_id':row['campsite_id'],'start':date.fromisoformat(row['valid_from']),
                'end':date.fromisoformat(row['valid_until']),'observed_at':timestamp(date.fromisoformat(row['valid_from'])-timedelta(days=1)),
                'origin_id':row['safety_case_id']})
    rows=[]
    def record(camp,kind,start,end,observed,*,state='OPEN',ban=False,closed=False,origins=()):
        key=f'trip-{camp.campsite_id}-{kind.lower()}-{start.isoformat()}-{end.isoformat()}'
        empty={'summary':None,'source_date':'unknown','status':'MISSING','data_status':'MISSING',
               'observed_at':None,'valid_from':None,'valid_until':None}
        row={'safety_case_id':key,'campsite_id':camp.campsite_id,'scenario_date':start.isoformat(),
             'valid_from':start.isoformat(),'valid_until':end.isoformat(),'weather':deepcopy(empty),
             'fire':deepcopy(empty),'road_access':{**empty,'status':'UNKNOWN'},'campsite_restrictions':[],
             'risk_tags':[],'mandatory_blockers':[],'evidence_facts':{},'active_kinds':[kind],
             'published_at':observed,'restriction_observed_at':observed if kind=='RESTRICTION' else None,
             'max_age_days':7 if kind=='WEATHER' else 45,'origin_case_ids':sorted(origins),**PROVENANCE}
        if kind=='RESTRICTION':
            row['campsite_restrictions'] = [*camp.mandatory_restrictions,*(['Synthetic campsite closure.'] if closed else [])]
        else:
            field={'WEATHER':'weather','FIRE':'fire','ROAD':'road_access'}[kind]
            summary={'WEATHER':'Mild synthetic conditions.',
                     'FIRE':'Synthetic comprehensive no-fire restriction.' if ban else 'No synthetic fire restriction.',
                     'ROAD':'road closed in synthetic scenario' if state=='CLOSED' else 'open in synthetic scenario'}[kind]
            row[field]={'summary':summary,'source_date':PROVENANCE['source_date'],'data_status':'AVAILABLE',
                        'status':state if kind=='ROAD' else 'AVAILABLE','observed_at':observed,
                        'valid_from':start.isoformat(),'valid_until':end.isoformat()}
            if kind=='WEATHER':
                row['evidence_facts']={'temperature_min_c':12,'temperature_max_c':22,'forecast_rain_mm':0,'wind_kph':10}
                if rolling_day is not None:
                    # Fixed per campsite/date, independent of user preferences,
                    # budget, itinerary and evaluation outcome. Include adverse
                    # mock conditions instead of guaranteeing a safe forecast.
                    code=int(hashlib.sha256(f'{camp.campsite_id}:{rolling_day}'.encode()).hexdigest()[:8],16)%10
                    if code==0:
                        row['weather']['summary']='Heavy rain in synthetic forecast.'
                        row['evidence_facts'].update(forecast_rain_mm=60,wind_kph=35)
                    elif code==1:
                        row['weather']['summary']='Cold synthetic conditions.'
                        row['evidence_facts'].update(temperature_min_c=3,temperature_max_c=12)
        rows.append(row)
    for camp in sorted(dataset.campsites,key=lambda value:value.campsite_id):
        for first,last in periods:
            begin,finish=date.fromisoformat(first),date.fromisoformat(last)
            if rolling_day is not None:
                record(camp,'WEATHER',rolling_day,rolling_day+timedelta(days=6),timestamp(rolling_day))
            else:
                day=begin
                while day<=finish:
                    record(camp,'WEATHER',day,min(finish,day+timedelta(days=6)),timestamp(day-timedelta(days=1)))
                    day+=timedelta(days=1)
            for kind in ('FIRE','ROAD','RESTRICTION'):
                relevant=[v for v in events if v['campsite_id']==camp.campsite_id and v['kind']==kind and v['start']<=finish and v['end']>=begin]
                if kind=='FIRE' and camp.fire_allowed is False:
                    # The campsite's permanent ban already covers this period;
                    # dated reminders must not split one unchanged source fact.
                    record(camp,kind,begin,finish,timestamp(begin-timedelta(days=1)),
                           ban=True,origins=[v['origin_id'] for v in relevant])
                    continue
                cuts={begin,finish+timedelta(days=1)}
                for event in relevant:
                    cuts.update([max(begin,event['start']),min(finish,event['end'])+timedelta(days=1)])
                points=sorted(cuts)
                for start,next_start in zip(points,points[1:]):
                    end=next_start-timedelta(days=1)
                    active=[v for v in relevant if v['start']<=end and v['end']>=start]
                    observed=max([v['observed_at'] for v in active],default=timestamp(begin-timedelta(days=1)))
                    record(camp,kind,start,end,observed,state='CLOSED' if active and kind=='ROAD' else 'OPEN',
                           ban=camp.fire_allowed is False or bool(active and kind=='FIRE'),
                           closed=bool(active and kind=='RESTRICTION'),origins=[v['origin_id'] for v in active])
    content={}
    for name in (*BUSINESS_FILES,*RUNTIME_FILES):
        content['data/'+name]=data_file_path(original,name).read_bytes()
    index=encode(sorted(rows,key=lambda row:row['safety_case_id']))
    content['data/runtime_safety_evidence.json']=index
    content['data/synthetic_safety_scenarios.json']=index
    # Original missing/stale/conflicting worlds remain explicit test-only inputs,
    # never read by the production Adapter or normal evidence index.
    content['tests/fixtures/legacy_runtime_safety_evidence.json']=encode(old_rows)
    coverage={'dataset_version':'2.1.0','periods':periods,'weather_horizon_days':7,'weather_max_age_days':7,
              'nonweather_max_age_days':45,'selection_policy':POLICY_VERSION,
              'campsites':[v.campsite_id for v in sorted(dataset.campsites,key=lambda v:v.campsite_id)],
              'record_count':len(rows),'kinds':['WEATHER','FIRE','ROAD','RESTRICTION'],
              'retained_restrictions':[{**v,'start':v['start'].isoformat(),'end':v['end'].isoformat()} for v in events],
              'coverage_limit':'Single-record full-trip coverage; partial intervals are reported, not spliced. Weather must already be published/observed at demo_today.',
              'provenance_note':'v2 is the source family/original synthetic creation date; this is an independent 2.1.0 release, not a modified 2.0.0 seal.'}
    content['coverage.json']=encode(coverage)
    content['README.md']=('''# CampMate Synthetic Demo Dataset 2.1.0

Independent synthetic snapshot; never use for real travel or safety decisions.
Sealed 2.0.0 is unchanged. Business rules, campsites, equipment and fees are
byte-identical to 2.0.0. Normal safety indices are replaced, not appended with
mutually exclusive test worlds. See coverage.json for exact dates and retained
closures/no-fire facts. All dates are finite; weather forecasts cover at most
seven days and future observations cannot be used early. Missing/stale/conflict
fixtures are isolated under tests/fixtures and are not loaded in normal runs.

Use workflow_safety_case_ids=[] and dataset_scenario_files=[] with this package.
Changing package/policy/check clock requires a newly registered run. Existing
SQLite schema and shared contracts remain 1.0; there is no database migration.
Do not copy 2.1 files over the sealed synthetic_demo_v2 directory.

Read-only validation from the repository root:
    .venv/bin/python scripts/validate_trip_dataset.py
''').encode()
    manifest={'dataset_version':'2.1.0','revision_date':'2026-10-15','provenance':PROVENANCE,
              'evidence_selection_policy':POLICY_VERSION,'derived_from':'synthetic_demo_v2/2.0.0',
              'original_manifest_sha256':hashlib.sha256(manifest_file_path(original).read_bytes()).hexdigest(),
              'files_sha256':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(content.items())}}
    if rolling_day is not None:
        manifest.update(generated_on=rolling_day.isoformat(),generator_policy='synthetic-daily-v1',
            derived_from='synthetic_demo_v2_1/2.1.0',
            generation_notice='Generated simulation, not observed weather or verified real-world road conditions.')
        # The sealed CLI's historical README/fixtures are irrelevant to runtime.
        content.pop('tests/fixtures/legacy_runtime_safety_evidence.json',None)
        content['README.md']=b'Generated synthetic simulation only. Never use for real travel.\n'
        manifest['files_sha256']={name:hashlib.sha256(data).hexdigest() for name,data in sorted(content.items())}
    content['manifest.json']=encode(manifest)
    return content
