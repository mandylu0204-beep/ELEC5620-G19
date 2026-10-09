from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv('CAMPMATE_DATABASE_PATH', str(tmp_path / 'campmate.sqlite3'))


def pytest_configure(config):
    # pytest clears basetemp between runs. Verify that it stays in our generated area.
    project_root = Path(__file__).resolve().parents[2]
    generated_root = (project_root / 'var').resolve()
    temp_path = Path(config.option.basetemp).resolve() if config.option.basetemp else generated_root / 'pytest-temp'
    if not temp_path.is_relative_to(generated_root) or temp_path == generated_root:
        raise pytest.UsageError('Keep --basetemp below campmate_app/var to protect source files.')
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(temp_path)
