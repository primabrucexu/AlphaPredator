import json
from pathlib import Path

from app.db.sqlite import connect_sqlite, ensure_sqlite_schema
from app.modules.trade_review import service as service_module
from app.modules.trade_review.service import TradeReviewService
from app.schemas.trade_review import (
    CreateTradeReviewRequest,
    DecisionNoteItem,
    OperationItem,
    UpdateTradeReviewRequest,
)


def _patch_trade_review_connect(sqlite_path: Path):
    original_connect = service_module.connect_sqlite
    service_module.connect_sqlite = lambda: connect_sqlite(sqlite_path)
    return original_connect


def _make_create_request() -> CreateTradeReviewRequest:
    return CreateTradeReviewRequest(
        stock_code='000001',
        stock_name='PingAn',
        start_date='2026-05-01',
        end_date='2026-05-03',
        status='closed',
        total_buy_amount=10000,
        total_sell_amount=10800,
        realized_pnl=800,
        return_rate=0.08,
        entry_reason='breakout',
        entry_expectation='trend continue',
        reflection_did_well='discipline',
        reflection_did_poorly='late add',
        reflection_redo_plan='better stop',
        operations=[
            OperationItem(
                trade_time='2026-05-01T09:35:00',
                operation_type='buy',
                price=10.0,
                quantity=100,
                amount=1000.0,
                source='manual',
                note='entry',
            ),
            OperationItem(
                trade_time='2026-05-03T14:30:00',
                operation_type='sell',
                price=10.8,
                quantity=100,
                amount=1080.0,
                source='manual',
                note='exit',
            ),
        ],
        decision_notes=[
            DecisionNoteItem(
                decision_type='sell',
                decision_time='2026-05-03T14:00:00',
                reason='target hit',
            )
        ],
    )


def _make_update_request() -> UpdateTradeReviewRequest:
    return UpdateTradeReviewRequest(
        stock_code='000001',
        stock_name='PingAn Bank',
        start_date='2026-05-01',
        end_date='2026-05-04',
        status='closed',
        total_buy_amount=10000,
        total_sell_amount=11000,
        realized_pnl=1000,
        return_rate=0.10,
        entry_reason='breakout',
        entry_expectation='trend continue',
        reflection_did_well='discipline',
        reflection_did_poorly='none',
        reflection_redo_plan='repeat',
        operations=[
            OperationItem(
                trade_time='2026-05-04T10:00:00',
                operation_type='sell',
                price=11.0,
                quantity=100,
                amount=1100.0,
            )
        ],
        decision_notes=[],
    )


def test_trade_review_service_crud_and_detail_loading(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'trade.sqlite3'
    ensure_sqlite_schema(sqlite_path)
    original_connect = _patch_trade_review_connect(sqlite_path)
    try:
        service = TradeReviewService()
        created = service.create_review(_make_create_request())
        assert created is not None
        assert created.stock_code == '000001'
        assert len(created.operations) == 2
        assert [op.sort_index for op in created.operations] == [0, 1]
        assert len(created.decision_notes) == 1

        conn = connect_sqlite(sqlite_path)
        try:
            conn.execute(
                '''
                INSERT INTO trade_review_ai_result
                    (id, result_type, review_id, month_key, model_name, input_payload_json, output_payload_json, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                [
                    'ai-1',
                    'single_review',
                    created.id,
                    None,
                    'gpt-test',
                    '{}',
                    json.dumps({'summary': 'good trade'}),
                    'done',
                    '',
                    '2026-05-04T00:00:00+00:00',
                ],
            )
            conn.commit()
        finally:
            conn.close()

        detail = service.get_review(created.id)
        assert detail is not None
        assert detail.ai_result == {'summary': 'good trade'}
        assert [op.operation_type for op in detail.operations] == ['buy', 'sell']

        listing = service.list_reviews(month='2026-05', stock_code='000001', status='closed', limit=10, offset=0)
        assert listing.total == 1
        assert len(listing.items) == 1
        assert listing.items[0].id == created.id

        updated = service.update_review(
            created.id,
            _make_update_request(),
        )
        assert updated is not None
        assert updated.stock_name == 'PingAn Bank'
        assert len(updated.operations) == 1
        assert updated.operations[0].operation_type == 'sell'
        assert updated.decision_notes == []

        assert service.update_review('missing-id', _make_update_request()) is None

        assert service.delete_review(created.id) is True
        assert service.get_review(created.id) is None
        assert service.delete_review(created.id) is False
    finally:
        service_module.connect_sqlite = original_connect


def test_trade_review_service_monthly_stats_and_ai_parse_fallback(tmp_path: Path) -> None:
    sqlite_path = tmp_path / 'trade.sqlite3'
    ensure_sqlite_schema(sqlite_path)
    original_connect = _patch_trade_review_connect(sqlite_path)
    try:
        service = TradeReviewService()
        first = service.create_review(
            CreateTradeReviewRequest(
                stock_code='000001',
                stock_name='PingAn',
                start_date='2026-05-01',
                end_date='2026-05-02',
                status='closed',
                total_buy_amount=1000,
                total_sell_amount=1100,
                realized_pnl=100,
                return_rate=0.1,
                operations=[],
                decision_notes=[],
            )
        )
        second = service.create_review(
            CreateTradeReviewRequest(
                stock_code='000002',
                stock_name='Vanke',
                start_date='2026-05-10',
                end_date='2026-05-11',
                status='closed',
                total_buy_amount=2000,
                total_sell_amount=1800,
                realized_pnl=-200,
                return_rate=-0.1,
                operations=[],
                decision_notes=[],
            )
        )
        assert first is not None and second is not None

        conn = connect_sqlite(sqlite_path)
        try:
            conn.execute(
                '''
                INSERT INTO trade_review_ai_result
                    (id, result_type, review_id, month_key, model_name, input_payload_json, output_payload_json, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                ['ai-invalid', 'single_review', first.id, None, 'gpt-test', '{}', '{invalid', 'done', '', '2026-05-12T00:00:00+00:00'],
            )
            conn.commit()
        finally:
            conn.close()

        detail = service.get_review(first.id)
        assert detail is not None
        assert detail.ai_result is None

        stats = service.get_monthly_stats('2026-05')
        assert stats.month_key == '2026-05'
        assert stats.trade_count == 2
        assert stats.win_count == 1
        assert stats.loss_count == 1
        assert stats.realized_pnl == -100
        assert stats.average_return_rate == 0.0
        assert stats.max_gain == 100
        assert stats.max_loss == -200
        assert [row['stock_code'] for row in stats.reviews] == ['000002', '000001']
    finally:
        service_module.connect_sqlite = original_connect
