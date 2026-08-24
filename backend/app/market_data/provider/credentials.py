from __future__ import annotations

import json
from pathlib import Path

from app.core.config import THS_CREDENTIALS_PATH

from .base import MarketDataError


def load_ths_credentials(path: Path = THS_CREDENTIALS_PATH) -> dict[str, str] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise MarketDataError(f"同花顺账号配置读取失败：{exc}") from exc
    if not isinstance(payload, dict):
        raise MarketDataError("同花顺账号配置必须是 JSON 对象")
    username = payload.get("username")
    password = payload.get("password")
    if not isinstance(username, str) or not username.strip():
        raise MarketDataError("同花顺账号配置缺少非空 username")
    if not isinstance(password, str) or not password:
        raise MarketDataError("同花顺账号配置缺少非空 password")
    return {"username": username.strip(), "password": password}
