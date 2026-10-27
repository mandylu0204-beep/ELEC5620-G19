"""Opt-in, bounded logistics-only diagnostic; original database is read-only.

Default is an offline preflight. --allow-model authorises at most three campus
HTTP requests, without HTTP retries, planning, safety or business persistence.
Only structural diagnostics and aggregate usage are written to a new var file.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.contracts.dto import ConfirmedContext, LogisticsInput, RunScope, VersionContext
from app.contracts.errors import ContractFailure
from app.llm.client import CampusModelClient
from app.llm.config import CampusModelSettings
from app.llm.logistics_agent import LogisticsAgent


class BoundedClient(CampusModelClient):
    def __init__(self, settings):
        if settings.max_attempts != 1 or settings.max_turns != 3:
            raise ValueError('Diagnostic settings must enforce one attempt and three turns')
        super().__init__(settings)
        self.calls = 0
        self.usage = {}

    async def complete(self, messages):
        if self.calls >= 3:
            raise RuntimeError('Diagnostic request budget exhausted')
        self.calls += 1
        response = await super().complete(messages)
        for key, value in response.usage.items():
            self.usage[key] = self.usage.get(key, 0) + value
        return response


def prepare(database, run_id, snapshot):
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro', uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        version = connection.execute('''SELECT v.id,v.plan_id,v.content,rv.fingerprint FROM run_versions rv
            JOIN versions v ON v.id=rv.version_id AND v.plan_id=rv.plan_id WHERE rv.run_id=?''', (run_id,)).fetchone()
    if row is None or version is None or row['plan_id'] != version['plan_id']:
        raise RuntimeError('Owned saved run/version association missing')
    scope = RunScope.model_validate_json(row['scope'])
    confirmed = ConfirmedContext.model_validate_json(row['confirmed_context'])
    if (row['status'] != 'FAILED' or row['stage'] != 'ASSESSING_LOGISTICS'
            or scope.run_id != run_id or scope.plan_id != row['plan_id']
            or scope.request_id != row['request_id'] or confirmed.request_id != scope.request_id
            or scope.dataset_context != confirmed.dataset_context or scope.demo_context != confirmed.demo_context):
        raise RuntimeError('Saved input identity mismatch')
    dataset = SyntheticDatasetV2Adapter(snapshot).load(expected_context=scope.dataset_context)
    source = LogisticsInput(version_context=VersionContext(plan_id=version['plan_id'],plan_version_id=version['id'],
        run_id=run_id,input_fingerprint=version['fingerprint']),saved_itinerary=json.loads(version['content']),
        confirmed_requirements=confirmed.requirements,profile_snapshot=confirmed.profile_snapshot,demo_context=confirmed.demo_context)
    seed = json.loads(scope.dataset_context.selection_config['a_logistics_identity_seed'])
    local = CampusModelSettings()
    # Explicit defaults (including optional None) prevent shell environment
    # options from silently overriding an omitted saved configuration field.
    public = {key: field.default for key,field in CampusModelSettings.model_fields.items() if key != 'api_key'}
    public.update({key: value for key,value in seed['model_client'].items() if key in public})
    public.update(max_attempts=1,max_turns=3)
    settings = CampusModelSettings(_env_file=None, api_key=local.api_key, **public)
    client = BoundedClient(settings)
    client.validate_configuration()
    config = SimpleNamespace(context=scope.dataset_context)
    agent = LogisticsAgent(dataset,client,workflow_configuration=config)
    # Diagnostics alone do not change the protocol. Refuse to claim an exact
    # reproduction after a later prompt/schema repair has changed its identity.
    if agent.identity['prompt_sha256'] != seed['prompt_sha256']:
        raise RuntimeError('Current prompt differs from saved protocol; use a new explicit validation case')
    agent._input(source)
    facts = agent._facts(source)
    return agent, client, source, {'source_run_id':run_id,'dataset_version':scope.dataset_context.dataset_version,
        'kind':'LOGISTICS_ONLY_DIAGNOSTIC','business_persistence':False,'raw_responses_saved':False,
        'max_http_requests':3,'max_attempts':1,'max_turns':3,
        'same_source_input_and_dataset':True,'saved_protocol_matches':True,
        'configuration_overrides':['max_attempts','max_turns'],
        'gear_items':len(facts.gear_checklist),'cost_lines':len(facts.cost_breakdown)}


async def probe(agent,client,source,report):
    try:
        outcome = await agent.assess_with_trace(source)
        report.update(status='VALIDATED_NOT_SAVED',turns=outcome.trace.turns,
            outcome=outcome.assessment.outcome.value,validation_passed=True)
    except ContractFailure as exc:
        allowed = {'diagnostic_version','failure_stage','validation_errors','json_line','json_column',
            'role','logistics_turn','elapsed_ms','response_bytes','http_attempts','http_status','cost_priority_diagnostics'}
        report.update(status='REJECTED',error_code=exc.error.code.value,
            diagnostics={key:value for key,value in exc.error.context.items() if key in allowed})
    report.update(http_requests=client.calls,reported_successful_response_usage=client.usage)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--allow-model',action='store_true')
    args = parser.parse_args()
    if args.allow_model:
        if not args.output or not args.output.resolve().is_relative_to((ROOT/'var').resolve()):
            parser.error('Live diagnostics require a new output below project var/')
        if args.output.exists() or not args.output.parent.is_dir():
            parser.error('Output must be new and its parent must already exist')
    try:
        agent, client, source, report = prepare(args.database,args.run_id,args.snapshot)
        if args.allow_model:
            report = asyncio.run(probe(agent,client,source,report))
            with args.output.open('x',encoding='utf-8') as destination:
                json.dump(report,destination,ensure_ascii=False,indent=2)
                destination.write('\n')
        else:
            report.update(status='OFFLINE_PREFLIGHT',http_requests=0)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        # Exception text can contain validated input or paths. Never print it.
        print(json.dumps({'status':'PREFLIGHT_OR_PROBE_FAILED','error_type':type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
