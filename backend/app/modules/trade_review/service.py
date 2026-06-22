"""
交易复盘 CRUD Service
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlmodel import select

from app.db.session import get_sqlite_session_factory
from app.models.sqlite_models import (
    TradeReviewAiResult,
    TradeReviewDecisionNote,
    TradeReviewOperation,
    TradeReviewSession,
)
from app.schemas.trade_review import (
    CreateTradeReviewRequest,
    DecisionNoteItem,
    MonthlyStatsResponse,
    OperationItem,
    TradeReviewDetail,
    TradeReviewListResponse,
    TradeReviewSessionItem,
    UpdateTradeReviewRequest,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _row_to_session(row: TradeReviewSession) -> TradeReviewSessionItem:
    return TradeReviewSessionItem(**row.model_dump())


def _row_to_op(row: TradeReviewOperation) -> OperationItem:
    return OperationItem(**row.model_dump())


def _row_to_note(row: TradeReviewDecisionNote) -> DecisionNoteItem:
    return DecisionNoteItem(**row.model_dump())


class TradeReviewService:
    def _session_factory(self):
        return get_sqlite_session_factory()

    # ------------------------------------------------------------------
    # 列表 & 详情
    # ------------------------------------------------------------------

    def list_reviews(
        self,
        month: str | None = None,
        stock_code: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TradeReviewListResponse:
        session_factory = self._session_factory()
        with session_factory() as session:
            statement = select(TradeReviewSession)
            if month:
                statement = statement.where(TradeReviewSession.start_date.startswith(month))  # type: ignore[attr-defined]
            if stock_code:
                statement = statement.where(TradeReviewSession.stock_code == stock_code)
            if status:
                statement = statement.where(TradeReviewSession.status == status)

            all_rows = session.exec(statement).all()
            total = len(all_rows)
            rows = sorted(
                all_rows,
                key=lambda item: (item.start_date, item.created_at),
                reverse=True,
            )[offset: offset + limit]

            return TradeReviewListResponse(
                total=total,
                items=[_row_to_session(r) for r in rows],
            )

    def get_review(self, review_id: str) -> TradeReviewDetail | None:
        session_factory = self._session_factory()
        with session_factory() as session:
            row = session.get(TradeReviewSession, review_id)
            if not row:
                return None

            ops = session.exec(
                select(TradeReviewOperation)
                .where(TradeReviewOperation.review_id == review_id)
                .order_by(TradeReviewOperation.trade_time, TradeReviewOperation.sort_index)
            ).all()

            notes = session.exec(
                select(TradeReviewDecisionNote)
                .where(TradeReviewDecisionNote.review_id == review_id)
                .order_by(TradeReviewDecisionNote.decision_time)
            ).all()

            ai_row = session.exec(
                select(TradeReviewAiResult)
                .where(
                    TradeReviewAiResult.review_id == review_id,
                    TradeReviewAiResult.result_type == 'single_review',
                    TradeReviewAiResult.status == 'done',
                )
                .order_by(TradeReviewAiResult.created_at.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()

            ai_result = None
            if ai_row:
                try:
                    ai_result = json.loads(ai_row.output_payload_json)
                except Exception:
                    pass

            return TradeReviewDetail(
                **row.model_dump(),
                operations=[_row_to_op(r) for r in ops],
                decision_notes=[_row_to_note(r) for r in notes],
                ai_result=ai_result,
            )

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create_review(self, req: CreateTradeReviewRequest) -> TradeReviewDetail:
        review_id = _new_id()
        now = _now()
        session_factory = self._session_factory()
        with session_factory() as session:
            session.add(
                TradeReviewSession(
                    id=review_id,
                    stock_code=req.stock_code,
                    stock_name=req.stock_name,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    status=req.status,
                    total_buy_amount=req.total_buy_amount,
                    total_sell_amount=req.total_sell_amount,
                    realized_pnl=req.realized_pnl,
                    return_rate=req.return_rate,
                    entry_reason=req.entry_reason,
                    entry_expectation=req.entry_expectation,
                    reflection_did_well=req.reflection_did_well,
                    reflection_did_poorly=req.reflection_did_poorly,
                    reflection_redo_plan=req.reflection_redo_plan,
                    ai_status='pending',
                    created_at=now,
                    updated_at=now,
                )
            )
            self._insert_operations(session, review_id, req.operations, now)
            self._insert_decision_notes(session, review_id, req.decision_notes, now)
            session.commit()

        review = self.get_review(review_id)
        if review is None:
            raise RuntimeError('created trade review not found')
        return review

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    def update_review(
        self, review_id: str, req: UpdateTradeReviewRequest
    ) -> TradeReviewDetail | None:
        now = _now()
        session_factory = self._session_factory()
        with session_factory() as session:
            row = session.get(TradeReviewSession, review_id)
            if not row:
                return None

            row.stock_code = req.stock_code
            row.stock_name = req.stock_name
            row.start_date = req.start_date
            row.end_date = req.end_date
            row.status = req.status
            row.total_buy_amount = req.total_buy_amount
            row.total_sell_amount = req.total_sell_amount
            row.realized_pnl = req.realized_pnl
            row.return_rate = req.return_rate
            row.entry_reason = req.entry_reason
            row.entry_expectation = req.entry_expectation
            row.reflection_did_well = req.reflection_did_well
            row.reflection_did_poorly = req.reflection_did_poorly
            row.reflection_redo_plan = req.reflection_redo_plan
            row.updated_at = now
            session.add(row)

            for operation in session.exec(
                select(TradeReviewOperation).where(TradeReviewOperation.review_id == review_id)
            ).all():
                session.delete(operation)
            for note in session.exec(
                select(TradeReviewDecisionNote).where(TradeReviewDecisionNote.review_id == review_id)
            ).all():
                session.delete(note)

            self._insert_operations(session, review_id, req.operations, now)
            self._insert_decision_notes(session, review_id, req.decision_notes, now)
            session.commit()

        return self.get_review(review_id)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_review(self, review_id: str) -> bool:
        session_factory = self._session_factory()
        with session_factory() as session:
            row = session.get(TradeReviewSession, review_id)
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # 月度统计（实时聚合）
    # ------------------------------------------------------------------

    def get_monthly_stats(self, month_key: str) -> MonthlyStatsResponse:
        session_factory = self._session_factory()
        with session_factory() as session:
            rows = session.exec(
                select(TradeReviewSession)
                .where(TradeReviewSession.start_date.startswith(month_key))  # type: ignore[attr-defined]
                .order_by(TradeReviewSession.start_date.desc())  # type: ignore[attr-defined]
            ).all()

            items = [
                {
                    'id': row.id,
                    'stock_code': row.stock_code,
                    'stock_name': row.stock_name,
                    'start_date': row.start_date,
                    'end_date': row.end_date,
                    'realized_pnl': row.realized_pnl,
                    'return_rate': row.return_rate,
                }
                for row in rows
            ]

        total = len(items)
        win = sum(1 for r in items if (r['realized_pnl'] or 0) > 0)
        loss = total - win
        pnl_total = sum((r['realized_pnl'] or 0) for r in items)
        rates = [r['return_rate'] for r in items if r['return_rate'] is not None]
        avg_rate = sum(rates) / len(rates) if rates else None
        pnls = [r['realized_pnl'] for r in items if r['realized_pnl'] is not None]
        max_gain = max(pnls) if pnls else None
        max_loss = min(pnls) if pnls else None

        return MonthlyStatsResponse(
            month_key=month_key,
            trade_count=total,
            win_count=win,
            loss_count=loss,
            realized_pnl=pnl_total,
            average_return_rate=avg_rate,
            max_gain=max_gain,
            max_loss=max_loss,
            reviews=items,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _insert_operations(
        self,
        session,
        review_id: str,
        operations: list[OperationItem],
        now: str,
    ) -> None:
        for i, op in enumerate(operations):
            op_id = op.id or _new_id()
            session.add(
                TradeReviewOperation(
                    id=op_id,
                    review_id=review_id,
                    trade_time=op.trade_time,
                    operation_type=op.operation_type,
                    price=op.price,
                    quantity=op.quantity,
                    amount=op.amount,
                    source=op.source,
                    note=op.note,
                    sort_index=op.sort_index if op.sort_index is not None else i,
                    created_at=now,
                    updated_at=now,
                )
            )

    def _insert_decision_notes(
        self,
        session,
        review_id: str,
        notes: list[DecisionNoteItem],
        now: str,
    ) -> None:
        for note in notes:
            note_id = note.id or _new_id()
            session.add(
                TradeReviewDecisionNote(
                    id=note_id,
                    review_id=review_id,
                    related_operation_id=note.related_operation_id,
                    decision_type=note.decision_type,
                    decision_time=note.decision_time,
                    reason=note.reason,
                    created_at=now,
                    updated_at=now,
                )
            )


trade_review_service = TradeReviewService()
