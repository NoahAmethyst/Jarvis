import copy
import logging
import os
import unicodedata


LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
HEALTH_CHECK_PATHS = frozenset({"/health/live", "/health/ready"})
RESET = "\x1b[0m"
LEVEL_LABELS = {
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
}
LEVEL_COLORS = {
    logging.INFO: "\x1b[32m",
    logging.WARNING: "\x1b[33m",
    logging.ERROR: "\x1b[31m",
}
MAX_LOG_TAG_PART_LENGTH = 160


def _safe_tag_part(value: object) -> str:
    sanitized = "".join(
        " "
        if unicodedata.category(character).startswith("C")
        or unicodedata.category(character) in {"Zl", "Zp"}
        else character
        for character in str(value)
    )
    return (
        sanitized.replace("【", "(").replace("】", ")")[
            :MAX_LOG_TAG_PART_LENGTH
        ]
    )


def format_log_tags(*fields: tuple[str, object]) -> str:
    return "".join(
        f"【{_safe_tag_part(name)}:{_safe_tag_part(value)}】"
        for name, value in fields
    )


class ColorLevelFormatter(logging.Formatter):
    def __init__(self, *args, use_color: bool | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_color = "NO_COLOR" not in os.environ if use_color is None else use_color

    def format(self, record: logging.LogRecord) -> str:
        formatted_record = copy.copy(record)
        label = LEVEL_LABELS.get(record.levelno, record.levelname)
        if self.use_color and record.levelno in LEVEL_COLORS:
            label = f"{LEVEL_COLORS[record.levelno]}{label}{RESET}"
        formatted_record.levelname = label
        return super().format(formatted_record)


class HealthCheckAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        if not isinstance(record.args, tuple) or len(record.args) < 3:
            return True
        return record.args[2] not in HEALTH_CHECK_PATHS


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ColorLevelFormatter(LOG_FORMAT))
    handler.addFilter(HealthCheckAccessFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
