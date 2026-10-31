"""Versioned synthetic forecast inputs, separate from frozen dataset releases."""
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from ..adapters.synthetic_dataset import _unique_object
from ..adapters.catalogue_identity import SYDNEY_VERSION
from ..config import APP_ROOT
from ..contracts.dto import Provenance
from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..dataset_paths import data_file_path

POLICY_VERSION = 'sydney-weather-events-1'
POLICY_KEY = 'a_weather_events_policy'
DIGEST_KEY = 'a_weather_events_sha256'
REFERENCE_FILE = 'weather/sydney_weather_events_v1.json'
SNAPSHOT_FILE = 'data/synthetic_weather_events.json'


class WeatherFacts(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    temperature_min_c: StrictInt = Field(ge=-80, le=60)
    temperature_max_c: StrictInt = Field(ge=-80, le=60)
    forecast_rain_mm: StrictInt = Field(ge=0, le=1000)
    wind_kph: StrictInt = Field(ge=0, le=300)


class WeatherEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    event_id: str = Field(pattern=r'^[a-z0-9-]{1,100}$')
    campsite_id: str = Field(pattern=r'^[a-z0-9-]{1,100}$')
    snapshot_date: date
    valid_from: date
    valid_to: date
    summary: Literal['Heavy rain in synthetic forecast.']
    facts: WeatherFacts

    @field_validator('snapshot_date', 'valid_from', 'valid_to', mode='before')
    @classmethod
    def iso_dates(cls, value):
        if not isinstance(value, str) or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is None:
            raise ValueError('Forecast dates must be ISO strings')
        return value

    @model_validator(mode='after')
    def bounded_forecast(self):
        if (self.valid_from != self.snapshot_date or self.valid_to != self.snapshot_date + timedelta(days=6)
                or self.facts.temperature_min_c > self.facts.temperature_max_c):
            raise ValueError('Invalid forecast interval or temperatures')
        return self


class WeatherCatalogue(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal['sydney-weather-events-1']
    created_on: Literal['2026-10-31']
    scope: str = Field(min_length=1, max_length=300)
    provenance: Provenance
    events: tuple[WeatherEvent, ...] = Field(min_length=1, max_length=100)


@dataclass(frozen=True)
class WeatherInput:
    document: WeatherCatalogue
    payload: bytes
    sha256: str


def fail(message):
    raise ContractFailure(ContractError(code=ErrorCode.STALE_CONTEXT, message=message))


def checked_policy(policy):
    if policy not in {None, POLICY_VERSION}:
        fail('Unknown forecast-events policy. Retain the registered input version.')
    return policy


def read_reference(policy=POLICY_VERSION):
    checked_policy(policy)
    if policy is None:
        return None
    try:
        payload = data_file_path(APP_ROOT, REFERENCE_FILE).read_bytes()
        if len(payload) > 65536:
            raise ValueError('Forecast reference is too large')
        document = WeatherCatalogue.model_validate(json.loads(payload, object_pairs_hook=_unique_object))
        source = document.provenance
        if (source.source_type != 'SYNTHETIC' or not source.demo_only
                or source.source_name != 'CampMate Synthetic Demo Dataset v2' or source.source_date != '2026-10-07'
                or len({e.event_id for e in document.events}) != len(document.events)
                or len({(e.campsite_id, e.snapshot_date) for e in document.events}) != len(document.events)):
            raise ValueError('Invalid synthetic forecast identity')
        return WeatherInput(document, payload, hashlib.sha256(payload).hexdigest())
    except (OSError, ValueError, TypeError, OverflowError):
        fail('Synthetic forecast-event inputs are missing or invalid. Existing snapshots were retained.')


def validate_saved(context):
    policy = context.selection_config.get(POLICY_KEY)
    digest = context.selection_config.get(DIGEST_KEY)
    if policy is None and digest is None:
        return
    if context.dataset_version != SYDNEY_VERSION or policy is None:
        fail('Saved forecast-events identity is incomplete or belongs to another dataset.')
    reference = read_reference(policy)
    if reference.sha256 != digest:
        fail('Forecast-event bytes differ from this run. Retain its saved input identity.')
