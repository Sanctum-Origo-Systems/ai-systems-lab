import io
import json
import logging
import re

import pytest
from labkit import LabSettings, configure_from_settings, configure_logging

TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
CONSOLE_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2} [A-Z]+ [\w.]+: .*$")


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
    root.setLevel(level)


def lines(stream: io.StringIO) -> list[str]:
    return stream.getvalue().splitlines()


def test_json_line_has_required_keys():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)

    logging.getLogger("demo.worker").info("job started")

    [line] = lines(stream)
    record = json.loads(line)
    assert {"ts", "level", "logger", "msg", "service"} <= record.keys()
    assert record["service"] == "demo-service"
    assert record["level"] == "INFO"
    assert record["logger"] == "demo.worker"
    assert record["msg"] == "job started"


def test_json_ts_is_iso8601_utc_with_z():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)
    logger = logging.getLogger("demo.clock")
    # A fixed creation time, so the check does not depend on the real clock.
    record = logger.makeRecord("demo.clock", logging.INFO, __file__, 1, "tick", None, None)
    record.created = 1_700_000_000.25

    logger.handle(record)

    ts = json.loads(lines(stream)[0])["ts"]
    assert TS_PATTERN.match(ts), ts


def test_json_extra_keys_are_top_level():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)

    logging.getLogger("demo").info("batch done", extra={"batch_id": "b-7", "count": 3})

    record = json.loads(lines(stream)[0])
    assert record["batch_id"] == "b-7"
    assert record["count"] == 3


def test_records_below_level_are_dropped():
    stream = io.StringIO()
    configure_logging("demo-service", level="INFO", stream=stream)

    logging.getLogger("demo").debug("noisy detail")

    assert stream.getvalue() == ""


def test_configuring_twice_keeps_one_handler():
    first, second = io.StringIO(), io.StringIO()
    configure_logging("demo-service", stream=first)
    configure_logging("demo-service", stream=second)

    logging.getLogger("demo").info("once")

    assert first.getvalue() == ""
    assert len(lines(second)) == 1


def test_exception_includes_traceback():
    stream = io.StringIO()
    configure_logging("demo-service", stream=stream)

    try:
        raise ValueError("bad input shape")
    except ValueError:
        logging.getLogger("demo").exception("request failed")

    [line] = lines(stream)
    record = json.loads(line)
    assert "Traceback" in record["exc"]
    assert "bad input shape" in record["exc"]


def test_console_format_with_sorted_extras():
    stream = io.StringIO()
    configure_logging("demo-service", fmt="console", stream=stream)

    logging.getLogger("demo.api").warning("slow call", extra={"zeta": 1, "alpha": "x"})

    [line] = lines(stream)
    assert CONSOLE_PATTERN.match(line), line
    assert line.endswith(" WARNING demo.api: slow call alpha=x zeta=1")


def test_configure_from_settings_json():
    stream = io.StringIO()
    settings = LabSettings(service_name="settings-service", log_level="WARNING", log_format="json")
    configure_from_settings(settings, stream=stream)
    logger = logging.getLogger("demo")

    logger.info("dropped")
    logger.warning("kept")

    [line] = lines(stream)
    record = json.loads(line)
    assert record["service"] == "settings-service"
    assert record["msg"] == "kept"


def test_configure_from_settings_console():
    stream = io.StringIO()
    settings = LabSettings(service_name="settings-service", log_level="DEBUG", log_format="console")
    configure_from_settings(settings, stream=stream)

    logging.getLogger("demo").debug("visible")

    [line] = lines(stream)
    assert CONSOLE_PATTERN.match(line), line
    assert line.endswith(" DEBUG demo: visible")
