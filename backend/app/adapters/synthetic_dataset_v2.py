"""Strict reader for the sealed v2 business/runtime input snapshot."""
import csv
import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..contracts.dto import DatasetContext, Evidence, Provenance, ScenarioContext, SourceRef, Transport, ProfileSnapshot
from ..contracts.enums import DataQuality, ErrorCode, RoadState
from ..contracts.errors import ContractError, ContractFailure
from ..dataset_paths import data_file_path, manifest_file_path
from .dataset_mapping import COST_CATEGORIES, aud_to_cents, csv_boolean, csv_list, decimal_value, optional_integer, optional_text, required_text, source_date, string_list
from .models import CampsiteRecord, CostReferenceRecord, GearRuleRecord, ProfileRecord, RequestRecord, SafetyRecord
from .synthetic_dataset import SyntheticDataset, _index, _unique_object

SOURCE_NAME = 'CampMate Synthetic Demo Dataset v2'
ADAPTER_VERSION_V2 = 'b01-v2-adapter-2'
V2_RULES_VERSION = 'b02-v2-rules-2/a-meal-clarification-v1/a-profile-essentials-v1'
BUSINESS_FILES = (
    'synthetic_campsites.csv', 'synthetic_gear_rules.csv', 'synthetic_cost_reference.csv',
    'synthetic_profiles.json', 'synthetic_requests.json', 'synthetic_safety_scenarios.json',
)
RUNTIME_FILES = ('runtime_requests.json', 'runtime_safety_evidence.json')


def _fail(message, filename=''):
    return ContractFailure(ContractError(code=ErrorCode.ADAPTER_FAILURE, message=message,
        context={'dataset_file': filename} if filename else {}))


def _json(payload):
    return json.loads(payload.decode('utf-8-sig'), parse_float=Decimal,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')),
        object_pairs_hook=_unique_object)


