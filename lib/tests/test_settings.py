import pytest
from labkit import LabSettings, SettingsError, load_settings

ENV_VARS = (
    "LAB_SERVICE_NAME",
    "LAB_LOG_LEVEL",
    "LAB_LOG_FORMAT",
    "LAB_AWS_REGION",
    "LAB_BATCH_SIZE",
    "QUEUE_ENDPOINT",
    "S3_ENDPOINT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LAB_SERVICE_NAME", "demo-service")


def test_defaults_with_only_service_name():
    settings = load_settings()

    assert isinstance(settings, LabSettings)
    assert settings.service_name == "demo-service"
    assert settings.log_level == "INFO"
    assert settings.log_format == "json"
    assert settings.aws_region == "us-east-1"
    assert settings.queue_endpoint is None
    assert settings.s3_endpoint is None


def test_env_vars_override_each_field(monkeypatch):
    monkeypatch.setenv("LAB_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LAB_LOG_FORMAT", "console")
    monkeypatch.setenv("LAB_AWS_REGION", "eu-west-1")
    monkeypatch.setenv("QUEUE_ENDPOINT", "http://queue.test:9324")
    monkeypatch.setenv("S3_ENDPOINT", "http://s3.test:9000")

    settings = load_settings()

    assert settings.log_level == "DEBUG"
    assert settings.log_format == "console"
    assert settings.aws_region == "eu-west-1"
    assert settings.queue_endpoint == "http://queue.test:9324"
    assert settings.s3_endpoint == "http://s3.test:9000"


def test_endpoints_are_none_when_removed(monkeypatch):
    monkeypatch.setenv("QUEUE_ENDPOINT", "http://queue.test:9324")
    monkeypatch.setenv("S3_ENDPOINT", "http://s3.test:9000")
    monkeypatch.delenv("QUEUE_ENDPOINT")
    monkeypatch.delenv("S3_ENDPOINT")

    settings = load_settings()

    assert settings.queue_endpoint is None
    assert settings.s3_endpoint is None


def test_endpoints_ignore_prefixed_names(monkeypatch):
    monkeypatch.setenv("LAB_QUEUE_ENDPOINT", "http://queue.test:9324")
    monkeypatch.setenv("LAB_S3_ENDPOINT", "http://s3.test:9000")

    settings = load_settings()

    assert settings.queue_endpoint is None
    assert settings.s3_endpoint is None


def test_missing_service_name_names_env_var(monkeypatch):
    monkeypatch.delenv("LAB_SERVICE_NAME")

    with pytest.raises(SettingsError) as excinfo:
        load_settings()

    assert "LAB_SERVICE_NAME is required" in str(excinfo.value)


def test_invalid_log_level_names_env_var(monkeypatch):
    monkeypatch.setenv("LAB_LOG_LEVEL", "VERBOSE")

    with pytest.raises(SettingsError) as excinfo:
        load_settings()

    assert "LAB_LOG_LEVEL" in str(excinfo.value)


def test_every_error_is_reported(monkeypatch):
    monkeypatch.delenv("LAB_SERVICE_NAME")
    monkeypatch.setenv("LAB_LOG_FORMAT", "xml")

    with pytest.raises(SettingsError) as excinfo:
        load_settings()

    message = str(excinfo.value)
    assert "LAB_SERVICE_NAME" in message
    assert "LAB_LOG_FORMAT" in message


class WorkerSettings(LabSettings):
    batch_size: int = 8


def test_subclass_field_defaults():
    settings = load_settings(WorkerSettings)

    assert isinstance(settings, WorkerSettings)
    assert settings.batch_size == 8


def test_subclass_field_reads_prefixed_env_var(monkeypatch):
    monkeypatch.setenv("LAB_BATCH_SIZE", "32")

    assert load_settings(WorkerSettings).batch_size == 32


def test_subclass_field_error_names_env_var(monkeypatch):
    monkeypatch.setenv("LAB_BATCH_SIZE", "many")

    with pytest.raises(SettingsError) as excinfo:
        load_settings(WorkerSettings)

    message = str(excinfo.value)
    assert "LAB_BATCH_SIZE" in message
    assert "batch_size" not in message.replace("LAB_BATCH_SIZE", "")
