# modules/common/logger.py

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
PIPELINE_LOG_ARCHIVE_DIR = LOG_DIR / "pipeline"

# GPU 서버(app/server_logging.py)와 동일한 형식입니다.
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5

# LOG_FORMAT으로 기록된 한 줄에서 메시지 부분을 분리하기 위한 패턴입니다.
LOG_LINE_PATTERN = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (?P<level>\w+) \| (?P<name>[^|]+?) \| (?P<message>.*)$"
)

class LineStampFormatter(logging.Formatter):
    """traceback처럼 여러 줄인 로그도 모든 줄 앞에 "시각 | 레벨 | 이름 | "을 붙입니다."""

    def format(self, record: logging.LogRecord) -> str:
        lines = super().format(record).split("\n")
        if len(lines) == 1:
            return lines[0]
        prefix = f"{self.formatTime(record, self.datefmt)} | {record.levelname} | {record.name} | "
        return "\n".join([lines[0], *(prefix + line for line in lines[1:])])


_LOG_FORMATTER = LineStampFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)


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


def configure_logging(log_file_name: str, console: bool = True) -> Path:
    """이 프로세스의 로그를 ``logs/<log_file_name>`` 회전 파일과 콘솔(stderr)에 기록하도록 설정합니다.

    프로세스마다 서로 다른 파일을 사용합니다(앱: client.log, 파이프라인: pipeline.log).
    한 파일에 여러 프로세스가 쓰면 Windows에서 회전(rename)이 실패하기 때문입니다.
    이미 설정된 프로세스에서 다시 호출하면 아무것도 하지 않습니다.

    Args:
        log_file_name: ``logs/`` 아래에 만들 로그 파일 이름입니다.
        console: 콘솔(stderr)에도 같은 로그를 출력할지 여부입니다.

    Returns:
        로그 파일 경로입니다.
    """
    root = logging.getLogger()
    for handler in root.handlers:
        if getattr(handler, "_client_log_file", None):
            return Path(handler.baseFilename)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / log_file_name,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(_LOG_FORMATTER)
    file_handler._client_log_file = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_colors_enabled = sys.stderr.isatty() and not os.getenv("NO_COLOR")
        if console_colors_enabled:
            try:
                from colorama import just_fix_windows_console

                just_fix_windows_console()
            except ImportError:
                pass
            console_handler.setFormatter(ColoredConsoleFormatter(datefmt=LOG_DATE_FORMAT))
        else:
            console_handler.setFormatter(_LOG_FORMATTER)
        root.addHandler(console_handler)

    root.setLevel(os.environ.get("CLIENT_LOG_LEVEL", "INFO").upper())
    # warnings.warn() 출력도 같은 형식(WARNING | py.warnings)으로 기록합니다.
    logging.captureWarnings(True)
    return Path(file_handler.baseFilename)


def get_logger(name: str) -> logging.Logger:
    """``configure_logging``으로 설정된 핸들러에 기록하는 로거를 반환합니다."""
    return logging.getLogger(name)


def format_log_line(message: str, name: str, level: int = logging.INFO, created: float | None = None) -> str:
    """로거를 거치지 않은 텍스트 한 줄을 LOG_FORMAT 형식으로 만듭니다."""
    record = logging.LogRecord(name, level, "", 0, message, None, None)
    if created is not None:
        record.created = created
    return _LOG_FORMATTER.format(record)


def split_log_line(line: str) -> tuple[str, str]:
    """LOG_FORMAT 형식 줄을 (시각, 메시지)로 나눕니다. 형식이 아니면 시각은 빈 문자열입니다."""
    match = LOG_LINE_PATTERN.match(line)
    if not match:
        return "", line
    return match.group("time"), match.group("message")


class TimestampedOutputRecorder:
    """자식 프로세스의 stdout/stderr를 읽어 모든 줄을 LOG_FORMAT 형식으로 파일에 기록합니다.

    - 이미 LOG_FORMAT으로 출력된 줄(자식 프로세스의 로거 출력)은 그대로 기록합니다.
    - print, tqdm, 네이티브 라이브러리 출력처럼 형식이 없는 줄에는 읽은 시각을 붙입니다.
    - tqdm은 ``\\r``로 같은 줄을 갱신하므로 ``\\r``도 줄 구분으로 취급합니다.
    """

    _LINE_SEPARATOR = re.compile(rb"\r\n|\r|\n")

    def __init__(self, log_path: str | Path, name: str = "pipeline"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.log_path.open("w", encoding="utf-8")
        self._lock = threading.Lock()
        self._name = name
        self._threads: list[threading.Thread] = []

    def attach(self, stream, stream_name: str) -> None:
        """``stream``(바이너리 파이프)을 백그라운드 스레드에서 끝(EOF)까지 읽습니다."""
        thread = threading.Thread(
            target=self._pump,
            args=(stream, f"{self._name}.{stream_name}"),
            name=f"log-pump-{stream_name}",
            daemon=True,
        )
        thread.start()
        self._threads.append(thread)

    def close(self, timeout: float = 5.0) -> None:
        """파이프를 다 읽을 때까지 기다린 뒤 파일을 닫습니다."""
        for thread in self._threads:
            thread.join(timeout)
        with self._lock:
            if not self._file.closed:
                self._file.close()

    def _pump(self, stream, logger_name: str) -> None:
        buffer = b""
        try:
            while True:
                chunk = stream.read1(4096) if hasattr(stream, "read1") else stream.read(4096)
                if not chunk:
                    break
                buffer += chunk
                *lines, buffer = self._LINE_SEPARATOR.split(buffer)
                for line in lines:
                    self._write(line, logger_name)
        except (OSError, ValueError):
            pass
        finally:
            if buffer:
                self._write(buffer, logger_name)
            stream.close()

    def _write(self, raw_line: bytes, logger_name: str) -> None:
        try:
            text = raw_line.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_line.decode("cp949", errors="replace")
        text = text.rstrip()
        if not text.strip():
            return

        line = text if LOG_LINE_PATTERN.match(text) else format_log_line(text, logger_name)
        with self._lock:
            if self._file.closed:
                return
            self._file.write(line + "\n")
            self._file.flush()


def archive_pipeline_log(source_path: str | Path, started_at: datetime, label: str) -> Path | None:
    """덮어쓰기되는 파이프라인 실행 로그를 실행 시각별 파일로 보관합니다.

    Args:
        source_path: 파이프라인 출력이 저장된 로그 파일입니다.
        started_at: 파이프라인 시작 시각입니다.
        label: 파일명 뒤에 붙일 결과 표시입니다. 예: ``success``, ``failed``, ``cancelled``

    Returns:
        보관된 로그 파일 경로입니다. 원본이 없으면 ``None``입니다.
    """
    source_path = Path(source_path)
    if not source_path.exists():
        return None

    PIPELINE_LOG_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = PIPELINE_LOG_ARCHIVE_DIR / f"{started_at:%Y%m%d_%H%M%S}_{label}.log"
    shutil.copy2(source_path, target_path)
    return target_path
