from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Stock(Base):
    __tablename__ = "stocks"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    pinyin: Mapped[str] = mapped_column(String(128), index=True, default="")
    pinyin_initials: Mapped[str] = mapped_column(String(32), index=True, default="")


class WatchlistGroup(Base):
    __tablename__ = "watchlist_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    items: Mapped[list[WatchlistItem]] = relationship(back_populates="group", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("group_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("watchlist_groups.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    group: Mapped[WatchlistGroup] = relationship(back_populates="items")


class StockTag(Base):
    __tablename__ = "stock_tags"
    __table_args__ = (UniqueConstraint("symbol", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(32))


class JygsCredential(Base):
    __tablename__ = "jygs_credentials"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    session: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)
    last_checked_at: Mapped[datetime | None]
    last_error: Mapped[str] = mapped_column(Text, default="")
    is_valid: Mapped[bool] = mapped_column(default=False)


class LimitUpRecord(Base):
    __tablename__ = "limit_up_records"
    __table_args__ = (UniqueConstraint("trade_date", "stock_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_date: Mapped[str] = mapped_column(String(10), index=True)
    limit_up_time: Mapped[str] = mapped_column(String(16), default="")
    stock_code: Mapped[str] = mapped_column(String(6), index=True)
    stock_name: Mapped[str] = mapped_column(String(64), default="")
    streak_text: Mapped[str] = mapped_column(String(32), default="")
    hot_theme: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="jygs")
