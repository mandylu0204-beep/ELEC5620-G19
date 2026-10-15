"""Read-only release/import/coverage checks. Never reseals or calls a model."""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.application.datasets import inspect_dataset
from app.config import Settings
from app.contracts.dto import ConfirmedRequirements, DemoContext


def validate(root):
    manifest=json.loads((root/'manifest.json').read_bytes())
    checks=[]
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
    for name,expected in manifest['files_sha256'].items():
        path=(root/name).resolve()
        check('sealed:'+name,path.is_relative_to(root.resolve()) and hashlib.sha256(path.read_bytes()).hexdigest()==expected)
    original=ROOT/'data/synthetic_demo_v2'
    check('unchanged_v2_manifest',hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest()==manifest['original_manifest_sha256'])
    settings=Settings(_env_file=None,dataset_path=root)
    descriptor=inspect_dataset(settings)
    dataset=SyntheticDatasetV2Adapter(root).load(expected_context=descriptor.context)
    check('adapter_matches_registered_bytes',dataset.context.file_digests==descriptor.context.file_digests)
    check('independent_version',dataset.context.dataset_version=='2.1.0')
    for name in ['synthetic_campsites.csv','synthetic_gear_rules.csv','synthetic_cost_reference.csv',
                 'synthetic_profiles.json','synthetic_requests.json','runtime_requests.json']:
        check('unchanged_business:'+name,(root/'data'/name).read_bytes()==(original/'data'/name).read_bytes())
    check('test_worlds_not_consumed',not any('tests' in name or 'fixtures' in name for name in dataset.context.file_digests))
    coverage=json.loads((root/'coverage.json').read_bytes())
    check('all_ten_campsites',len(dataset.campsites)==10 and set(coverage['campsites'])=={v.campsite_id for v in dataset.campsites})
    check('registered_record_count',len(dataset.safety_cases)==coverage['record_count'])
    queries,weather_ok=0,True
    for first,last in coverage['periods']:
        day,end=date.fromisoformat(first),date.fromisoformat(last)
        while day+timedelta(days=2)<=end:
            req=ConfirmedRequirements(destination='CampMate Demo Region',start_date=day,end_date=day+timedelta(days=2),
                duration_nights=2,duration_days=3,budget_cents=32000)
            demo=DemoContext(mode='deterministic_demo',demo_today=day-timedelta(days=1),dataset_version='2.1.0')
            for camp in dataset.campsites:
                selection=dataset.trip_evidence_selector.resolve_trip_evidence(req,[camp.campsite_id],demo)
                weather_ok &= not any(item.kind=='WEATHER' for item in selection.coverage_issues)
                weather_ok &= selection.weather_facts_by_campsite[camp.campsite_id].temperature_min_c is not None
                queries+=1
            day+=timedelta(days=1)
    check('finite_two_night_weather_coverage_at_publication_clock',weather_ok)
    return {'kind':'STATIC_RELEASE_IMPORT_AND_COVERAGE_CHECKS_NOT_HTTP_OR_LLM_ACCEPTANCE',
            'dataset_version':'2.1.0','periods':coverage['periods'],'weather_queries':queries,
            'passed':sum(item['passed'] for item in checks),'failed':sum(not item['passed'] for item in checks),'checks':checks}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/synthetic_demo_v2_1')
    parser.add_argument('--report',type=Path,help='Optional NEW JSON output; refuses to overwrite.')
    args=parser.parse_args()
    result=validate(args.dataset.resolve())
    if args.report:
        with args.report.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
    print(json.dumps({key:value for key,value in result.items() if key!='checks'},ensure_ascii=False))
    return 1 if result['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
