from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.api.router import api_router
from app.database.session import get_session
from app.screening.sr001_report import (
    SR001ReportError,
    build_sr001_screening_report,
    load_rule_summary,
)
from app.screening.sr001_report_pdf import render_sr001_screening_report_pdf
from app.tasks.models import (
    ModeScreeningStockResult,
    SchedulingPolicy,
    Task,
    TaskItem,
    TaskStatus,
)


def _task(db, *, status: str = TaskStatus.SUCCEEDED.value, revision: int = 3) -> Task:
    task = Task(
        task_type="mode_screening_analysis",
        scheduling_policy=SchedulingPolicy.COMPUTE.value,
        title="SR001 report test",
        status=status,
        total_items=20,
        input_json=json.dumps({
            "rule_id": "SR001",
            "rule_revision": revision,
            "parameters": {"macd_fast": 8},
            "as_of_date": "2026-08-28",
        }),
        result_json=json.dumps({
            "stock_count": 20,
            "matched_stocks": 4,
            "skipped_stocks": 1,
            "failed_stocks": 0,
        }),
    )
    db.add(task)
    db.flush()
    return task


def _result(
    db,
    task: Task,
    sequence: int,
    *,
    state: str,
    win_rate: str | None,
    average_return: str | None,
    maximum_return: str | None,
    insufficient_history: bool = False,
) -> ModeScreeningStockResult:
    code = f"{sequence:06d}"
    symbol = f"{code}.SZ"
    item = TaskItem(
        task_id=task.id,
        sequence=sequence,
        title=symbol,
        status="SUCCEEDED",
        total=2,
    )
    db.add(item)
    db.flush()
    row = ModeScreeningStockResult(
        task_id=task.id,
        task_item_id=item.id,
        symbol=symbol,
        code=code,
        name=f"股票{sequence}",
        as_of_date="2026-08-28",
        data_start_date="2024-01-02",
        data_end_date="2026-08-28",
        signal_date="2026-08-27",
        insufficient_history=insufficient_history,
        evidence_json=json.dumps([{
            "condition_id": "C1",
            "passed": True,
            "values": {"h_s_minus_1": "-0.2", "h_s": "-0.1"},
        }]),
        metrics_json="{}",
        backtest_status="open",
        current_state=state,
        completed_trades=5,
        winning_trades=3,
        losing_trades=1,
        flat_trades=1,
        win_rate=win_rate,
        average_return=average_return,
        maximum_return=maximum_return,
        minimum_return="-0.05",
        open_trade_json="null",
        pending_orders_json="[]",
    )
    db.add(row)
    db.flush()
    return row


def test_rule_summary_loads_revision_3_and_rejects_unsupported_revision():
    summary = load_rule_summary("SR001", 3)
    assert summary.rule_metadata.rule_revision == 3
    assert summary.summary_data.trade_simulation_summary.stop_loss
    with pytest.raises(SR001ReportError, match="revision 1 尚未支持"):
        load_rule_summary("SR001", 1)


def test_report_separates_states_deduplicates_rankings_and_filters_other_states(db):
    task = _task(db)
    _result(
        db, task, 1, state="pending_entry",
        win_rate="0.8", average_return="0.1", maximum_return="0.4",
    )
    _result(
        db, task, 2, state="pending_entry",
        win_rate="0.7", average_return="0.2", maximum_return="0.3",
    )
    _result(
        db, task, 3, state="pending_entry",
        win_rate="0.9", average_return="0.3", maximum_return="0.5",
        insufficient_history=True,
    )
    _result(
        db, task, 4, state="bought_today",
        win_rate="0.6", average_return="0.15", maximum_return="0.25",
    )
    _result(
        db, task, 5, state="holding",
        win_rate="0.95", average_return="0.5", maximum_return="0.8",
    )
    report = build_sr001_screening_report(db, task)

    summary = report.execution_summary
    assert summary.matched_stocks == 5
    assert summary.pending_entry_stocks == 3
    assert summary.bought_today_stocks == 1
    assert summary.filtered_other_states == 1
    pending = report.opportunities["pending_entry"]
    assert pending.leaderboards["win_rate"] == ["000001.SZ", "000002.SZ"]
    assert pending.leaderboards["average_return"] == ["000002.SZ", "000001.SZ"]
    assert len(pending.items) == 2
    first = next(item for item in pending.items if item.symbol == "000001.SZ")
    assert first.ranks == {"win_rate": 1, "average_return": 2, "maximum_return": 1}
    assert first.macd_signal_window["h_s"] == "-0.1"
    assert pending.insufficient_history.total == 1
    assert pending.insufficient_history.items[0].symbol == "000003.SZ"


