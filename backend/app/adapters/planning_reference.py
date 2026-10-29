"""Versioned, bounded onsite suggestions; the sealed campsite package is untouched."""
from datetime import date, datetime, time, timedelta
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ..config import APP_ROOT
from ..contracts.dto import ItineraryEntry, Provenance, SourceRef
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure

POLICY_KEY = 'b_planning_details'
LEGACY_POLICY_VERSION = 'camp-activities-1'
POLICY_VERSION = 'camp-activities-2'
LEGACY_REFERENCE_KEY = 'planning/camp_activities_v1.json'
REFERENCE_KEY = 'planning/camp_activities_v2.json'
REFERENCE_PATH = APP_ROOT / 'data' / REFERENCE_KEY
LEGACY_REFERENCE_PATH = APP_ROOT / 'data' / LEGACY_REFERENCE_KEY


class Activity(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    activity_id: str = Field(pattern=r'^[a-z0-9-]{1,100}$')
    campsite_id: str = Field(pattern=r'^[a-z0-9-]{1,100}$')
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)
    category: Literal['ONSITE_LEISURE', 'ONSITE_DEPARTURE']
    intensity: Literal['LOW']
    additional_cost_cents: StrictInt = Field(ge=0, le=0)
    requires_booking: Literal[False]
    additional_equipment: tuple[str, ...] = Field(max_length=0)
    valid_from: date
    valid_to: date
    weather_dependency: Literal['EXISTING_SAFETY_CHECK']
    availability: Literal['SUGGESTION_ONLY']

    @property
    def saved_description(self):
        return self.title + '：' + self.description + '（模拟活动建议；须以正式安全检查和现场条件为准。）'


class Reference(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal['camp-activities-1', 'camp-activities-2']
    created_on: Literal['2026-10-29']
    scope: str
    provenance: Provenance
    activities: tuple[Activity, ...] = Field(min_length=1, max_length=30)


def fail(message):
    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message=message))


def checked_policy(value):
    if value not in {None, LEGACY_POLICY_VERSION, POLICY_VERSION}:
        fail('行程资料版本不受支持，请联系项目负责人。')
    return value


def reference_key(policy):
    checked_policy(policy)
    return LEGACY_REFERENCE_KEY if policy == LEGACY_POLICY_VERSION else REFERENCE_KEY


def read_reference(policy=POLICY_VERSION):
    try:
        from .synthetic_dataset import _unique_object
        checked_policy(policy)
        path = LEGACY_REFERENCE_PATH if policy == LEGACY_POLICY_VERSION else REFERENCE_PATH
        payload = path.read_bytes()
        value = Reference.model_validate(json.loads(payload, object_pairs_hook=_unique_object))
        if (value.version != policy or value.provenance.source_type != 'SYNTHETIC' or not value.provenance.demo_only
                or len({row.activity_id for row in value.activities}) != len(value.activities)
                or any(row.valid_from > row.valid_to for row in value.activities)):
            raise ValueError('Invalid onsite catalogue')
        return value, hashlib.sha256(payload).hexdigest()
    except (OSError, ValueError, TypeError):
        fail('模拟活动资料缺失或无效，不能生成替代活动。')


def enabled(context):
    return checked_policy(context.selection_config.get(POLICY_KEY)) is not None


def register_reference(context):
    if not enabled(context):
        return context
    if context.dataset_version != '2.2.0':
        fail('新的行程资料只登记在 Sydney 2.2 数据上。')
    policy = context.selection_config[POLICY_KEY]
    key = reference_key(policy)
    reference, digest = read_reference(policy)
    if context.file_digests.get(key, digest) != digest:
        fail('活动资料与本次运行登记的字节不同。')
    return context.model_copy(update={'file_digests': {**context.file_digests, key: digest}}, deep=True)


