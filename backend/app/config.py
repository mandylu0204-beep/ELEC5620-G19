from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .contracts.enums import ExecutionMode

APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CAMPMATE_", env_file=APP_ROOT / ".env",
        env_file_encoding="utf-8", extra="ignore",
    )
    execution_mode: ExecutionMode = ExecutionMode.STUB
    planning_enabled: bool = False
    logistics_execution: Literal['rules', 'model'] = 'rules'
    safety_execution: Literal['rules', 'model'] = 'rules'
    demo_today: date = date(2026, 10, 8)
    clock_mode: Literal['current', 'fixed'] = 'current'
    synthetic_evidence_mode: Literal['auto', 'sealed', 'rolling'] = 'auto'
    snapshot_cache_path: Path = APP_ROOT / 'var' / 'daily-snapshots'
    dataset_path: Path = APP_ROOT / "data" / "synthetic_demo"
    dataset_scenario_files: list[str] = Field(default_factory=list)
    dataset_selection: dict[str, str] = Field(default_factory=dict)
    workflow_safety_case_ids: list[str] = Field(default_factory=list)
    database_path: Path = APP_ROOT / "var" / "campmate.sqlite3"
    seed_demo_accounts: bool = True
    session_hours: int = Field(default=8, ge=1, le=168)
    secure_cookies: bool = False

    def __init__(self, **values):
        # Explicit Python test/CLI dates remain reproducible. A legacy .env date
        # alone does not override the normal, live Sydney clock.
        if 'demo_today' in values and 'clock_mode' not in values:
            values['clock_mode'] = 'fixed'
        super().__init__(**values)

    def checking_date(self):
        return self.demo_today if self.clock_mode == 'fixed' else sydney_today()

    @field_validator("dataset_path", "database_path", "snapshot_cache_path", mode="before")
    @classmethod
    def resolve_project_path(cls, value):
        path = Path(value).expanduser()
        return (APP_ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def sydney_today():
    return datetime.now(ZoneInfo('Australia/Sydney')).date()
