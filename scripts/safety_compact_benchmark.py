"""Offline byte comparison only. Fake key and MockTransport, never campus HTTP."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import socket

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
import httpx
from app.adapters.synthetic_dataset_v2 import SyntheticDatasetV2Adapter
from app.llm.client import CampusModelClient
from app.llm.safety_compact import CompactSafetyToolset
from app.llm.safety_schema import canonical
from app.llm.safety_v3 import SafetyAgent as V3Agent,SafetyToolset as V3Tools
from app.llm.safety_v4 import SafetyAgent as V4Agent
from app.workflow import WorkflowConfiguration
from llm_fixtures import completion,model_settings
from test_sydney_model_safety import safety_input


async def _compare_async(case):
    dataset,config,input,baseline,selection=case
    facts3=V3Tools(input,baseline,selection=selection,workflow_context=config.context).read_safety_facts()
    tools4=CompactSafetyToolset(input,baseline,selection=selection,workflow_context=config.context)
    assert tools4.expanded_facts()==facts3
    facts4=tools4.read_safety_facts()
    metrics={}
    outcomes={}
    for version,cls in (('v3',V3Agent),('v4',V4Agent)):
        requests=[];responses=[]
        def respond(request):
            requests.append(request.content)
            body=json.loads(request.content)
            results=[json.loads(item['content'][12:]) for item in body['messages']
                if item['content'].startswith('TOOL_RESULT=')]
            if not results:
                action={'action':'tool','name':'read_safety_facts','arguments':{}}
            else:
                facts=results[0]
                advice='Review this recorded issue before departure.'
                summary='Address unresolved issues before departure.'
                if version=='v3':
                    proposal={'findings':[{'finding_key':item['finding_key'],
                        'interpretation_unverified':advice,'action_code':item['allowed_actions'][0],
                        'action_unverified':advice} for item in facts['findings']],
                        'action_priority':[item['finding_key'] for item in facts['findings']],
                        'decision_summary_unverified':summary}
                else:
                    proposal={'facts_sha256':facts['facts_sha256'],
                        'findings':[{'id':item['id'],'action':item['actions'][0],'advice':advice}
                            for item in facts['findings']],
                        'priority':[item['id'] for item in facts['findings']],'summary':summary}
                action={'action':'tool','name':'evaluate_safety_plan','arguments':proposal} if len(results)==1 else {
                    'action':'final','proposal':proposal}
            text=canonical(action);responses.append(text)
            return httpx.Response(200,json=completion(text,model='offline-byte-comparison'))
        values=model_settings(timeout_seconds=45,max_attempts=2,max_completion_tokens=4096,reasoning_effort='low')
        agent=cls(dataset,CampusModelClient(values,transport=httpx.MockTransport(respond)),workflow_configuration=config)
        outcomes[version]=await agent.assess_safety_with_trace(input)
        metrics[version]={'serialized_http_request_bytes':[len(raw) for raw in requests],
            'request_sha256':[hashlib.sha256(raw).hexdigest() for raw in requests],
            'mock_action_utf8_bytes':[len(text.encode()) for text in responses],
            'facts_utf8_bytes':len(canonical(facts3 if version=='v3' else facts4).encode())}
    assert outcomes['v3'].assessment==outcomes['v4'].assessment==baseline
    assert outcomes['v3'].plan==outcomes['v4'].plan
    old,new=metrics['v3'],metrics['v4']
    reductions={name:round(100*(1-b/a),2) for name,a,b in (
        ('second_http_body_percent',old['serialized_http_request_bytes'][1],new['serialized_http_request_bytes'][1]),
        ('facts_percent',old['facts_utf8_bytes'],new['facts_utf8_bytes']),
        ('mock_evaluation_action_percent',old['mock_action_utf8_bytes'][1],new['mock_action_utf8_bytes'][1]))}
    assert all(value>0 for value in reductions.values())
    return {'v3':old,'v4':new,'reduction':reductions,'same_complete_assessment':True,
        'same_complete_expanded_advice':True,'lossless_fact_projection':True,
        'findings_retained':len(facts3['findings']),'facts_retained':len(facts3['fact_catalog']),
        'latency_or_token_improvement':'NOT_MEASURED_NO_REAL_MODEL',
        'actual_campus_calls':0,'fake_usage_not_reported':True}


def fixture():
    dataset=SyntheticDatasetV2Adapter(ROOT/'data/sydney_surrounds_v2_2').load()
    config=WorkflowConfiguration(dataset)
    binding=SimpleNamespace(agent=SimpleNamespace(dataset=dataset,workflow_configuration=config))
    input,baseline,selection=safety_input(binding)
    return dataset,config,input,baseline,selection


def compare(case=None):
    # Runner.__enter__ creates the loop first. On Windows its internal socketpair
    # may need a localhost TCP connection; this is stdlib setup, not a benchmark
    # request. Do NOT whitelist localhost once application work has started.
    def forbidden(*args,**kwargs):
        raise AssertionError('No real network is allowed in the byte benchmark')
    with asyncio.Runner() as runner:
        with patch.object(socket.socket,'connect',forbidden),patch.object(socket.socket,'connect_ex',forbidden),\
                patch.object(socket,'create_connection',forbidden),\
                patch.object(httpx.AsyncHTTPTransport,'handle_async_request',forbidden),\
                patch.object(httpx.HTTPTransport,'handle_request',forbidden):
            try:
                return runner.run(_compare_async(fixture() if case is None else case))
            finally:
                # Also keep pending-task cancellation/async-generator cleanup
                # under the guards. The outer context's close is an idempotent
                # no-op, including when fixture/model code failed or cancelled.
                runner.close()


def main():
    value=compare()
    print(json.dumps(value,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
