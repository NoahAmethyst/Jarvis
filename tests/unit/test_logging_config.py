import logging

import pytest

from jarvis.logging_config import ColorLevelFormatter


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
