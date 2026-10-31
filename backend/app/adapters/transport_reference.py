"""Versioned synthetic distance extension; never rewrites a sealed package."""
import hashlib
import json
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ..config import APP_ROOT
from ..contracts.dto import Provenance, SourceRef
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..agents.rules.transport import POLICY_KEY, POLICY_VERSION

REFERENCE_KEY = 'transport/sydney_city_v1.json'
REFERENCE_PATH = APP_ROOT / 'data' / REFERENCE_KEY
ORIGIN_ID = 'sydney_city_demo'


class Route(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    campsite_id: str
    round_trip_km_per_vehicle: Annotated[StrictInt, Field(ge=1, le=2000)] | None


class Reference(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal['sydney-city-demo-distances-1']
    created_on: Literal['2026-10-27']
    origin_id: Literal['sydney_city_demo']
    origin_label: Literal['\u6089\u5c3c\u5e02\u533a\uff08\u56fa\u5b9a\u6a21\u62df\u51fa\u53d1\u5730\uff09']
    scope: str
    provenance: Provenance
    routes: tuple[Route, ...]


def fail(message):
    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message=message))


def read_reference():
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('Duplicate key')
                result[key] = value
            return result
        payload = REFERENCE_PATH.read_bytes()
        value = Reference.model_validate(json.loads(payload, object_pairs_hook=pairs))
        if (value.provenance.source_type != 'SYNTHETIC' or value.provenance.demo_only is not True
                or len(value.routes) != 10 or len({row.campsite_id for row in value.routes}) != len(value.routes)):
            raise ValueError('Invalid synthetic reference')
        return value, hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, TypeError):
        fail('Simulated transport distances are missing or invalid. Legacy personal distance cannot be substituted.')


def register_reference(context):
    if context.selection_config.get(POLICY_KEY) != POLICY_VERSION:
        return context
    if context.dataset_version != '2.2.0':
        fail('System transport preparation policy is registered only in  Sydney 2.2 dataset.')
    reference, digest = read_reference()
    markers = {'b_transport_origin': reference.origin_id, 'b_transport_reference_sha256': digest}
    if (any(context.selection_config.get(key, value) != value for key, value in markers.items())
            or context.file_digests.get(REFERENCE_KEY, digest) != digest):
        fail('Simulated transport distance registration does not match the actual file.')
    return context.model_copy(update={'selection_config': {**context.selection_config, **markers},
        'file_digests': {**context.file_digests, REFERENCE_KEY: digest}}, deep=True)


def bind_reference(dataset, context):
    if context.selection_config.get(POLICY_KEY) != POLICY_VERSION:
        return
    reference, digest = read_reference()
    if (context.file_digests.get(REFERENCE_KEY) != digest
            or context.selection_config.get('b_transport_reference_sha256') != digest
            or context.selection_config.get('b_transport_origin') != reference.origin_id
            or {row.campsite_id for row in reference.routes} != {camp.campsite_id for camp in dataset.campsites}):
        fail('Consumed simulated distances do not belong to this run snapshot.')
    dataset.transport_reference = reference


def estimate_vehicle_km(dataset, profile, campsites):
    reference = getattr(dataset, 'transport_reference', None)
    if reference is None or len(campsites) != 1:
        return None, None
    route = next((row for row in reference.routes if row.campsite_id == campsites[0].campsite_id), None)
    vehicles = [row for row in profile.equipment if row.item_key == 'vehicle']
    if (route is None or route.round_trip_km_per_vehicle is None or not vehicles
            or any(not row.confirmed or row.quantity is None or row.unit != 'vehicle' for row in vehicles)
            or profile.transport.vehicle_count is None
            or sum(row.quantity for row in vehicles) != profile.transport.vehicle_count):
        return None, None
    quantity = Decimal(route.round_trip_km_per_vehicle * profile.transport.vehicle_count)
    return quantity, SourceRef(dataset_file=REFERENCE_KEY, record_id=route.campsite_id, provenance=reference.provenance)
