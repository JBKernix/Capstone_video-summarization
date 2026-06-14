import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ColoredConsoleFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    SEPARATOR = "\x1b[90m"
    TIME = "\x1b[36m"
    LOGGER = "\x1b[35m"
    MESSAGE = "\x1b[97m"
    LEVEL_COLORS = {
        logging.DEBUG: "\x1b[34m",
        logging.INFO: "\x1b[32m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[1;31m",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level_color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        separator = f" {self.SEPARATOR}|{self.RESET} "
        output = separator.join(
            (
                f"{self.TIME}{timestamp}{self.RESET}",
                f"{level_color}{record.levelname}{self.RESET}",
                f"{self.LOGGER}{record.name}{self.RESET}",
                f"{self.MESSAGE}{record.getMessage()}{self.RESET}",
            )
        )
        if record.exc_info:
            output = f"{output}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            output = f"{output}\n{self.formatStack(record.stack_info)}"
        return output


def configure_logging(project_root: Path) -> logging.Logger:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_dir / "server.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(log_formatter)

    console_colors_enabled = sys.stderr.isatty() and not os.getenv("NO_COLOR")
    if console_colors_enabled:
        try:
            from colorama import just_fix_windows_console

            just_fix_windows_console()
        except ImportError:
            pass

    console_handler = logging.StreamHandler()
    if console_colors_enabled:
        console_handler.setFormatter(
            ColoredConsoleFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        )
    else:
        console_handler.setFormatter(log_formatter)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
        force=True,
    )
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    logger = logging.getLogger("scripts.server")
    logger.info("File logging enabled: %s", file_handler.baseFilename)
    return logger
