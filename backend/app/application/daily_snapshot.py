"""A-owned daily synthetic input snapshots, separate from sealed source data.

Generation takes only the inspected base package and a Sydney calendar date.
Existing snapshots are verified, never repaired/overwritten behind a saved run.
"""
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock

from ..contracts.enums import ErrorCode
from ..contracts.errors import ContractError, ContractFailure
from ..dataset_paths import data_file_path, manifest_file_path
from .datasets import inspect_dataset
from .synthetic_generation import build
from ..adapters.catalogue_identity import TRIP_DATASET_VERSIONS
from ..adapters.catalogue_identity import SYDNEY_VERSION
from .weather_events import (POLICY_VERSION as WEATHER_POLICY, POLICY_KEY as WEATHER_KEY,
    DIGEST_KEY as WEATHER_DIGEST, checked_policy, read_reference)

POLICY = 'synthetic-daily-v1'
_lock = RLock()
_expected = {}


def failure(message):
    return ContractFailure(ContractError(code=ErrorCode.ADAPTER_FAILURE, message=message))


def effective_settings(settings, today, *, base=None, weather_policy=WEATHER_POLICY):
    try:
        return _effective_settings(settings,today,base=base,weather_policy=weather_policy)
    except (OSError,OverflowError) as exc:
        raise failure('Daily simulated information could not be read or generated. Original data and plans are retained.') from exc


def _effective_settings(settings, today, *, base=None, weather_policy=WEATHER_POLICY):
    checked_policy(weather_policy)
    base = base or inspect_dataset(settings)
    rolling = settings.synthetic_evidence_mode == 'rolling' or (
        settings.synthetic_evidence_mode == 'auto' and settings.clock_mode == 'current'
        and base.context.dataset_version in TRIP_DATASET_VERSIONS)
    if not rolling:
        return settings
    if (base.context.dataset_version not in TRIP_DATASET_VERSIONS or settings.dataset_scenario_files
            or settings.workflow_safety_case_ids or settings.dataset_selection):
        raise failure('Daily information requires a supported itinerary dataset and automatic source selection. For fixed scenarios, use  sealed mode.')
    reference = read_reference(weather_policy) if base.context.dataset_version == SYDNEY_VERSION else None
    weather = reference if reference is not None and any(
        event.snapshot_date == today for event in reference.document.events) else None
    identity_values = {
        'base':base.context.model_dump(mode='json'), 'date':today.isoformat(), 'policy':POLICY,
    }
    if weather is not None:
        identity_values['weather_events'] = {'policy':weather.document.version, 'sha256':weather.sha256}
    identity = hashlib.sha256(json.dumps(identity_values,sort_keys=True).encode()).hexdigest()
    raw_cache=settings.snapshot_cache_path
    for path in (raw_cache,*raw_cache.parents):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise failure('Daily snapshot cache cannot use a directory symlink.')
    cache = raw_cache.resolve()
    source = settings.dataset_path.resolve()
    if cache == source or cache.is_relative_to(source) or source.is_relative_to(cache):
        raise failure('Daily information cache must be separate from the original data directory.')
    target = cache / today.isoformat() / identity
    # Reject link redirection before creating or reading cache content.
    for path in (cache, target.parent, target):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise failure('Daily snapshot cache cannot use a directory symlink.')
    with _lock:
        key=(str(source),identity)
        if key not in _expected:
            content=build(source,[(today.isoformat(),(today+timedelta(days=30)).isoformat())],
                rolling_day=today,weather_events=weather)
            if inspect_dataset(settings) != base:
                raise failure('Base data changed during generation. Please retry.')
            _expected[key]=content
            if len(_expected)>32:
                del _expected[next(iter(_expected))]
        content=_expected[key]
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.building-',dir=target.parent) as temporary:
                staging=Path(temporary)/'snapshot'
                staging.mkdir()
                for name,payload in content.items():
                    path=staging/name
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(payload)
                try:
                    os.rename(staging,target)
                except OSError:
                    if not target.is_dir():
                        raise
        try:
            # Compare against deterministic expected bytes, not just a possibly
            # resealed manifest. A corrupt snapshot cannot silently be replaced.
            for name,payload in content.items():
                if name.startswith('data/'):
                    path=data_file_path(target,name[5:])
                elif name=='manifest.json':
                    path=manifest_file_path(target)
                else:
                    continue
                if path.read_bytes()!=payload:
                    raise ValueError('Changed snapshot bytes')
        except (OSError,ValueError) as exc:
            raise failure('Registered daily snapshot is damaged or changed. Historical data was not overwritten.') from exc
    return settings.model_copy(update={
        'dataset_path':target,
        'dataset_selection':{'a_daily_snapshot':POLICY,'a_snapshot_date':today.isoformat(),
                             'a_snapshot_base':identity,'a_clock_mode':settings.clock_mode,
                             **({WEATHER_KEY:weather.document.version, WEATHER_DIGEST:weather.sha256}
                                if weather is not None else {})},
    })
