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

POLICY = 'synthetic-daily-v1'
_lock = RLock()
_expected = {}


def failure(message):
    return ContractFailure(ContractError(code=ErrorCode.ADAPTER_FAILURE, message=message))


def effective_settings(settings, today, *, base=None):
    try:
        return _effective_settings(settings,today,base=base)
    except (OSError,OverflowError) as exc:
        raise failure('每日模拟资料暂时无法读取或生成；原资料和方案均已保留。') from exc


def _effective_settings(settings, today, *, base=None):
    base = base or inspect_dataset(settings)
    rolling = settings.synthetic_evidence_mode == 'rolling' or (
        settings.synthetic_evidence_mode == 'auto' and settings.clock_mode == 'current'
        and base.context.dataset_version in TRIP_DATASET_VERSIONS)
    if not rolling:
        return settings
    if (base.context.dataset_version not in TRIP_DATASET_VERSIONS or settings.dataset_scenario_files
            or settings.workflow_safety_case_ids or settings.dataset_selection):
        raise failure('每日资料需要受支持的行程数据包和自动资料选择；固定场景请使用 sealed 模式。')
    identity = hashlib.sha256(json.dumps({
        'base':base.context.model_dump(mode='json'), 'date':today.isoformat(), 'policy':POLICY,
    },sort_keys=True).encode()).hexdigest()
    raw_cache=settings.snapshot_cache_path
    for path in (raw_cache,*raw_cache.parents):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise failure('每日资料缓存不能经过目录链接。')
    cache = raw_cache.resolve()
    source = settings.dataset_path.resolve()
    if cache == source or cache.is_relative_to(source) or source.is_relative_to(cache):
        raise failure('每日资料缓存必须与原始数据目录分开。')
    target = cache / today.isoformat() / identity
    # Reject link redirection before creating or reading cache content.
    for path in (cache, target.parent, target):
        if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):
            raise failure('每日资料缓存不能经过目录链接。')
    with _lock:
        key=(str(source),identity)
        if key not in _expected:
            content=build(source,[(today.isoformat(),(today+timedelta(days=30)).isoformat())],rolling_day=today)
            if inspect_dataset(settings) != base:
                raise failure('基础数据在生成期间变化，请重试。')
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
            raise failure('已登记的每日模拟快照损坏或变化，未覆盖历史资料。') from exc
    return settings.model_copy(update={
        'dataset_path':target,
        'dataset_selection':{'a_daily_snapshot':POLICY,'a_snapshot_date':today.isoformat(),
                             'a_snapshot_base':identity,'a_clock_mode':settings.clock_mode},
    })
