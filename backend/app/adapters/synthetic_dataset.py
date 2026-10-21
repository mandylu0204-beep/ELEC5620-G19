"""Read-only v1 snapshot adapter. No database, Agent, clock or test-oracle access."""
import csv
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from typing import TypeVar

from ..contracts.base import ContractModel
from ..contracts.dto import (
    DatasetContext, DemoContext, Evidence, InterpretRequestInput, ProfileSnapshot,
    Provenance, ScenarioContext, SourceRef, Transport,
)
from ..contracts.enums import AllowedAction, DataQuality, ErrorCode, RoadState
from ..contracts.errors import ContractError, ContractFailure
from .dataset_mapping import (
    COST_CATEGORIES, aud_to_cents, csv_boolean, csv_list, decimal_value,
    normalize_equipment, optional_integer, optional_text, required_text,
    source_date, string_list,
)
from .models import (
    CampsiteRecord, CostReferenceRecord, GearRuleRecord, ProfileRecord,
    RequestRecord, SafetyRecord,
)

BUSINESS_FILES = (
    'synthetic_campsites.csv', 'synthetic_gear_rules.csv', 'synthetic_cost_reference.csv',
    'synthetic_profiles.json', 'synthetic_requests.json', 'synthetic_safety_scenarios.json',
)
# Matches A-09's data_context. B-02's executable rules need a jointly registered version.
CONTEXT_RULES_VERSION = 'a-request-normalization-v1'
ADAPTER_VERSION = 'b01-v1-adapter-1'
PROVENANCE_FIELDS = ('source_type', 'source_name', 'source_date', 'demo_only')
V1_SOURCE_NAME = 'CampMate Synthetic Demo Dataset v1'
Record = TypeVar('Record', bound=ContractModel)


def _failure(message: str, **context: str) -> ContractFailure:
    return ContractFailure(ContractError(
        code=ErrorCode.ADAPTER_FAILURE, message=message,
        allowed_actions=[AllowedAction.CONTACT_OPERATOR], context=context,
    ))


def _stale(message: str) -> ContractFailure:
    return ContractFailure(ContractError(
        code=ErrorCode.STALE_CONTEXT, message=message,
        allowed_actions=[AllowedAction.REFRESH],
    ))


def _source(row: dict, filename: str, record_id: str) -> SourceRef:
    metadata = {key: row[key] for key in PROVENANCE_FIELDS}
    if filename.endswith('.csv'):
        metadata['demo_only'] = csv_boolean(metadata['demo_only'])
    # Keep this adapter's package-level contract strict even if a later shared
    # Provenance schema learns additional source_name values.
    if metadata['source_name'] != V1_SOURCE_NAME:
        raise ValueError('This adapter accepts only a consistent Git v1 source package')
    return SourceRef(
        dataset_file=filename, record_id=record_id,
        provenance=Provenance.model_validate(metadata),
    )


def _campsite(row: dict, filename: str) -> CampsiteRecord:
    record_id = required_text(row['campsite_id'])
    booleans = (
        'booking_required', 'vehicle_access', 'public_transport_access', 'toilets',
        'potable_water', 'showers', 'fire_allowed', 'pets_allowed', 'wheelchair_accessible',
    )
    lists = ('supported_seasons', 'facilities', 'mandatory_restrictions', 'risk_tags')
    return CampsiteRecord(
        campsite_id=record_id, name=required_text(row['name']),
        region=required_text(row['region']), subregion=required_text(row['subregion']),
        latitude=decimal_value(row['latitude']), longitude=decimal_value(row['longitude']),
        nightly_fee_cents=aud_to_cents(row['nightly_fee_aud']), fee_unit=row['fee_unit'],
        max_group_size=optional_integer(row['max_group_size']),
        source_ref=_source(row, filename, record_id),
        **{key: csv_boolean(row[key]) for key in booleans},
        **{key: csv_list(row[key]) for key in lists},
    )


def _gear(row: dict, filename: str) -> GearRuleRecord:
    record_id = required_text(row['gear_rule_id'])
    return GearRuleRecord(
        gear_rule_id=record_id, category=required_text(row['category']),
        item_name=required_text(row['item_name']),
        trigger_conditions=required_text(row['trigger_conditions']),
        quantity_rule=required_text(row['quantity_rule']),
        essential=csv_boolean(row['essential']), severity_if_missing=row['severity_if_missing'],
        substitute_allowed=csv_boolean(row['substitute_allowed']),
        substitute_example=optional_text(row['substitute_example']),
        reason=required_text(row['reason']), source_ref=_source(row, filename, record_id),
    )