def test_report_limits_tied_rankings_and_insufficient_history_to_ten(db):
    task = _task(db)
    for sequence in range(1, 13):
        _result(
            db, task, sequence, state="pending_entry",
            win_rate="0.5", average_return=str(sequence / 100),
            maximum_return=str(sequence / 50),
        )
    for sequence in range(20, 32):
        _result(
            db, task, sequence, state="bought_today",
            win_rate=None, average_return=None, maximum_return=None,
            insufficient_history=True,
        )
    report = build_sr001_screening_report(db, task)

    pending = report.opportunities["pending_entry"]
    assert pending.leaderboards["win_rate"] == [
        f"{sequence:06d}.SZ" for sequence in range(1, 11)
    ]
    insufficient = report.opportunities["bought_today"].insufficient_history
    assert insufficient.total == 12
    assert insufficient.returned == 10
    assert insufficient.truncated is True


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "PARTIALLY_SUCCEEDED", "FAILED", "CANCELLED"])
def test_report_requires_succeeded_task(db, status):
    task = _task(db, status=status)
    with pytest.raises(SR001ReportError, match="只有成功完成"):
        build_sr001_screening_report(db, task)


def test_report_rejects_unsupported_rule_revision(db):
    task = _task(db, revision=1)
    with pytest.raises(SR001ReportError, match="revision 1 尚未支持"):
        build_sr001_screening_report(db, task)


def test_report_pdf_is_readable_and_contains_same_task(db):
    task = _task(db)
    _result(
        db, task, 1, state="pending_entry",
        win_rate="0.8", average_return="0.1", maximum_return="0.4",
    )
    report = build_sr001_screening_report(db, task)
    pdf = render_sr001_screening_report_pdf(report)

    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "SR001 规则执行报告" in text
    assert task.uuid in text
    assert "T点待买入" in text
    assert "规则口径摘要" in text


def _client(db) -> TestClient:
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_session] = lambda: db
    return TestClient(app)


def test_sr001_report_download_returns_pdf_with_expected_filename(db):
    task = _task(db)
    _result(
        db, task, 1, state="pending_entry",
        win_rate="0.8", average_return="0.1", maximum_return="0.4",
    )

    response = _client(db).get(f"/api/tasks/{task.uuid}/sr001-report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="SR001-revision-3-2026-08-28-{task.uuid}.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


def test_sr001_report_download_returns_clear_errors(db):
    task = _task(db, status=TaskStatus.RUNNING.value)
    client = _client(db)

    missing = client.get("/api/tasks/missing/sr001-report.pdf")
    unavailable = client.get(f"/api/tasks/{task.uuid}/sr001-report.pdf")

    assert missing.status_code == 404
    assert missing.json()["detail"] == "任务不存在"
    assert unavailable.status_code == 400
    assert unavailable.json()["detail"] == "只有成功完成的任务才能生成报告"


def test_sr001_report_download_rejects_unsupported_revision(db):
    task = _task(db, revision=1)

    response = _client(db).get(f"/api/tasks/{task.uuid}/sr001-report.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "SR001 revision 1 尚未支持报告"


def test_sr001_report_download_rejects_other_task_type(db):
    task = _task(db)
    task.task_type = "individual_backtest"
    db.flush()

    response = _client(db).get(f"/api/tasks/{task.uuid}/sr001-report.pdf")

    assert response.status_code == 400
    assert response.json()["detail"] == "该任务不是模式选股分析任务"
