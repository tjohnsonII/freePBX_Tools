from __future__ import annotations

import io
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

LOG_DIR = (Path(__file__).resolve().parents[2] / "var" / "logs").resolve()
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 10


class RedactionFilter(logging.Filter):
    _KEY_PATTERNS = ["cookie", "authorization", "set-cookie", "token", "session", "x-api-key"]
    _KEY_VALUE_RE = re.compile(
        r"(?i)(\b(?:" + "|".join(re.escape(key) for key in _KEY_PATTERNS) + r")\b\s*[:=]\s*)([^\s,;]+)"
    )
    _BEARER_RE = re.compile(r"(?i)(\bbearer\s+)([^\s,;]+)")
    _JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text
        text = cls._KEY_VALUE_RE.sub(r"\1[REDACTED]", text)
        text = cls._BEARER_RE.sub(r"\1[REDACTED]", text)
        text = cls._JWT_RE.sub("[REDACTED_JWT]", text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        record.msg = self.redact(rendered)
        record.args = ()
        return True


class _LoggerWriter(io.TextIOBase):
    def __init__(self, logger: logging.Logger, level: int) -> None:
        self._logger = logger
        self._level = level
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self._logger.log(self._level, line)
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            self._logger.log(self._level, self._buffer.strip())
        self._buffer = ""


def _resolve_log_level() -> int:
    configured = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    return getattr(logging, configured, logging.INFO)


def _build_console_handler() -> logging.Handler:
    redaction = RedactionFilter()
    console = logging.StreamHandler(stream=sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    console.addFilter(redaction)
    return console


def _build_file_handler(log_name: str) -> logging.Handler:
    redaction = RedactionFilter()
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", log_name or "webscraper")
    file_handler = RotatingFileHandler(
        LOG_DIR / f"{safe_name}.log",
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    file_handler.addFilter(redaction)
    return file_handler


def redirect_stdout_to_logger(logger: logging.Logger, level: int = logging.INFO) -> TextIO:
    stream = _LoggerWriter(logger, level)
    sys.stdout = stream
    return stream


def redirect_stderr_to_logger(logger: logging.Logger, level: int = logging.ERROR) -> TextIO:
    stream = _LoggerWriter(logger, level)
    sys.stderr = stream
    return stream


def setup_logging(log_name: str = "webscraper") -> logging.Logger:
    level = _resolve_log_level()
    root = logging.getLogger()
    root.setLevel(level)

    marker = "_webscraper_logging_configured"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not getattr(root, marker, False):
        root.addHandler(_build_console_handler())
        setattr(root, marker, True)

    logger = logging.getLogger(log_name)
    logger.setLevel(level)

    file_marker = f"_webscraper_file_handler_{log_name}"
    if not getattr(root, file_marker, False):
        root.addHandler(_build_file_handler(log_name))
        setattr(root, file_marker, True)

    if os.getenv("SCRAPER_CAPTURE_PRINT") == "1" and not getattr(root, "_webscraper_capture_print", False):
        redirect_stdout_to_logger(logging.getLogger(f"{log_name}.stdout"), level=logging.INFO)
        redirect_stderr_to_logger(logging.getLogger(f"{log_name}.stderr"), level=logging.ERROR)
        setattr(root, "_webscraper_capture_print", True)

    logger.debug("logging initialized log_name=%s log_dir=%s level=%s", log_name, LOG_DIR, logging.getLevelName(level))
    return logger
