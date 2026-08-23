from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.models import JygsCredential
from app.database.session import get_session
from app.market_data.provider.base import normalize_symbol

from .client import JygsError, check_credential, recent_records, save_credential
from .playwright_login import login_and_capture_session
from .schemas import JygsLoginInput, JygsSessionInput


router = APIRouter()


@router.get("/stocks/{symbol}/limit-up-history")
def limit_up_history(symbol: str, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_session)):
    normalized = normalize_symbol(symbol)
    return [{"trade_date": r.trade_date, "limit_up_time": r.limit_up_time, "streak_text": r.streak_text,
             "hot_theme": r.hot_theme, "reason": r.reason} for r in recent_records(db, normalized, limit)]


@router.get("/jygs/status")
def jygs_status(db: Session = Depends(get_session)):
    row = db.get(JygsCredential, 1)
    return {"is_configured": bool(row), "is_valid": row.is_valid if row else False,
            "updated_at": row.updated_at if row else None, "last_checked_at": row.last_checked_at if row else None,
            "last_error": row.last_error if row else ""}


@router.put("/jygs/session")
def update_jygs_session(payload: JygsSessionInput, db: Session = Depends(get_session)):
    save_credential(db, payload.session)
    return {"message": "SESSION 已保存"}


@router.post("/jygs/login")
def login_jygs(payload: JygsLoginInput, db: Session = Depends(get_session)):
    try:
        result = login_and_capture_session(payload.timeout_seconds)
        session_value = str(result.get("session") or "").strip()
        if not session_value:
            raise JygsError("登录完成，但未捕获到 SESSION")
        save_credential(db, session_value)
        credential = check_credential(db)
        if not credential.is_valid:
            raise JygsError(f"登录后校验失败：{credential.last_error}")
        return {"is_valid": True}
    except JygsError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"韭研公社登录失败：{exc}") from exc


@router.post("/jygs/check")
def check_jygs(db: Session = Depends(get_session)):
    try:
        row = check_credential(db)
    except JygsError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"is_valid": row.is_valid, "last_error": row.last_error}
