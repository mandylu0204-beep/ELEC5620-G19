"""Independent opt-in school proxy settings; never change the app's .env."""
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENV = Path(__file__).resolve().parents[3] / '.env.llm.local'


class CampusModelSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=LOCAL_ENV, env_file_encoding='utf-8', extra='ignore',
        populate_by_name=True, frozen=True, hide_input_in_errors=True,
    )
    api_key: SecretStr = Field(default=SecretStr(''), validation_alias='ELEC5620_API_KEY',
        repr=False, exclude=True)
    base_url: str = Field(default='http://10.167.60.148:8000/v1', validation_alias='ELEC5620_BASE_URL')
    model: Literal['campus-qwen'] = Field(default='campus-qwen', validation_alias='ELEC5620_MODEL')
    timeout_seconds: float = Field(default=45, gt=0, le=120, allow_inf_nan=False,
        validation_alias='ELEC5620_TIMEOUT_SECONDS')
    max_completion_tokens: int = Field(default=4096, ge=128, le=8192,
        validation_alias='ELEC5620_MAX_COMPLETION_TOKENS')
    max_attempts: int = Field(default=2, ge=1, le=3, validation_alias='ELEC5620_MAX_ATTEMPTS')
    max_turns: int = Field(default=4, ge=2, le=6, validation_alias='ELEC5620_MAX_TURNS')
    # Explicit opt-in only. The school proxy accepted low in live diagnostics;
    # unsupported provider/template overrides are deliberately not forwarded.
    reasoning_effort: Literal['low'] | None = Field(default=None,
        validation_alias='ELEC5620_REASONING_EFFORT')

    @field_validator('base_url')
    @classmethod
    def valid_endpoint(cls, value):
        value = value.rstrip('/')
        parsed = urlsplit(value)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path != '/v1'):
            raise ValueError('Use an HTTP(S) proxy base URL ending in /v1, without credentials/query/fragment.')
        parsed.port  # Reject malformed port numbers before sending credentials.
        return value

    @field_validator('timeout_seconds', 'max_completion_tokens', 'max_attempts', 'max_turns', mode='before')
    @classmethod
    def no_boolean_limits(cls, value):
        if isinstance(value, bool):
            raise ValueError('Limits must be numeric, not boolean.')
        return value

    def public_identity(self):
        """Only non-secret configuration may participate in saved run identity."""
        # Preserve pre-option identities when the option is not enabled.
        return self.model_dump(mode='json', exclude_none=True)
