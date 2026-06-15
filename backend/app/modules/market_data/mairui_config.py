"""Mairui runtime configuration stored in a local JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from app.core.settings import settings


@dataclass(frozen=True)
class MairuiConfig:
    licence: str
    rate_limit_per_minute: int
    fetch_concurrency: int
    updated_at: str = ''


def _default_config() -> MairuiConfig:
    return MairuiConfig(
        licence='',
        rate_limit_per_minute=int(settings.market_data_rate_limit),
        fetch_concurrency=int(settings.mairui_fetch_concurrency),
    )


def _validate_config(config: MairuiConfig) -> MairuiConfig:
    if config.rate_limit_per_minute <= 0:
        raise ValueError('rate_limit_per_minute must be greater than 0')
    if config.fetch_concurrency <= 0:
        raise ValueError('fetch_concurrency must be greater than 0')
    return config


def load_mairui_config() -> MairuiConfig:
    path = settings.mairui_config_path
    if not path.exists():
        return _default_config()

    data = json.loads(path.read_text(encoding='utf-8'))
    config = MairuiConfig(
        licence=str(data.get('licence') or '').strip(),
        rate_limit_per_minute=int(data.get('rate_limit_per_minute') or settings.market_data_rate_limit),
        fetch_concurrency=int(data.get('fetch_concurrency') or settings.mairui_fetch_concurrency),
        updated_at=str(data.get('updated_at') or ''),
    )
    return _validate_config(config)


def save_mairui_config(
    *,
    licence: str,
    rate_limit_per_minute: int,
    fetch_concurrency: int,
) -> MairuiConfig:
    config = _validate_config(
        MairuiConfig(
            licence=licence.strip(),
            rate_limit_per_minute=int(rate_limit_per_minute),
            fetch_concurrency=int(fetch_concurrency),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    path = settings.mairui_config_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return config
