from copy import deepcopy
from io import BytesIO
import re
from pypdf import PdfReader
from app.application.visitor_copy import visitor_text
from app.application.final_pdf import render_final_pdf
from plan_fixtures import create
from test_finalisation import final_client, command


def test_export_text_preserves_hazards_and_review_requirement():
    for original, required in [('Heavy rain in synthetic forecast.', 'Heavy rain'),
            ('Synthetic data only; escalate to authorised Founder before use.', 'authorised Founder'),
            ('Road closed in synthetic scenario.', 'Road closed')]:
        value=visitor_text(original)
        assert required in value
        assert not re.search(r'synthetic|simulated|demo data',value,re.I)


def test_final_pdf_omits_simulation_copy_without_mutating_saved_record(final_client,tmp_path):
    client,app,camper,headers=final_client
    scope,_=create(app.state.repository,camper,'visitor-copy-final','complete')
    path='/api/v1/plans/'+scope.plan_id
    detail=client.get(path).json()
    final=client.post(path+'/finalise',headers=headers,json=command(detail)).json()
    final_path=path+'/finals/'+final['final_id']
    original=client.get(final_path).json()
    saved=deepcopy(original['final_record'])
    safety=next(a['result'] for a in saved['assessments'] if a['kind']=='SAFETY')
    safety['hazards']=['Heavy rain in synthetic forecast.']
    safety['recommended_actions']=['Synthetic data only; escalate to authorised Founder before use.']
    before=deepcopy(saved)
    payload=render_final_pdf(saved,is_current=True)
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(payload)).pages)
    assert not re.search(r'\b(?:synthetic|simulated|fictional|demonstration)\b|demo data',text,re.I)
    assert 'Heavy rain' in text and 'authorised Founder' in text
    assert saved==before and client.get(final_path).json()==original
    (tmp_path/'visitor-final.pdf').write_bytes(payload)
