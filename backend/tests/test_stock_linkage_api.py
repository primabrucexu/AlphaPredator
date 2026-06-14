from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.stock_linkage.models import StockLinkageBacktestJob


def _job(job_id='job-1', status='pending'):
    return StockLinkageBacktestJob(
        job_id=job_id,
        job_name=None,
        a_select_mode='manual_single',
        manual_a_full_code='000001.SZ',
        hot_top_n=None,
        start_date='2025-01-01',
        end_date='2025-06-01',
        min_sample_count=30,
        status=status,
        error_message=None,
        created_at='2025-06-01 10:00:00',
        updated_at='2025-06-01 10:00:00',
        finished_at=None,
    )


def test_create_stock_linkage_backtest_creates_and_starts_background_job(monkeypatch):
    from app.api.routes import stock_linkage

    started = []

    def fake_create(request):
        assert request.a_select_mode == 'manual_single'
        assert request.manual_a_full_code == '000001.SZ'
        assert request.min_sample_count == 30
        return _job()

    def fake_start(job_id):
        started.append(job_id)
        return True

    monkeypatch.setattr(stock_linkage, 'create_stock_linkage_backtest_job', fake_create)
    monkeypatch.setattr(stock_linkage, 'start_stock_linkage_backtest_job', fake_start)
    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.post(
        '/backtests',
        json={
            'a_select_mode': 'manual_single',
            'manual_a_full_code': '000001.SZ',
            'start_date': '2025-01-01',
            'end_date': '2025-06-01',
        },
    )

    assert response.status_code == 202
    assert response.json()['job_id'] == 'job-1'
    assert response.json()['status'] == 'pending'
    assert started == ['job-1']


def test_create_stock_linkage_backtest_returns_conflict_when_job_is_running(monkeypatch):
    from app.api.routes import stock_linkage

    monkeypatch.setattr(stock_linkage, 'create_stock_linkage_backtest_job', lambda request: _job())
    monkeypatch.setattr(stock_linkage, 'start_stock_linkage_backtest_job', lambda job_id: False)
    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.post(
        '/backtests',
        json={
            'a_select_mode': 'manual_single',
            'manual_a_full_code': '000001.SZ',
            'start_date': '2025-01-01',
            'end_date': '2025-06-01',
        },
    )

    assert response.status_code == 409
    assert '已有联动回测任务正在运行' in response.json()['detail']


def test_create_stock_linkage_backtest_rejects_ranges_over_two_years():
    from app.api.routes import stock_linkage

    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.post(
        '/backtests',
        json={
            'a_select_mode': 'manual_single',
            'manual_a_full_code': '000001.SZ',
            'start_date': '2025-01-01',
            'end_date': '2027-01-03',
        },
    )

    assert response.status_code == 422
    assert '最长不超过2年' in response.json()['detail']


def test_get_stock_linkage_backtest_returns_job(monkeypatch):
    from app.api.routes import stock_linkage

    monkeypatch.setattr(stock_linkage, 'get_stock_linkage_job', lambda job_id: _job(job_id, 'running'))
    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.get('/backtests/job-1')

    assert response.status_code == 200
    assert response.json()['job_id'] == 'job-1'
    assert response.json()['status'] == 'running'


def test_list_stock_linkage_backtests_returns_recent_jobs(monkeypatch):
    from app.api.routes import stock_linkage

    monkeypatch.setattr(stock_linkage, 'list_stock_linkage_jobs', lambda limit=20: [_job('job-2'), _job('job-1')])
    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.get('/backtests')

    assert response.status_code == 200
    assert [item['job_id'] for item in response.json()] == ['job-2', 'job-1']
