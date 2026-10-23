"""A real place card must survive public projection without exposing diagnostics."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.auth import User
from app.application.presentation import plan_response, SYDNEY_CATALOGUE_DIGEST, SYDNEY_CATALOGUE_ID


@pytest.mark.parametrize('version,digest,visible', [
    ('2.2.0', SYDNEY_CATALOGUE_DIGEST, True),
    ('2.2.0', 'a' * 64, False),
    ('2.1.0', SYDNEY_CATALOGUE_DIGEST, False),
    ('2.2.0', None, False),
])
def test_public_location_identity_is_source_bound_not_a_configuration_side_channel(version, digest, visible):
    value = {'confirmed_context': {'profile_snapshot': {'equipment': []},
        'dataset_context': {'dataset_version': version,
            'file_digests': {'source_catalogue.json': digest},
            'selection_config': {'private': 'private-runtime-marker'}}},
        'campsite_catalogue_id': SYDNEY_CATALOGUE_ID,
        'events': [], 'assessments': [], 'model_assessment_audits': {}}
    before = deepcopy(value)
    view = plan_response(value, User('camper-a', 'camper.a', 'Camper A', 'CAMPER'))
    assert (view.get('campsite_catalogue_id') == SYDNEY_CATALOGUE_ID) is visible
    assert view['confirmed_context']['dataset_context'] == {'dataset_version': version}
    assert 'private-runtime-marker' not in json.dumps(view)
    assert SYDNEY_CATALOGUE_DIGEST not in json.dumps(view)
    assert 'model_diagnostics' not in view
    assert value == before


def test_public_identity_is_pinned_to_the_shipped_catalogue_seal():
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads((root / 'data/sydney_surrounds_v2_2/manifest.json').read_bytes())
    assert manifest['files_sha256']['data/source_catalogue.json'] == SYDNEY_CATALOGUE_DIGEST
