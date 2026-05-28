"""
交易复盘 CRUD Service
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.db.sqlite import connect_sqlite
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


def _row_to_session(row) -> TradeReviewSessionItem:
    data = dict(row)
    return TradeReviewSessionItem(**data)


def _row_to_op(row) -> OperationItem:
    return OperationItem(**dict(row))


def _row_to_note(row) -> DecisionNoteItem:
    return DecisionNoteItem(**dict(row))


class TradeReviewService:
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
        conn = connect_sqlite()
        try:
            conditions: list[str] = []
            params: list = []

            if month:
                conditions.append("substr(start_date, 1, 7) = ?")
                params.append(month)
            if stock_code:
                conditions.append("stock_code = ?")
                params.append(stock_code)
            if status:
                conditions.append("status = ?")
                params.append(status)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            total = conn.execute(
                f"SELECT COUNT(*) FROM trade_review_session {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"""
                SELECT * FROM trade_review_session
                {where}
                ORDER BY start_date DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

            return TradeReviewListResponse(
                total=total,
                items=[_row_to_session(r) for r in rows],
            )
        finally:
            conn.close()

    def get_review(self, review_id: str) -> TradeReviewDetail | None:
        conn = connect_sqlite()
        try:
            row = conn.execute(
                "SELECT * FROM trade_review_session WHERE id = ?", [review_id]
            ).fetchone()
            if not row:
                return None

            ops = conn.execute(
                """
                SELECT * FROM trade_review_operation
                WHERE review_id = ?
                ORDER BY trade_time, sort_index
                """,
                [review_id],
            ).fetchall()

            notes = conn.execute(
                """
                SELECT * FROM trade_review_decision_note
                WHERE review_id = ?
                ORDER BY decision_time
                """,
                [review_id],
            ).fetchall()

            ai_row = conn.execute(
                """
                SELECT output_payload_json FROM trade_review_ai_result
                WHERE review_id = ? AND result_type = 'single_review' AND status = 'done'
                ORDER BY created_at DESC LIMIT 1
                """,
                [review_id],
            ).fetchone()

            ai_result = None
            if ai_row:
                try:
                    ai_result = json.loads(ai_row[0])
                except Exception:
                    pass

            return TradeReviewDetail(
                **dict(row),
                operations=[_row_to_op(r) for r in ops],
                decision_notes=[_row_to_note(r) for r in notes],
                ai_result=ai_result,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 创建
    # ------------------------------------------------------------------

    def create_review(self, req: CreateTradeReviewRequest) -> TradeReviewDetail:
        conn = connect_sqlite()
        try:
            review_id = _new_id()
            now = _now()

            conn.execute(
                """
                INSERT INTO trade_review_session (
                    id, stock_code, stock_name, start_date, end_date, status,
                    total_buy_amount, total_sell_amount, realized_pnl, return_rate,
                    entry_reason, entry_expectation,
                    reflection_did_well, reflection_did_poorly, reflection_redo_plan,
                    ai_status, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)
                """,
                [
                    review_id, req.stock_code, req.stock_name,
                    req.start_date, req.end_date, req.status,
                    req.total_buy_amount, req.total_sell_amount,
                    req.realized_pnl, req.return_rate,
                    req.entry_reason, req.entry_expectation,
                    req.reflection_did_well, req.reflection_did_poorly,
                    req.reflection_redo_plan, now, now,
                ],
            )

            self._insert_operations(conn, review_id, req.operations, now)
            self._insert_decision_notes(conn, review_id, req.decision_notes, now)
            conn.commit()
        finally:
            conn.close()

        return self.get_review(review_id)

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------

    def update_review(
        self, review_id: str, req: UpdateTradeReviewRequest
    ) -> TradeReviewDetail | None:
        conn = connect_sqlite()
        try:
            exists = conn.execute(
                "SELECT id FROM trade_review_session WHERE id = ?", [review_id]
            ).fetchone()
            if not exists:
                return None

            now = _now()
            conn.execute(
                """
                UPDATE trade_review_session SET
                    stock_code = ?, stock_name = ?, start_date = ?, end_date = ?,
                    status = ?, total_buy_amount = ?, total_sell_amount = ?,
                    realized_pnl = ?, return_rate = ?,
                    entry_reason = ?, entry_expectation = ?,
                    reflection_did_well = ?, reflection_did_poorly = ?,
                    reflection_redo_plan = ?, updated_at = ?
                WHERE id = ?
                """,
                [
                    req.stock_code, req.stock_name, req.start_date, req.end_date,
                    req.status, req.total_buy_amount, req.total_sell_amount,
                    req.realized_pnl, req.return_rate,
                    req.entry_reason, req.entry_expectation,
                    req.reflection_did_well, req.reflection_did_poorly,
                    req.reflection_redo_plan, now, review_id,
                ],
            )

            # 全量替换操作明细和决策备注
            conn.execute(
                "DELETE FROM trade_review_operation WHERE review_id = ?", [review_id]
            )
            conn.execute(
                "DELETE FROM trade_review_decision_note WHERE review_id = ?", [review_id]
            )
            self._insert_operations(conn, review_id, req.operations, now)
            self._insert_decision_notes(conn, review_id, req.decision_notes, now)
            conn.commit()
        finally:
            conn.close()

        return self.get_review(review_id)

    # ------------------------------------------------------------------
    # 删除
    # ------------------------------------------------------------------

    def delete_review(self, review_id: str) -> bool:
        conn = connect_sqlite()
        try:
            result = conn.execute(
                "DELETE FROM trade_review_session WHERE id = ?", [review_id]
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 月度统计（实时聚合）
    # ------------------------------------------------------------------

    def get_monthly_stats(self, month_key: str) -> MonthlyStatsResponse:
        conn = connect_sqlite()
        try:
            rows = conn.execute(
                """
                SELECT id, stock_code, stock_name,
                       start_date, end_date, realized_pnl, return_rate
                FROM trade_review_session
                WHERE substr(start_date, 1, 7) = ?
                ORDER BY start_date DESC
                """,
                [month_key],
            ).fetchall()

            items = [dict(r) for r in rows]
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
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _insert_operations(
        self,
        conn,
        review_id: str,
        operations: list[OperationItem],
        now: str,
    ) -> None:
        for i, op in enumerate(operations):
            op_id = op.id or _new_id()
            conn.execute(
                """
                INSERT INTO trade_review_operation (
                    id, review_id, trade_time, operation_type,
                    price, quantity, amount, source, note, sort_index,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    op_id, review_id, op.trade_time, op.operation_type,
                    op.price, op.quantity, op.amount, op.source,
                    op.note, op.sort_index if op.sort_index is not None else i,
                    now, now,
                ],
            )

    def _insert_decision_notes(
        self,
        conn,
        review_id: str,
        notes: list[DecisionNoteItem],
        now: str,
    ) -> None:
        for note in notes:
            note_id = note.id or _new_id()
            conn.execute(
                """
                INSERT INTO trade_review_decision_note (
                    id, review_id, related_operation_id, decision_type,
                    decision_time, reason, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    note_id, review_id, note.related_operation_id,
                    note.decision_type, note.decision_time, note.reason,
                    now, now,
                ],
            )


trade_review_service = TradeReviewService()