def _cost(row: dict, filename: str) -> CostReferenceRecord:
    record_id = required_text(row['cost_id'])
    prices = [decimal_value(row[key]) for key in ('low_aud', 'typical_aud', 'high_aud')]
    known = [value for value in prices if value is not None]
    if any(value < 0 for value in known) or known != sorted(known):
        raise ValueError('Invalid price range')
    return CostReferenceRecord(
        cost_id=record_id, category=COST_CATEGORIES[row['category']],
        item_name=required_text(row['item_name']), unit=row['unit'],
        low_cents=aud_to_cents(prices[0]), typical_cents=aud_to_cents(prices[1]),
        high_cents=aud_to_cents(prices[2]),
        calculation_rule=required_text(row['calculation_rule']),
        assumption=required_text(row['assumption']), source_ref=_source(row, filename, record_id),
    )


def _profile(row: dict, filename: str) -> ProfileRecord:
    record_id = required_text(row['profile_id'])
    has_children = row['has_children']
    if has_children is not None and not isinstance(has_children, bool):
        raise ValueError('JSON has_children must be a boolean or null')
    equipment = [normalize_equipment(label) for label in string_list(row['available_equipment'])]
    transport_type = optional_text(row['transport_type'])
    if transport_type not in {None, 'CAR', 'PUBLIC_TRANSPORT'}:
        raise ValueError('Unsupported transport type')
    snapshot = ProfileSnapshot(
        profile_id=record_id, group_size=optional_integer(row['group_size']),
        experience_level=optional_text(row['experience_level']), has_children=has_children,
        equipment=equipment, transport=Transport(transport_type=transport_type),
        accessibility_requirements=string_list(row['accessibility_requirements']),
    )
    uncertainties = ['Source profile is demonstration input, not an account or user confirmation.']
    uncertainties.extend(f'Equipment {item.label!r} needs quantity confirmation.' for item in equipment if item.quantity is None)
    uncertainties.append('All source equipment remains unconfirmed.')
    if any(item.item_key == 'tent' and item.capacity_persons is None for item in equipment):
        uncertainties.append('Tent capacity is unknown.')
    if has_children:
        uncertainties.append('Children count is unknown; profile notes are not structured input.')
    if transport_type == 'CAR':
        uncertainties.append('Vehicle count and total vehicle kilometres are unknown.')
    return ProfileRecord(
        profile_id=record_id, snapshot=snapshot, uncertainties=uncertainties,
        source_ref=_source(row, filename, record_id),
    )


def _request(row: dict, filename: str) -> RequestRecord:
    record_id = required_text(row['request_id'])
    # Only original user text and linked profile enter interpretation. The structured
    # v1 summary has duration ambiguity and is not a confirmed user supplement.
    return RequestRecord(
        request_id=record_id, profile_id=required_text(row['profile_id']),
        raw_text=required_text(row['natural_language_request']),
        source_ref=_source(row, filename, record_id),
    )


