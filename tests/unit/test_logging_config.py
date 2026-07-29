import logging

import pytest

from jarvis.logging_config import (
    ColorLevelFormatter,
    HealthCheckAccessFilter,
    configure_logging,
)


@pytest.mark.parametrize(
    ("level", "label", "color"),
    [
        (logging.INFO, "INFO", "\x1b[32m"),
        (logging.WARNING, "WARN", "\x1b[33m"),
        (logging.ERROR, "ERROR", "\x1b[31m"),
    ],
)
def test_formatter_colors_supported_level_labels(level, label, color):
    formatter = ColorLevelFormatter("%(levelname)s %(message)s", use_color=True)
    record = logging.LogRecord("jarvis.test", level, __file__, 1, "message", (), None)

    rendered = formatter.format(record)

    assert rendered == f"{color}{label}\x1b[0m message"
    assert record.levelname == logging.getLevelName(level)


def test_formatter_honors_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    formatter = ColorLevelFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        "jarvis.test", logging.WARNING, __file__, 1, "message", (), None
    )

    assert formatter.format(record) == "WARN message"


def _uvicorn_access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("10.0.0.15:1234", "GET", path, "1.1", 200),
        None,
    )


@pytest.mark.parametrize("path", ["/health/live", "/health/ready"])
def test_health_access_filter_suppresses_probe_paths(path):
    assert HealthCheckAccessFilter().filter(_uvicorn_access_record(path)) is False


@pytest.mark.parametrize("path", ["/docs", "/chat"])
def test_health_access_filter_keeps_application_paths(path):
    assert HealthCheckAccessFilter().filter(_uvicorn_access_record(path)) is True


def test_health_access_filter_keeps_non_access_records():
    record = logging.LogRecord(
        "jarvis.main",
        logging.INFO,
        __file__,
        1,
        "Application started",
        (),
        None,
    )

    assert HealthCheckAccessFilter().filter(record) is True


def test_configure_logging_attaches_health_access_filter():
    root = logging.getLogger()
    previous_handlers = root.handlers[:]
    previous_level = root.level
    try:
        configure_logging()

        assert any(
            isinstance(log_filter, HealthCheckAccessFilter)
            for log_filter in root.handlers[0].filters
        )
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