def _csv(payload):
    reader = csv.DictReader(io.StringIO(payload.decode('utf-8-sig'), newline=''), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('Invalid CSV header')
    rows = list(reader)
    if not rows or any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed or empty CSV')
    return rows


def _source(row, filename, record_id):
    if (row.get('source_type'), row.get('source_name'), row.get('source_date')) != ('SYNTHETIC', SOURCE_NAME, '2026-10-07'):
        raise ValueError('Inconsistent v2 provenance')
    demo = row.get('demo_only')
    if isinstance(demo, str):
        demo = csv_boolean(demo)
    if demo is not True:
        raise ValueError('v2 inputs must be explicitly demo-only')
    return SourceRef(dataset_file=filename, record_id=record_id,
        provenance=Provenance(source_type='SYNTHETIC', source_name=SOURCE_NAME, source_date='2026-10-07', demo_only=True))


def _campsite(row):
    record_id = required_text(row['campsite_id'])
    booleans = ('booking_required','vehicle_access','public_transport_access','toilets','potable_water','showers','fire_allowed','pets_allowed','wheelchair_accessible','walk_in_only','quiet_environment','step_free_path')
    lists = ('supported_seasons','facilities','mandatory_restrictions','risk_tags')
    return CampsiteRecord(campsite_id=record_id, name=required_text(row['name']), region=required_text(row['region']),
        subregion=required_text(row['subregion']), latitude=decimal_value(row['latitude']), longitude=decimal_value(row['longitude']),
        nightly_fee_cents=aud_to_cents(row['nightly_fee_aud']), fee_unit=row['fee_unit'], max_group_size=optional_integer(row['max_group_size']),
        source_ref=_source(row, 'synthetic_campsites.csv', record_id),
        **{key: csv_boolean(row[key]) for key in booleans}, **{key: csv_list(row[key]) for key in lists})


def _gear(row):
    record_id = required_text(row['gear_rule_id'])
    trigger, quantity = _json(row['trigger_json'].encode()), _json(row['quantity_json'].encode())
    if not isinstance(trigger, (dict, bool)) or not isinstance(quantity, (dict, int, Decimal)):
        raise ValueError('Invalid gear DSL expression')
    return GearRuleRecord(gear_rule_id=record_id, category=required_text(row['category']), item_name=required_text(row['item_name']),
        trigger_conditions=required_text(row['trigger_conditions']), quantity_rule=required_text(row['quantity_rule']),
        essential=csv_boolean(row['essential']), severity_if_missing=row['severity_if_missing'],
        substitute_allowed=csv_boolean(row['substitute_allowed']), substitute_example=optional_text(row['substitute_example']),
        reason=required_text(row['reason']), source_ref=_source(row, 'synthetic_gear_rules.csv', record_id))


def _cost(row):
    record_id = required_text(row['cost_id'])
    unit = required_text(row['unit'])
    units = {'per_night':'per_night','per_kilometre':'per_kilometre','per_person':'per_person','per_person_per_day':'per_person_per_day','per_item':'per_item','per_vehicle':'per_vehicle','one_time':'one_time'}
    if unit not in units:
        raise ValueError('Unsupported v2 cost unit')
    prices = [decimal_value(row[key]) for key in ('low_aud','typical_aud','high_aud')]
    if any(value is None or value < 0 for value in prices) or prices != sorted(prices):
        raise ValueError('Invalid v2 rate range')
    _json(row['quantity_json'].encode())
    return CostReferenceRecord(cost_id=record_id, category=COST_CATEGORIES[required_text(row['category'])],
        item_name=required_text(row['item_name']), unit=units[unit], low_cents=aud_to_cents(prices[0]),
        typical_cents=aud_to_cents(prices[1]), high_cents=aud_to_cents(prices[2]),
        calculation_rule=required_text(row['calculation_rule']), assumption=required_text(row['assumption']),
        source_ref=_source(row, 'synthetic_cost_reference.csv', record_id))


def _profile(row):
    record_id = required_text(row['profile_id'])
    items = []
    for value in row['normalized_equipment']:
        if not isinstance(value.get('confirmed'), bool):
            raise ValueError('normalized equipment confirmation must be boolean')
        items.append({'item_key': required_text(value['item_key']), 'label': required_text(value['original_text']),
            'quantity': optional_integer(value['quantity']), 'unit': required_text(value['unit']),
            'capacity_persons': optional_integer(value['capacity_persons']), 'confirmed': value['confirmed'] is True})
    transport_type = optional_text(row['transport_type'])
    if transport_type not in {None, 'CAR', 'PUBLIC_TRANSPORT'}:
        raise ValueError('Unsupported transport type')
    children = row['has_children']
    if children is not None and not isinstance(children, bool):
        raise ValueError('Invalid has_children')
    snapshot = ProfileSnapshot(profile_id=record_id, group_size=optional_integer(row['group_size']),
        experience_level=optional_text(row['experience_level']), has_children=children,
        children_count=optional_integer(row['children_count']), equipment=items,
        transport=Transport(transport_type=transport_type,
            vehicle_count=(optional_integer(row['vehicle_count']) or None) if transport_type != 'CAR' else optional_integer(row['vehicle_count'])),
        accessibility_requirements=string_list(row['accessibility_requirements']))
    return ProfileRecord(profile_id=record_id, snapshot=snapshot,
        uncertainties=['v2 inventory is a candidate only; unconfirmed items do not count as available.'],
        source_ref=_source(row, 'synthetic_profiles.json', record_id))


def _request(row):
    record_id = required_text(row['request_id'])
    return RequestRecord(request_id=record_id, profile_id=required_text(row['profile_id']),
        raw_text=required_text(row['natural_language_request']),
        source_ref=_source(row, 'synthetic_requests.json', record_id))


def _safety(row, filename='synthetic_safety_scenarios.json'):
    record_id, campsite_id = required_text(row['safety_case_id']), required_text(row['campsite_id'])
    ref = _source(row, filename, campsite_id)
    evidence = []
    for field, kind in (('weather','WEATHER'),('fire','FIRE'),('road_access','ROAD')):
        item = row[field]
        status = DataQuality(item.get('data_status', item.get('status', 'MISSING')))
        observed = item.get('observed_at')
        observed_date = datetime.fromisoformat(observed).date() if observed else source_date(item.get('source_date'))
        state = None
        if kind == 'ROAD':
            raw = item.get('status')
            state = RoadState(raw) if raw in {'OPEN','CLOSED'} else RoadState.UNKNOWN
            if state == RoadState.UNKNOWN and status == DataQuality.AVAILABLE:
                status = DataQuality.MISSING
        valid_from = source_date(item.get('valid_from') or row.get('valid_from'))
        valid_to = source_date(item.get('valid_until') or row.get('valid_until'))
        evidence.append(Evidence(kind=kind, summary=optional_text(item.get('summary')), source_date=observed_date,
            status=status, valid_from=valid_from, valid_to=valid_to, road_state=state,
            source_refs=[ref.model_copy(update={'valid_from':valid_from,'valid_to':valid_to})]))
    restrictions = string_list(row.get('campsite_restrictions', []))
    evidence.append(Evidence(kind='RESTRICTION', summary='; '.join(restrictions) if restrictions else 'No synthetic campsite restrictions reported.',
        source_date=source_date(row.get('source_date')), status=DataQuality.AVAILABLE,
        valid_from=source_date(row.get('valid_from')), valid_to=source_date(row.get('valid_until')),
        source_refs=[ref.model_copy(update={'valid_from':source_date(row.get('valid_from')),'valid_to':source_date(row.get('valid_until'))})]))
    start, end = source_date(row.get('valid_from')), source_date(row.get('valid_until'))
    case_ref = _source(row, filename, record_id)
    return SafetyRecord(safety_case_id=record_id, campsite_id=campsite_id,
        scenario_date=source_date(row.get('scenario_date')), scenario_context=ScenarioContext(
            scenario_id=record_id, campsite_ids=[campsite_id], valid_from=start, valid_to=end, evidence=evidence),
        campsite_restrictions=restrictions, risk_tags=string_list(row.get('risk_tags', [])),
        raw_road_status=row['road_access']['status'], uncertainties=[], source_ref=case_ref)


class SyntheticDatasetV2Adapter:
    """Consumes the same sealed bytes A inspected; does not load tests/oracles."""
    def __init__(self, dataset_path):
        self.dataset_path = Path(dataset_path)

    def load(self, *, expected_context=None):
        filename = ''
        try:
            root = self.dataset_path.resolve(strict=True)
            payloads = {}
            for filename in (*BUSINESS_FILES, *RUNTIME_FILES):
                payloads[filename] = data_file_path(root, filename).read_bytes()
            filename = 'manifest.json'
            manifest = manifest_file_path(root).read_bytes()
            actual = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
            actual['manifest.json'] = hashlib.sha256(manifest).hexdigest()
            if expected_context is not None and any(expected_context.file_digests.get(name) != value for name, value in actual.items()):
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='v2 Adapter 消费的原始字节与应用登记摘要不一致。'))
            parsed = {name: (_csv(payload) if name.endswith('.csv') else _json(payload)) for name, payload in payloads.items()}
            for rows in parsed.values():
                for row in rows:
                    _source(row, '', required_text(row.get('request_id') or row.get('safety_case_id') or row.get('profile_id') or row.get('campsite_id') or row.get('gear_rule_id') or row.get('cost_id')))
            manifest_value = _json(manifest)
            version = manifest_value.get('dataset_version')
            if version not in {'2.0.0', '2.1.0'} or any(manifest_value.get('files_sha256', {}).get('data/' + name) != value for name, value in actual.items() if name != 'manifest.json'):
                raise ValueError('v2 package seal does not match consumed bytes')
            if len({row.get('source_name') for name, rows in parsed.items() for row in rows}) != 1 or next(iter({row.get('source_name') for name, rows in parsed.items() for row in rows})) != SOURCE_NAME:
                raise ValueError('Mixed source names')
            camps = _index([_campsite(row) for row in parsed[BUSINESS_FILES[0]]], 'campsite_id')
            gear_rows = parsed[BUSINESS_FILES[1]]
            costs_rows = parsed[BUSINESS_FILES[2]]
            gear = _index([_gear(row) for row in gear_rows], 'gear_rule_id')
            cost_records = _index([_cost(row) for row in costs_rows], 'cost_id')
            profiles = _index([_profile(row) for row in parsed[BUSINESS_FILES[3]]], 'profile_id')
            requests = _index([_request(row) for row in parsed[BUSINESS_FILES[4]]], 'request_id')
            safety_rows = parsed[RUNTIME_FILES[1]]
            safety = _index([_safety(row, 'runtime_safety_evidence.json') for row in safety_rows], 'safety_case_id')
            if any(record.campsite_id not in camps for record in safety.values()):
                raise ValueError('Safety record references unknown campsite')
            if any(record.profile_id not in profiles for record in requests.values()):
                raise ValueError('Request references unknown profile')
            rules = {required_text(row['gear_rule_id']): row | {'trigger_json': _json(row['trigger_json'].encode()), 'quantity_json': _json(row['quantity_json'].encode())} for row in gear_rows}
            costs = {required_text(row['cost_id']): row | {'quantity_json': _json(row['quantity_json'].encode())} for row in costs_rows}
            if len(rules) != len(gear_rows) or len(costs) != len(costs_rows):
                raise ValueError('Duplicate rule or cost ID')
            # Preserve machine policies verbatim after parsing, alongside common DTO projections.
            policy = {'gear': rules, 'costs': costs, 'safety': {row['safety_case_id']: row for row in safety_rows}}
            runtime_requests = {row['request_id']: row for row in parsed[RUNTIME_FILES[0]]}
            runtime_profiles = {}
            for request_id, row in runtime_requests.items():
                if row['profile_id'] not in profiles or row['profile_snapshot'].get('profile_id') != row['profile_id']:
                    raise ValueError('Runtime request has an unlinked profile snapshot')
                candidate = _profile(row['profile_snapshot'])
                if candidate.snapshot != profiles[row['profile_id']].snapshot:
                    raise ValueError('Runtime profile snapshot disagrees with canonical profile mapping')
                runtime_profiles[request_id] = candidate.snapshot
            context = DatasetContext(dataset_version=version, file_digests=actual,
                rules_version='a-request-normalization-v1')
            if expected_context is not None and any(expected_context.file_digests.get(name) != value for name, value in actual.items()):
                raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message='v2 Adapter 输入身份已变化。'))
            dataset = SyntheticDataset(context, camps, gear, cost_records, profiles, requests, safety,
                v2_policy=policy, runtime_requests=runtime_requests,
                safety_facts={key: row.get('evidence_facts', {}) for key, row in policy['safety'].items()},
                runtime_profiles=runtime_profiles)
            dataset.adapter_version = ADAPTER_VERSION_V2
            dataset.rules_version = V2_RULES_VERSION
            if version == '2.1.0':
                from ..agents.rules.trip_evidence import POLICY_VERSION, TripEvidenceSelector
                if manifest_value.get('evidence_selection_policy') != POLICY_VERSION:
                    raise ValueError('Unregistered trip evidence policy')
                dataset.trip_evidence_selector = TripEvidenceSelector(dataset, safety_rows)
                dataset.rules_version += '/' + POLICY_VERSION
            return dataset
        except ContractFailure:
            raise
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, ArithmeticError, csv.Error) as exc:
            raise _fail('无法严格读取或验证已封存的 v2 业务与运行数据。', filename) from exc
