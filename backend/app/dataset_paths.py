"""Shared source-path boundary, checked before A/B open any input bytes."""
from pathlib import Path


def data_file_path(root: Path, name: str, *, scenarios=False) -> Path:
    root = root.resolve(strict=True)
    # Do not resolve the allowlisted directory: a data/scenarios junction must
    # not turn its tests/ or external target into an allowed business directory.
    allowed = root / 'data' / 'scenarios' if scenarios else root / 'data'
    path = (root / 'data' / name).resolve(strict=True)
    if not path.is_relative_to(allowed):
        raise ValueError('Business source escapes the business data directory')
    return path


def manifest_file_path(root: Path) -> Path:
    root = root.resolve(strict=True)
    expected = root / 'manifest.json'
    path = expected.resolve(strict=True)
    if path != expected:
        raise ValueError('Manifest source must remain at the dataset root')
    return path
