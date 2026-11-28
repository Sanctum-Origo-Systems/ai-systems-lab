"""Service configuration read from environment variables.

Every service builds its config from `LabSettings` (or a subclass) via `load_settings`.
Fields read from `LAB_<FIELD_NAME>`, except the endpoint overrides, which use the
unprefixed names the AWS-compatible local services expect.
"""

from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

ENV_PREFIX = "LAB_"


class SettingsError(Exception):
    """Raised when the environment does not describe a valid configuration."""


class LabSettings(BaseSettings):
    """Settings shared by every service. Subclass to add service-specific fields."""

    model_config = SettingsConfigDict(env_prefix=ENV_PREFIX, env_file=None, extra="ignore")

    service_name: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    aws_region: str = "us-east-1"
    # None means "use AWS"; set to point at a local stand-in.
    queue_endpoint: str | None = Field(default=None, validation_alias="QUEUE_ENDPOINT")
    s3_endpoint: str | None = Field(default=None, validation_alias="S3_ENDPOINT")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Environment only: compose passes the environment, no .env or secrets files.
        return (init_settings, env_settings)


def _env_var_names(cls: type[LabSettings]) -> dict[str, str]:
    """Map each field name and alias that can appear in an error location to its env var."""
    prefix = cls.model_config.get("env_prefix", "")
    names: dict[str, str] = {}
    for field_name, info in cls.model_fields.items():
        alias = info.validation_alias
        env = alias if isinstance(alias, str) else f"{prefix}{field_name}"
        names[field_name] = env.upper()
        if isinstance(alias, str):
            names[alias] = env.upper()
    return names


def _describe(exc: ValidationError, cls: type[LabSettings]) -> str:
    env_names = _env_var_names(cls)
    problems = []
    for error in exc.errors():
        loc = error.get("loc") or ("",)
        key = str(loc[0])
        env = env_names.get(key, key.upper())
        if error["type"] == "missing":
            problems.append(f"{env} is required")
        else:
            problems.append(f"{env}: {error['msg']}")
    return "invalid settings: " + "; ".join(problems)


def load_settings[T: LabSettings](cls: type[T] = LabSettings) -> T:
    """Build `cls` from the environment, raising SettingsError that names bad env vars."""
    try:
        return cls()
    except ValidationError as exc:
        raise SettingsError(_describe(exc, cls)) from None