def bind_reference(dataset, context):
    dataset.planning_reference = None
    if not enabled(context):
        return
    policy = context.selection_config[POLICY_KEY]
    key = reference_key(policy)
    reference, digest = read_reference(policy)
    if (context.file_digests.get(key) != digest
            or not {row.campsite_id for row in reference.activities}.issubset({row.campsite_id for row in dataset.campsites})):
        fail('活动资料不属于本次绑定的数据快照。')
    dataset.planning_reference = reference


def available_activities(dataset, campsite_id, requirements, *, include_departure=False):
    reference = getattr(dataset, 'planning_reference', None)
    if reference is None:
        return []
    return [row for row in reference.activities if row.campsite_id == campsite_id
        and (include_departure or row.category == 'ONSITE_LEISURE')
        and row.valid_from <= requirements.start_date and row.valid_to >= requirements.end_date]


def activity_source(dataset, activity):
    return SourceRef(dataset_file=reference_key(dataset.planning_reference.version), record_id=activity.activity_id,
        provenance=dataset.planning_reference.provenance,
        valid_from=activity.valid_from, valid_to=activity.valid_to)


def known_activity(dataset, entry, content, requirements):
    if entry.entry_kind != 'ACTIVITY':
        return False
    from ..agents.rules.common import TRIP_ZONE
    start, end = entry.start_at.astimezone(TRIP_ZONE), entry.end_at.astimezone(TRIP_ZONE)
    for row in available_activities(dataset, entry.campsite_id, requirements, include_departure=True):
        expected = (time(10), time(11)) if row.category == 'ONSITE_DEPARTURE' else (time(13), time(16))
        correct_day = start.date() == requirements.end_date if row.category == 'ONSITE_DEPARTURE' else requirements.start_date <= start.date() < requirements.end_date
        if (entry.description == row.saved_description and activity_source(dataset, row) in content.source_refs
                and correct_day and start.date() == end.date() and (start.time(), end.time()) == expected):
            return True
    return False


def daily_entries(dataset, campsite, requirements, choices):
    from ..agents.rules.common import TRIP_ZONE, camp_description
    catalogue = {row.activity_id: row for row in available_activities(dataset, campsite.campsite_id, requirements)}
    days = [requirements.start_date + timedelta(days=i) for i in range(requirements.duration_nights)]
    if [row.date for row in choices] != days or any(row.activity_id not in catalogue for row in choices):
        raise ValueError('Daily choices must cover each occupied date using this campsite catalogue')
    entries, refs = [], []
    for index, choice in enumerate(choices):
        activity = catalogue[choice.activity_id]
        # A suggested afternoon block and a separate overnight stay, never a
        # claimed check-in, actual activity duration or transport timetable.
        entries.append(ItineraryEntry(entry_kind='ACTIVITY',
            start_at=datetime.combine(choice.date, time(13), TRIP_ZONE),
            end_at=datetime.combine(choice.date, time(16), TRIP_ZONE),
            campsite_id=campsite.campsite_id, description=activity.saved_description))
        entries.append(ItineraryEntry(entry_kind='CAMP',
            start_at=datetime.combine(choice.date, time(17), TRIP_ZONE),
            end_at=datetime.combine(choice.date + timedelta(days=1), time(10 if index == len(days)-1 else 8), TRIP_ZONE),
            campsite_id=campsite.campsite_id, description=camp_description(campsite)))
        ref = activity_source(dataset, activity)
        if ref not in refs:
            refs.append(ref)
    departure = next((row for row in available_activities(dataset, campsite.campsite_id, requirements,
        include_departure=True) if row.category == 'ONSITE_DEPARTURE'), None)
    if departure:
        entries.append(ItineraryEntry(entry_kind='ACTIVITY',
            start_at=datetime.combine(requirements.end_date, time(10), TRIP_ZONE),
            end_at=datetime.combine(requirements.end_date, time(11), TRIP_ZONE),
            campsite_id=campsite.campsite_id, description=departure.saved_description))
        refs.append(activity_source(dataset, departure))
    return entries, refs
