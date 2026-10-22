"""Identity of the mixed factual-location / simulated-condition catalogue.

The frozen shared provenance describes the simulation source family. Official
field citations and pricing assumptions are a separately sealed consumed input.
"""
import hashlib
import json

from ..dataset_paths import data_file_path

SYDNEY_VERSION = '2.2.0'
TRIP_DATASET_VERSIONS = frozenset({'2.1.0', SYDNEY_VERSION})
CATALOGUE_FILE = 'source_catalogue.json'


def read_catalogue(root, manifest):
    payload = data_file_path(root, CATALOGUE_FILE).read_bytes()
    if manifest.get('files_sha256', {}).get('data/' + CATALOGUE_FILE) != hashlib.sha256(payload).hexdigest():
        raise ValueError('Location source catalogue differs from package seal')
    value = json.loads(payload.decode('utf-8-sig'))
    if not isinstance(value, dict) or value.get('dataset_version') != SYDNEY_VERSION:
        raise ValueError('Missing versioned location source catalogue')
    return payload
