from datetime import date
from pathlib import Path

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
    demo_today: date = date(2026, 10, 8)
    dataset_path: Path = APP_ROOT / "data" / "synthetic_demo"
    dataset_scenario_files: list[str] = Field(default_factory=list)
    dataset_selection: dict[str, str] = Field(default_factory=dict)
    workflow_safety_case_ids: list[str] = Field(default_factory=list)
    database_path: Path = APP_ROOT / "var" / "campmate.sqlite3"
    seed_demo_accounts: bool = True
    session_hours: int = Field(default=8, ge=1, le=168)
    secure_cookies: bool = False

    @field_validator("dataset_path", "database_path", mode="before")
    @classmethod
    def resolve_project_path(cls, value):
        path = Path(value).expanduser()
        return (APP_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
