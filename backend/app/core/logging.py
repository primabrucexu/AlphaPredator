from __future__ import annotations

import gzip
import logging
import logging.config
import os
import shutil
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def _default_log_dir() -> Path:
    return Path(__file__).resolve().parents[3] / 'logs'


def _gzip_namer(default_name: str) -> str:
    return default_name if default_name.endswith('.gz') else f'{default_name}.gz'


def _gzip_rotator(source: str, destination: str) -> None:
    with open(source, mode='rb') as source_file:
        with gzip.open(destination, mode='wb') as destination_file:
            shutil.copyfileobj(source_file, destination_file)
    os.remove(source)


def _build_daily_gzip_file_handler(
    filename: str,
    when: str = 'midnight',
    interval: int = 1,
    backupCount: int = 7,
    encoding: str = 'utf-8',
) -> TimedRotatingFileHandler:
    handler = TimedRotatingFileHandler(
        filename=filename,
        when=when,
        interval=interval,
        backupCount=backupCount,
        encoding=encoding,
    )
    handler.namer = _gzip_namer
    handler.rotator = _gzip_rotator
    return handler


def configure_logging(level: int = logging.INFO, log_dir: str | Path | None = None) -> None:
    """Configure app and uvicorn loggers to write to console and daily compressed files."""
    resolved_log_dir = Path(log_dir) if log_dir is not None else _default_log_dir()
    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    backend_log_file = resolved_log_dir / 'backend.log'

    logging.config.dictConfig(
        {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'default': {
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S',
                },
                'access': {
                    # Uvicorn emits access data via args into %(message)s in current versions.
                    'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S',
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout',
                },
                'access_console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'access',
                    'stream': 'ext://sys.stdout',
                },
                'file': {
                    '()': 'app.core.logging._build_daily_gzip_file_handler',
                    'filename': str(backend_log_file),
                    'formatter': 'default',
                },
            },
            'loggers': {
                'app': {
                    'handlers': ['console', 'file'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn': {
                    'handlers': ['console', 'file'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn.error': {
                    'handlers': ['console', 'file'],
                    'level': level,
                    'propagate': False,
                },
                'uvicorn.access': {
                    'handlers': ['access_console', 'file'],
                    'level': level,
                    'propagate': False,
                },
            },
            'root': {
                'handlers': ['console', 'file'],
                'level': level,
            },
        }
    )
