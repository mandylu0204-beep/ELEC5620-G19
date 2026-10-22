"""Owned, immutable safety sources; materialization always returns detached values."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from pydantic import BaseModel, ValidationError

from ..contracts.dto import Evidence, Provenance, ScenarioContext, SourceRef
from ..contracts.enums import DataQuality, RoadState
from .models import SafetyRecord

FORMAT_VERSION = 'safety-source-image-1'
MODEL_TYPES = frozenset((SafetyRecord, Evidence, Provenance, ScenarioContext, SourceRef))


class UnsupportedArchive(ValueError):
    """Use the existing detached deep-copy representation for unfamiliar state."""


def model_shape(value):
    if isinstance(value, BaseModel):
        if (type(value) not in MODEL_TYPES or value.__pydantic_private__ is not None
                or value.__pydantic_extra__ is not None
                or set(vars(value)) != set(type(value).model_fields)):
            raise UnsupportedArchive('Unregistered model type or instance state')
        return (type(value), frozenset(value.model_fields_set),
                tuple((key, model_shape(getattr(value, key))) for key in type(value).model_fields))
    if type(value) is list:
        return (list, tuple(model_shape(item) for item in value))
    if type(value) is dict:
        return (dict, tuple((key, model_shape(item)) for key, item in value.items()))
    if type(value) not in (str, int, bool, float, type(None), Decimal, date, datetime, DataQuality, RoadState):
        raise UnsupportedArchive('Unregistered model field state')
    return type(value)


class ImmutableCopy:
    __slots__ = ()

    def __deepcopy__(self, memo):
        if type(self) not in (SafetyArchive, RawSafetyArchive, FrozenMap, FrozenList, FrozenTuple):
            raise UnsupportedArchive('Unknown immutable archive subclass')
        return self


@dataclass(frozen=True, slots=True)
class SafetyArchive(ImmutableCopy, Mapping):
    entries: tuple[tuple[str, str], ...]
    _index: Mapping = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if (type(self.entries) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                or any(type(item) is not str for item in pair) for pair in self.entries)
                or len(dict(self.entries)) != len(self.entries)):
            raise UnsupportedArchive('Invalid safety archive entries')
        object.__setattr__(self, '_index', MappingProxyType(dict(self.entries)))

    @classmethod
    def capture(cls, records):
        if type(records) is not dict:
            raise UnsupportedArchive('Unknown safety table representation')
        entries = []
        for key, record in records.items():
            if type(key) is not str or type(record) is not SafetyRecord:
                raise UnsupportedArchive('Unregistered safety record type')
            shape = model_shape(record)
            payload = record.model_dump_json(exclude_unset=True)
            try:
                restored = SafetyRecord.model_validate_json(payload)
            except ValidationError as exc:
                raise UnsupportedArchive('Safety record cannot round trip') from exc
            if (shape != model_shape(restored) or record.model_dump_json() != restored.model_dump_json()
                    or payload != restored.model_dump_json(exclude_unset=True)):
                raise UnsupportedArchive('Safety record state differs after materialization')
            entries.append((key, payload))
        return cls(tuple(entries))

    def __getitem__(self, key):
        # Fixed type only; no dynamic import/model_construct or shared DTO cache.
        return SafetyRecord.model_validate_json(self._index[key])

    def __iter__(self):
        return iter(self._index)

    def __len__(self):
        return len(self.entries)


@dataclass(frozen=True, slots=True)
class FrozenMap(ImmutableCopy):
    entries: tuple

    def __post_init__(self):
        if type(self.entries) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not str or not frozen_value(pair[1]) for pair in self.entries):
            raise UnsupportedArchive('Invalid frozen map')
        if len(dict(self.entries)) != len(self.entries):
            raise UnsupportedArchive('Duplicate frozen map key')


@dataclass(frozen=True, slots=True)
class FrozenList(ImmutableCopy):
    values: tuple

    def __post_init__(self):
        if type(self.values) is not tuple or not all(frozen_value(item) for item in self.values):
            raise UnsupportedArchive('Invalid frozen list')


@dataclass(frozen=True, slots=True)
class FrozenTuple(ImmutableCopy):
    values: tuple

    def __post_init__(self):
        if type(self.values) is not tuple or not all(frozen_value(item) for item in self.values):
            raise UnsupportedArchive('Invalid frozen tuple')


def frozen_value(value):
    return type(value) in (str, int, bool, type(None), Decimal, FrozenMap, FrozenList, FrozenTuple)


def freeze(value):
    if type(value) in (str, int, bool, type(None), Decimal):
        return value
    if type(value) is dict and all(type(key) is str for key in value):
        return FrozenMap(tuple((key, freeze(item)) for key, item in value.items()))
    if type(value) is list:
        return FrozenList(tuple(freeze(item) for item in value))
    if type(value) is tuple:
        return FrozenTuple(tuple(freeze(item) for item in value))
    raise UnsupportedArchive('Unregistered raw policy value type')


def thaw(value):
    if type(value) is FrozenMap:
        return {key: thaw(item) for key, item in value.entries}
    if type(value) is FrozenList:
        return [thaw(item) for item in value.values]
    if type(value) is FrozenTuple:
        return tuple(thaw(item) for item in value.values)
    return value


@dataclass(frozen=True, slots=True)
class RawSafetyArchive(ImmutableCopy, Mapping):
    entries: tuple
    _index: Mapping = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if type(self.entries) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                or type(pair[0]) is not str or type(pair[1]) is not FrozenMap for pair in self.entries):
            raise UnsupportedArchive('Invalid raw safety archive entries')
        if len(dict(self.entries)) != len(self.entries):
            raise UnsupportedArchive('Duplicate raw safety archive key')
        # Check node ownership recursively even for direct internal construction.
        for _, node in self.entries:
            if freeze(thaw(node)) != node:
                raise UnsupportedArchive('Invalid frozen policy tree')
        object.__setattr__(self, '_index', MappingProxyType(dict(self.entries)))

    @classmethod
    def capture(cls, rows):
        if type(rows) is not dict or any(type(key) is not str or type(row) is not dict for key, row in rows.items()):
            raise UnsupportedArchive('Unknown raw safety table representation')
        return cls(tuple((key, freeze(row)) for key, row in rows.items()))

    def __getitem__(self, key):
        return thaw(self._index[key])

    def __iter__(self):
        return iter(self._index)

    def __len__(self):
        return len(self.entries)


def compact_owned_dataset(dataset):
    """Only alter known fields on an already detached cold snapshot.

    Unfamiliar subclasses/state keep the conservative original deep-copy path.
    All other Dataset fields and selector objects remain normally deep-copied.
    """
    from .synthetic_dataset import SyntheticDataset
    if type(dataset) is not SyntheticDataset:
        return dataset
    try:
        safety = SafetyArchive.capture(dataset._safety)
    except UnsupportedArchive:
        pass
    else:
        dataset._safety = safety
    policy = dataset._v2_policy
    if type(policy) is dict and type(policy.get('safety')) is dict:
        try:
            rows = RawSafetyArchive.capture(policy['safety'])
        except UnsupportedArchive:
            pass
        else:
            policy['safety'] = rows
    return dataset
