"""Internal, immutable, day-granularity evidence selection. No IO or oracle."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator

from ...contracts.base import ContractModel
from ...contracts.dto import ConfirmedRequirements, DemoContext, Evidence, ScenarioContext, SourceRef
from ...contracts.enums import DataQuality, RoadState
from .common import TRIP_ZONE, input_failure, rule_failure

POLICY_VERSION = 'trip-evidence-selection-1'
KINDS = ('WEATHER', 'FIRE', 'ROAD', 'RESTRICTION')
WEATHER_KEYS = ('temperature_min_c', 'temperature_max_c', 'forecast_rain_mm', 'wind_kph')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def contains_oracle(value):
    if isinstance(value,dict):
        return any(key.startswith('expected_') or key in {'oracle','expected','assertions','test_id','execution_status',
                   'confidence','severity','setup','actions','finalization_eligible'}
                   or contains_oracle(item) for key,item in value.items())
    return isinstance(value,list) and any(contains_oracle(item) for item in value)


class WeatherFacts(ContractModel):
    temperature_min_c: Decimal | None = Field(default=None, allow_inf_nan=False)
    temperature_max_c: Decimal | None = Field(default=None, allow_inf_nan=False)
    forecast_rain_mm: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    wind_kph: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator('*', mode='before')
    @classmethod
    def no_boolean_facts(cls, value):
        if isinstance(value, bool):
            raise ValueError('Weather numbers cannot be boolean')
        return value


class DateRange(ContractModel):
    start: date
    end: date


class CoverageIssue(ContractModel):
    campsite_id: str
    kind: Literal['WEATHER', 'FIRE', 'ROAD', 'RESTRICTION']
    code: Literal['MISSING', 'OUTSIDE_VALIDITY', 'NOT_YET_OBSERVED', 'STALE', 'CONFLICTING', 'ROAD_STATE_UNKNOWN']
    requested_range: DateRange
    available_ranges: list[DateRange]
    uncovered_ranges: list[DateRange]
    reason: str


class TripEvidenceSelection(ContractModel):
    selected_case_ids: list[str]
    scenario_context: ScenarioContext
    weather_facts_by_campsite: dict[str, WeatherFacts]
    coverage_issues: list[CoverageIssue]
    selection_digest: str = Field(pattern=r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class Entry:
    case_id: str
    campsite_id: str
    kind: str
    evidence_json: str
    weather_json: str
    published: date | None
    observed: date | None
    max_age_days: int


def observed_day(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Evidence timestamps need an explicit timezone')
    # DemoContext has a date, not a time-of-day. Never consult the host clock.
    return parsed.astimezone(TRIP_ZONE).date()


def uncovered(start, end, ranges):
    cursor, gaps = start, []
    for first, last in sorted(ranges):
        if last < cursor or first > end:
            continue
        if first > cursor:
            gaps.append(DateRange(start=cursor, end=min(end, first - timedelta(days=1))))
        if last >= end:
            return gaps
        cursor = max(cursor, last + timedelta(days=1))
    if cursor <= end:
        gaps.append(DateRange(start=cursor, end=end))
    return gaps


class TripEvidenceSelector:
    """Frozen source bytes, not a view onto mutable dataset dictionaries.

    v1 requires at least one complete record per campsite/kind. It does not
    splice partial forecasts into a fictitious continuous forecast. Overlapping
    restrictions still apply to any overlapping day of the requested trip.
    """
    def __init__(self, dataset, rows):
        self.dataset_version = dataset.context.dataset_version
        self.index_digest = dataset.context.file_digests['runtime_safety_evidence.json']
        self.campsite_ids = frozenset(item.campsite_id for item in dataset.campsites)
        self._camp_refs = tuple((item.campsite_id,item.source_ref.model_dump_json()) for item in dataset.campsites)
        entries = []
        for row in rows:
            if contains_oracle(row):
                raise ValueError('Production evidence cannot contain test oracle fields')
            record = dataset.get_safety(row['safety_case_id'])
            active = row['active_kinds']
            if not active or len(set(active)) != len(active) or not set(active) <= set(KINDS):
                raise ValueError('Explicit, unique evidence kinds are required')
            published = observed_day(row.get('published_at'))
            age = row['max_age_days']
            if type(age) is not int or not 1 <= age <= 366:
                raise ValueError('Bounded integer evidence age is required')
            weather = WeatherFacts.model_validate({key: row.get('evidence_facts', {}).get(key) for key in WEATHER_KEYS})
            for evidence in record.scenario_context.evidence:
                if evidence.kind not in active:
                    continue
                field = {'WEATHER':'weather', 'FIRE':'fire', 'ROAD':'road_access'}.get(evidence.kind)
                observed = observed_day(row[field].get('observed_at')) if field else observed_day(row.get('restriction_observed_at'))
                evidence = evidence.model_copy(update={'source_date': observed,
                    'source_refs': [*evidence.source_refs, record.source_ref.model_copy(update={
                        'valid_from': evidence.valid_from, 'valid_to': evidence.valid_to})]})
                entries.append(Entry(record.safety_case_id, record.campsite_id, evidence.kind,
                    evidence.model_dump_json(), weather.model_dump_json(), published, observed, age))
        self._entries = tuple(sorted(entries, key=lambda value:(value.campsite_id, value.kind, value.case_id)))

    def resolve_trip_evidence(self, confirmed_requirements, campsite_ids, demo_context):
        req = ConfirmedRequirements.model_validate(confirmed_requirements)
        demo = DemoContext.model_validate(demo_context)
        ids = tuple(campsite_ids)
        if not ids or len(set(ids)) != len(ids) or not set(ids) <= self.campsite_ids:
            raise input_failure('Evidence query needs unique, known actual campsites.', 'campsite_ids')
        if demo.dataset_version != self.dataset_version:
            raise rule_failure('Evidence index and run dataset identities differ.', 'dataset_version')
        start, end, today = req.start_date, req.end_date, demo.demo_today
        requested = DateRange(start=start, end=end)
        selected, evidence, issues, weather_by_site = set(), [], [], {}
        for campsite in sorted(ids):
            weather_by_site[campsite] = WeatherFacts()
            for kind in KINDS:
                source = [entry for entry in self._entries if (entry.campsite_id,entry.kind)==(campsite,kind)]
                usable, codes, unavailable = [], set(), set()
                for entry in source:
                    item = Evidence.model_validate_json(entry.evidence_json)
                    if item.valid_from is None or item.valid_to is None or item.valid_from > item.valid_to:
                        continue
                    if item.valid_from > end or item.valid_to < start:
                        continue
                    if entry.published is None or entry.observed is None:
                        unavailable.add('MISSING')
                    elif max(entry.published,entry.observed) > today:
                        unavailable.add('NOT_YET_OBSERVED')
                    else:
                        status = item.status
                        if (today-entry.observed).days > entry.max_age_days:
                            status = DataQuality.STALE
                        if kind=='ROAD' and item.road_state not in {RoadState.OPEN,RoadState.CLOSED}:
                            status = DataQuality.MISSING
                            codes.add('ROAD_STATE_UNKNOWN')
                        if status != DataQuality.AVAILABLE:
                            codes.add(status.value)
                        usable.append((entry,item.model_copy(update={'status':status})))
                full = [(entry,item) for entry,item in usable
                    if item.valid_from<=start and item.valid_to>=end and item.status==DataQuality.AVAILABLE]
                conflict = any(
                    left.status==right.status==DataQuality.AVAILABLE
                    and max(left.valid_from,right.valid_from)<=min(left.valid_to,right.valid_to)
                    and (left.summary,left.road_state,first.weather_json if kind=='WEATHER' else None)
                        != (right.summary,right.road_state,second.weather_json if kind=='WEATHER' else None)
                    for i,(first,left) in enumerate(usable) for second,right in usable[i+1:])
                if conflict:
                    codes.add('CONFLICTING')
                if not full:
                    codes.update(unavailable)
                    if not codes:
                        codes.add('OUTSIDE_VALIDITY' if source else 'MISSING')
                # Do not hide a current contradictory/stale source behind a more
                # favourable complete record; never use future observations.
                # Only after comparing ALL contemporaneous observations may
                # identical full facts be de-duplicated by a stable source ID.
                # No newer/favourable source silently overrides disagreement.
                chosen = usable if codes or conflict else full[:1]
                for entry,item in chosen:
                    status = DataQuality.CONFLICTING if conflict else item.status
                    if status==DataQuality.AVAILABLE and not (item.valid_from<=start and item.valid_to>=end):
                        status=DataQuality.MISSING
                    evidence.append(item.model_copy(update={'status':status}))
                    selected.add(entry.case_id)
                if not chosen:
                    evidence.append(Evidence(kind=kind, summary=None, source_date=None, status='MISSING',valid_from=None,valid_to=None,
                        source_refs=[SourceRef.model_validate_json(dict(self._camp_refs)[campsite])]))
                # Include known ranges outside this trip as diagnostic data;
                # never advertise future/unpublished/stale records as usable.
                known_ranges=set()
                for entry in source:
                    item=Evidence.model_validate_json(entry.evidence_json)
                    if (entry.published is not None and entry.observed is not None
                            and max(entry.published,entry.observed)<=today
                            and (today-entry.observed).days<=entry.max_age_days
                            and item.status==DataQuality.AVAILABLE
                            and item.valid_from is not None and item.valid_to is not None
                            and (kind!='ROAD' or item.road_state in {RoadState.OPEN,RoadState.CLOSED})):
                        known_ranges.add((item.valid_from,item.valid_to))
                available=sorted(known_ranges)
                if codes:
                    for code in sorted(codes):
                        issues.append(CoverageIssue(campsite_id=campsite,kind=kind,code=code,
                            requested_range=requested,
                            available_ranges=[DateRange(start=a,end=b) for a,b in available],
                            uncovered_ranges=uncovered(start,end,available),
                            reason=('Single-record full-trip coverage is required; partial intervals are not spliced.'
                                    if code=='OUTSIDE_VALIDITY' else 'Evidence is unavailable, unobserved, stale, unknown or conflicting for this query.')))
                elif kind=='WEATHER':
                    weather_by_site[campsite] = WeatherFacts.model_validate_json(full[0][0].weather_json)
        # This is the QUERY envelope, not a union/extension of source validity.
        # Every Evidence and SourceRef retains its actual individual interval;
        # incomplete records are MISSING and gaps are reported above.
        scenario = ScenarioContext(scenario_id=POLICY_VERSION,campsite_ids=sorted(ids),
            valid_from=start, valid_to=end, evidence=evidence)
        body = {'selected_case_ids':sorted(selected),'scenario_context':scenario.model_dump(mode='json'),
                'weather_facts_by_campsite':{key:value.model_dump(mode='json') for key,value in weather_by_site.items()},
                'coverage_issues':[item.model_dump(mode='json') for item in issues]}
        identity = {'policy_version':POLICY_VERSION,'index_digest':self.index_digest,
                    'query':{'requirements':req.model_dump(mode='json'),'campsite_ids':sorted(ids),'demo_context':demo.model_dump(mode='json')},
                    'selection':body}
        return TripEvidenceSelection(**body,selection_digest=digest(identity))