def _safety(row: dict, filename: str) -> SafetyRecord:
    record_id, campsite_id = required_text(row['safety_case_id']), required_text(row['campsite_id'])
    reference = _source(row, filename, record_id)
    # A's evidence relationship checks use the campsite source ID. The enclosing
    # record retains the independent safety-case ID, so both links are available.
    evidence_ref = _source(row, filename, campsite_id)
    uncertainties = ['v1 has no evidence validity interval; scenario_date is not a coverage interval.']
    evidence = []
    for source_key, kind in (('weather', 'WEATHER'), ('fire', 'FIRE'), ('road_access', 'ROAD')):
        value = row[source_key]
        if not isinstance(value, dict):
            raise ValueError('Evidence must be an object')
        status_text = value['status']
        if not isinstance(status_text, str) or not status_text.strip():
            raise ValueError('Evidence status must be nonblank text')
        status_text = status_text.strip()
        observed_source_date = source_date(value['source_date'])
        road_state = None
        if kind == 'ROAD':
            if status_text not in {'OPEN', 'CLOSED', 'UNKNOWN', 'RESTRICTED'}:
                raise ValueError('Unsupported road status')
            road_state = RoadState(status_text) if status_text in {'OPEN', 'CLOSED'} else RoadState.UNKNOWN
            quality = DataQuality.AVAILABLE if road_state != RoadState.UNKNOWN else DataQuality.MISSING
            if status_text == 'RESTRICTED':
                uncertainties.append('RESTRICTED has no shared RoadState; retained raw, mapped to UNKNOWN/MISSING, never OPEN.')
        else:
            quality = DataQuality(status_text)
        if quality == DataQuality.AVAILABLE and observed_source_date is None:
            quality = DataQuality.MISSING
            uncertainties.append(f'{kind} source date is missing despite AVAILABLE label.')
        evidence.append(Evidence(
            kind=kind, summary=optional_text(value['summary']), source_date=observed_source_date,
            status=quality, valid_from=None, valid_to=None, road_state=road_state,
            source_refs=[evidence_ref],
        ))
    restrictions = string_list(row['campsite_restrictions'])
    evidence.append(Evidence(
        kind='RESTRICTION', summary='; '.join(restrictions) if restrictions else 'No restrictions listed; completeness is unverified.',
        source_date=source_date(reference.provenance.source_date), status=DataQuality.AVAILABLE,
        valid_from=None, valid_to=None, source_refs=[evidence_ref],
    ))
    return SafetyRecord(
        safety_case_id=record_id, campsite_id=campsite_id,
        scenario_date=source_date(row['scenario_date']),
        scenario_context=ScenarioContext(
            scenario_id=record_id, campsite_ids=[campsite_id], valid_from=None,
            valid_to=None, evidence=evidence,
        ),
        campsite_restrictions=restrictions, risk_tags=string_list(row['risk_tags']),
        raw_road_status=row['road_access']['status'].strip(),
        uncertainties=uncertainties, source_ref=reference,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def _reject_constant(value: str):
    raise ValueError('Non-finite JSON number')


def _rows(payload: bytes, filename: str) -> list[dict]:
    text = payload.decode('utf-8-sig')
    if filename.endswith('.csv'):
        reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
        headers = reader.fieldnames
        if not headers or len(set(headers)) != len(headers) or any(not name for name in headers):
            raise ValueError('Invalid CSV headers')
        records = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in records):
            raise ValueError('CSV row does not match headers')
    else:
        records = json.loads(text, parse_float=decimal_value, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    if not isinstance(records, list) or not records or any(not isinstance(row, dict) for row in records):
        raise ValueError('Expected a nonempty record array')
    return records


def _index(records: list[Record], id_field: str) -> dict[str, Record]:
    indexed = {}
    for record in records:
        record_id = getattr(record, id_field)
        if record_id in indexed:
            raise ValueError('Duplicate record ID')
        indexed[record_id] = record
    return indexed


class SyntheticDataset:
    """Detached source views, not a guarantee that a whole binding is immutable."""

    def __init__(
        self, context: DatasetContext, campsites: dict[str, CampsiteRecord],
        gear_rules: dict[str, GearRuleRecord], costs: dict[str, CostReferenceRecord],
        profiles: dict[str, ProfileRecord], requests: dict[str, RequestRecord],
        safety: dict[str, SafetyRecord], *, v2_policy=None, runtime_requests=None,
        safety_facts=None, runtime_profiles=None,
    ):
        self._context = context
        self._campsites, self._gear_rules, self._costs = campsites, gear_rules, costs
        self._profiles, self._requests, self._safety = profiles, requests, safety
        # v2-only declarative source material. Kept separate from shared DTOs so
        # contract 1.0 remains stable and the source expressions remain auditable.
        # Own the source objects: neither constructor aliases nor exported views
        # may mutate a snapshot reused by another component.
        self._v2_policy = deepcopy(v2_policy)
        self._runtime_requests = deepcopy(runtime_requests) if runtime_requests is not None else {}
        self._safety_facts = deepcopy(safety_facts) if safety_facts is not None else {}
        self._runtime_profiles = deepcopy(runtime_profiles) if runtime_profiles is not None else {}
        self.adapter_version = ADAPTER_VERSION

    @property
    def has_v2_policy(self) -> bool:
        return self._v2_policy is not None

    @property
    def v2_policy(self) -> dict | None:
        """Detached compatibility view; rule hot paths use per-record getters."""
        return deepcopy(self._v2_policy)

    @property
    def runtime_requests(self) -> dict:
        return deepcopy(self._runtime_requests)

    @property
    def safety_facts(self) -> dict:
        return deepcopy(self._safety_facts)

    @property
    def runtime_profiles(self) -> dict[str, ProfileSnapshot]:
        return deepcopy(self._runtime_profiles)

    def _policy_record(self, kind: str, record_id: str) -> dict:
        if self._v2_policy is None or record_id not in self._v2_policy[kind]:
            raise _failure('Synthetic policy record does not exist.', record_id=record_id)
        return deepcopy(self._v2_policy[kind][record_id])

    def get_gear_policy(self, gear_rule_id: str) -> dict:
        return self._policy_record('gear', gear_rule_id)

    def get_cost_policy(self, cost_id: str) -> dict:
        return self._policy_record('costs', cost_id)

    def get_safety_facts(self, safety_case_id: str) -> dict:
        return deepcopy(self._safety_facts.get(safety_case_id, {}))

    @property
    def context(self) -> DatasetContext:
        return self._context.model_copy(deep=True)

    @property
    def regions(self) -> tuple[str, ...]:
        return tuple(sorted({record.region for record in self._campsites.values()}))

    @property
    def campsites(self) -> tuple[CampsiteRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._campsites.values())

    @property
    def gear_rules(self) -> tuple[GearRuleRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._gear_rules.values())

    @property
    def cost_references(self) -> tuple[CostReferenceRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._costs.values())

    @property
    def profiles(self) -> tuple[ProfileRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._profiles.values())

    @property
    def requests(self) -> tuple[RequestRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._requests.values())

    @property
    def safety_cases(self) -> tuple[SafetyRecord, ...]:
        return tuple(record.model_copy(deep=True) for record in self._safety.values())

    def _get(self, records: dict[str, Record], record_id: str) -> Record:
        if record_id not in records:
            raise _failure('Synthetic source record does not exist.', record_id=record_id)
        return records[record_id].model_copy(deep=True)

    def get_campsite(self, campsite_id: str) -> CampsiteRecord:
        return self._get(self._campsites, campsite_id)

    def get_gear_rule(self, gear_rule_id: str) -> GearRuleRecord:
        return self._get(self._gear_rules, gear_rule_id)

    def get_cost_reference(self, cost_id: str) -> CostReferenceRecord:
        return self._get(self._costs, cost_id)

    def get_profile(self, profile_id: str) -> ProfileRecord:
        return self._get(self._profiles, profile_id)

    def get_request(self, request_id: str) -> RequestRecord:
        return self._get(self._requests, request_id)

    def get_safety(self, safety_case_id: str, *, campsite_id: str | None = None) -> SafetyRecord:
        record = self._get(self._safety, safety_case_id)
        if campsite_id is not None and record.campsite_id != campsite_id:
            raise _failure('Safety evidence belongs to a different campsite.', record_id=safety_case_id)
        return record

    def request_input(self, request_id: str, demo_context: DemoContext) -> InterpretRequestInput:
        if demo_context.dataset_version != self._context.dataset_version:
            raise _stale('DemoContext and source dataset versions differ.')
        request = self.get_request(request_id)
        runtime = self._runtime_requests.get(request_id)
        raw_text = runtime['natural_language_request'] if runtime is not None else request.raw_text
        profile_snapshot = self._runtime_profiles.get(request_id) or self.get_profile(request.profile_id).snapshot
        if runtime is not None and runtime.get('profile_snapshot', {}).get('profile_id') != request.profile_id:
            raise _failure('Runtime request profile snapshot does not match its linked profile.', record_id=request_id)
        return InterpretRequestInput(
            raw_text=raw_text, profile_snapshot=profile_snapshot.model_copy(deep=True),
            demo_context=demo_context,
        )


class SyntheticDatasetAdapter:
    """Load exactly six registered v1 files; never execute package scripts."""

    def __init__(self, dataset_path: str | Path):
        self.dataset_path = Path(dataset_path)

    def load(self, *, expected_context: DatasetContext | None = None) -> SyntheticDataset:
        filename = ''
        try:
            root = self.dataset_path.resolve(strict=True)
            payloads = {}
            for filename in BUSINESS_FILES:
                path = (root / 'data' / filename).resolve(strict=True)
                if not path.is_relative_to(root / 'data'):
                    raise ValueError('Business source escapes the business data directory')
                payloads[filename] = path.read_bytes()
            context = DatasetContext(
                dataset_version='v1',
                file_digests={name: hashlib.sha256(content).hexdigest() for name, content in payloads.items()},
                rules_version=CONTEXT_RULES_VERSION,
            )
            if expected_context is not None and context != expected_context:
                raise _stale('Source bytes or registered dataset configuration changed; do not reuse this run.')
            parsers = (
                (_campsite, 'campsite_id'), (_gear, 'gear_rule_id'), (_cost, 'cost_id'),
                (_profile, 'profile_id'), (_request, 'request_id'), (_safety, 'safety_case_id'),
            )
            indexes = []
            for filename, (parse, id_field) in zip(BUSINESS_FILES, parsers, strict=True):
                records = [parse(row, filename) for row in _rows(payloads[filename], filename)]
                indexes.append(_index(records, id_field))
            campsites, gear, costs, profiles, requests, safety = indexes
            filename = 'synthetic_requests.json'
            if any(record.profile_id not in profiles for record in requests.values()):
                raise ValueError('Unknown request profile reference')
            filename = 'synthetic_safety_scenarios.json'
            if any(record.campsite_id not in campsites for record in safety.values()):
                raise ValueError('Unknown safety campsite reference')
            return SyntheticDataset(context, campsites, gear, costs, profiles, requests, safety)
        except ContractFailure:
            raise
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, ArithmeticError, csv.Error) as exc:
            raise _failure('Cannot load or validate the synthetic v1 business dataset.', dataset_file=filename) from exc
