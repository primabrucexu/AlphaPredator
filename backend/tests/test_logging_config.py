from __future__ import annotations

import gzip
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.logging import _default_log_dir, configure_logging


def test_default_log_dir_is_project_logs_folder() -> None:
    project_root = Path(__file__).resolve().parents[2]

    assert _default_log_dir() == project_root / 'logs'


def test_configure_logging_writes_backend_log_with_daily_gzip_rotation(tmp_path: Path) -> None:
    configure_logging(log_dir=tmp_path)

    file_handlers = [
        handler
        for handler in logging.getLogger('app').handlers
        if isinstance(handler, TimedRotatingFileHandler)
    ]

    assert len(file_handlers) == 1
    handler = file_handlers[0]
    access_file_handlers = [
        access_handler
        for access_handler in logging.getLogger('uvicorn.access').handlers
        if isinstance(access_handler, TimedRotatingFileHandler)
    ]
    assert access_file_handlers == [handler]

    assert Path(handler.baseFilename) == tmp_path / 'backend.log'
    assert handler.when == 'MIDNIGHT'
    assert handler.interval == 24 * 60 * 60
    assert handler.backupCount == 7
    assert handler.encoding == 'utf-8'
    assert handler.namer('backend.log.2026-06-29') == 'backend.log.2026-06-29.gz'

    source = tmp_path / 'backend.log.2026-06-29'
    destination = tmp_path / 'backend.log.2026-06-29.gz'
    source.write_text('compressed log line\n', encoding='utf-8')

    handler.rotator(str(source), str(destination))

    assert not source.exists()
    with gzip.open(destination, mode='rt', encoding='utf-8') as compressed:
        assert compressed.read() == 'compressed log line\n'
