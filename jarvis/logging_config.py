import copy
import logging
import os


LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
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


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ColorLevelFormatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
