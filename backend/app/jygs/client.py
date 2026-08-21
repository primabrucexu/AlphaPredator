from __future__ import annotations

import hashlib
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models import JygsCredential, LimitUpRecord


BASE_URL = "https://app.jiuyangongshe.com/jystock-app"
TOKEN_SALT = "Uu0KfOB8iUP69d3c"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)


class JygsError(RuntimeError):
    pass


def build_headers(session_value: str) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    token = hashlib.md5(f"{TOKEN_SALT}:{timestamp}".encode()).hexdigest()
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "DNT": "1",
        "Pragma": "no-cache",
        "Referer": "https://www.jiuyangongshe.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": BROWSER_UA,
        "platform": "3",
        "timestamp": timestamp,
        "token": token,
        "Cookie": f"SESSION={session_value.removeprefix('SESSION=').strip()}",
    }


def _post(path: str, payload: dict[str, Any], session_value: str) -> dict[str, Any]:
    try:
        response = httpx.post(f"{BASE_URL}{path}", json=payload, headers=build_headers(session_value), timeout=20)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise JygsError(f"韭研公社请求失败：{exc}") from exc
    if str(data.get("errCode", "")) != "0":
        raise JygsError(str(data.get("msg") or f"韭研公社返回错误 {data.get('errCode')}"))
    return data


def save_credential(db: Session, session_value: str) -> JygsCredential:
    clean = session_value.removeprefix("SESSION=").strip()
    credential = db.get(JygsCredential, 1) or JygsCredential(id=1, session=clean)
    credential.session = clean
    credential.updated_at = datetime.now(timezone.utc)
    credential.is_valid = False
    credential.last_error = ""
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential


def check_credential(db: Session) -> JygsCredential:
    credential = db.get(JygsCredential, 1)
    if not credential:
        raise JygsError("尚未配置韭研公社 SESSION")
    try:
        _post("/api/v1/action/diagram-url", {"date": date.today().isoformat()}, credential.session)
        credential.is_valid, credential.last_error = True, ""
    except JygsError as exc:
        credential.is_valid, credential.last_error = False, str(exc)
    credential.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    return credential


def parse_records(trade_date: str, payload: dict[str, Any]) -> list[LimitUpRecord]:
    themes: dict[str, set[str]] = {}
    stocks: dict[str, dict[str, Any]] = {}
    for category in payload.get("data") or []:
        theme = str(category.get("name") or "").strip()
        for stock in category.get("list") or []:
            digits = "".join(ch for ch in str(stock.get("code") or "") if ch.isdigit())
            code = digits[-6:]
            if not code:
                continue
            if theme:
                themes.setdefault(code, set()).add(theme)
            stocks.setdefault(code, stock)
    records = []
    for code, stock in stocks.items():
        action = ((stock.get("article") or {}).get("action_info") or {})
        records.append(LimitUpRecord(
            trade_date=trade_date, stock_code=code, stock_name=str(stock.get("name") or ""),
            limit_up_time=str(action.get("time") or ""), streak_text=str(action.get("num") or ""),
            hot_theme="、".join(sorted(themes.get(code, set()))), reason=str(action.get("expound") or ""),
        ))
    return records


def sync_range(db: Session, start_date: str, end_date: str) -> dict[str, int]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start:
        raise ValueError("结束日期不能早于开始日期")
    credential = db.get(JygsCredential, 1)
    if not credential:
        raise JygsError("尚未配置韭研公社 SESSION")
    days = records_count = 0
    current = start
    while current <= end:
        trade_date = current.isoformat()
        payload = _post("/api/v1/action/field", {"date": trade_date, "pc": 1}, credential.session)
        records = parse_records(trade_date, payload)
        db.execute(delete(LimitUpRecord).where(LimitUpRecord.trade_date == trade_date))
        db.add_all(records)
        db.commit()
        records_count += len(records)
        days += 1
        current += timedelta(days=1)
    return {"days": days, "records": records_count}


def recent_records(db: Session, stock_code: str, limit: int = 10) -> list[LimitUpRecord]:
    return list(db.scalars(select(LimitUpRecord).where(
        LimitUpRecord.stock_code == stock_code[:6]
    ).order_by(LimitUpRecord.trade_date.desc()).limit(limit)).all())
