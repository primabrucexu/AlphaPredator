from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from sqlmodel import func, select

from app.db.session import get_sqlite_session_factory
from app.models.sqlite_models import StockList
from app.queries.market_queries import get_stock_list_active_board_count_rows


class StockListRepo:
    def __init__(self, sqlite_path: Path | None = None) -> None:
        self._sqlite_path = sqlite_path

    def _session_factory(self):
        return get_sqlite_session_factory(self._sqlite_path)

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return cast(dict[str, Any], dict(row))

    def replace_all(self, rows: list[tuple[str, str, str, int, str, str]]) -> None:
        """Upsert incoming rows into stock_list.

        Guard: if *rows* is empty, the existing data is preserved and the
        method returns without touching the table.  This prevents an
        accidental full wipe when the upstream provider returns nothing.

        Strategy: never delete existing rows during sync.
        """
        if not rows:
            logging.getLogger(__name__).warning(
                'replace_all called with empty rows – keeping existing stock_list data'
            )
            return
        session_factory = self._session_factory()
        with session_factory() as session:
            for full_code, code, name, is_st, cnspell, market in rows:
                session.merge(
                    StockList(
                        full_code=full_code,
                        code=code,
                        name=name,
                        is_st=bool(is_st),
                        cnspell=cnspell,
                        market=market,
                    )
                )
            session.commit()

    @staticmethod
    def _model_to_dict(row: StockList) -> dict[str, Any]:
        return {
            'full_code': row.full_code,
            'code': row.code,
            'name': row.name,
            'is_st': row.is_st,
            'cnspell': row.cnspell,
            'market': row.market,
        }

    @staticmethod
    def _models_to_dicts(rows: list[StockList]) -> list[dict[str, Any]]:
        return [StockListRepo._model_to_dict(row) for row in rows]

    def get_by_full_code_upper(self, full_code_upper: str) -> dict[str, Any] | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            row = session.exec(
                select(StockList).where(func.upper(StockList.full_code) == full_code_upper).limit(1)
            ).first()
            return self._model_to_dict(row) if row else None

    def list_by_code(self, code: str) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(
                select(StockList).where(StockList.code == code)
            ).all()
            return self._models_to_dicts(list(rows))

    def list_by_cnspell_exact(self, cnspell_upper: str) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(
                select(StockList).where(StockList.cnspell == cnspell_upper)
            ).all()
            return self._models_to_dicts(list(rows))

    def list_by_cnspell_prefix(self, cnspell_prefix_upper: str, limit: int = 20) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(
                select(StockList)
                .where(StockList.cnspell.like(cnspell_prefix_upper + '%'))  # type: ignore[attr-defined]
                .limit(limit)
            ).all()
            return self._models_to_dicts(list(rows))

    def list_for_search(self, query_upper: str, limit: int) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            if query_upper.isdigit():
                statement = (
                    select(StockList)
                    .where(StockList.code.like(query_upper + '%'))  # type: ignore[attr-defined]
                    .limit(limit)
                )
            else:
                statement = (
                    select(StockList)
                    .where(StockList.cnspell.like(query_upper + '%'))  # type: ignore[attr-defined]
                    .limit(limit)
                )
            rows = session.exec(statement).all()
            return self._models_to_dicts(list(rows))

    def list_code_name_pairs(self) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(select(StockList)).all()
            return [
                {'code': row.code, 'name': row.name}
                for row in rows
            ]

    def list_all_ordered(self) -> list[dict[str, Any]]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(
                select(StockList).order_by(StockList.full_code)
            ).all()
            return self._models_to_dicts(list(rows))

    def count_rows(self) -> int:
        session_factory = self._session_factory()
        with session_factory() as session:
            count = session.exec(select(func.count()).select_from(StockList)).one()
            return int(count)

    def has_rows(self) -> bool:
        return self.count_rows() > 0

    def get_board_counts(self) -> dict[str, int]:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = get_stock_list_active_board_count_rows(session)
            return {str(row['market']): int(row['cnt']) for row in rows}
