from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_scan_macd_alert_api_creates_background_task(monkeypatch):
    from app.api.routes import macd_alert

    created = {}
    started = []

    def fake_create(**kwargs):
        created.update(kwargs)
        return {
            'task_id': 'task-1',
            'task_type': 'MACD_ALERT_SCAN',
            'start_date': '20260110',
            'end_date': '20260110',
            'status': 'PENDING',
            'total_items': 0,
            'processed_items': 0,
            'current_label': '',
            'error_message': '',
            'task_start_date': '',
            'task_end_date': '',
        }

    def fake_start(task_id):
        started.append(task_id)
        return True

    monkeypatch.setattr(macd_alert, 'create_macd_alert_scan_task', fake_create)
    monkeypatch.setattr(macd_alert, 'start_task', fake_start)
    monkeypatch.setattr(macd_alert, 'get_task', lambda task_id: fake_create())
    app = FastAPI()
    app.include_router(macd_alert.router)
    client = TestClient(app)

    response = client.post(
        '/scan',
        json={
            'trade_date': '2026-01-10',
            'markets': ['主板'],
            'exclude_st': True,
            'green_shrink_days': 2,
        },
    )

    assert response.status_code == 202
    assert response.json()['task_id'] == 'task-1'
    assert response.json()['task_type'] == 'MACD_ALERT_SCAN'
    assert created['trade_date'] == '2026-01-10'
    assert created['markets'] == ['主板']
    assert started == ['task-1']


def test_track_macd_alert_api_calls_service(monkeypatch):
    from app.api.routes import macd_alert

    monkeypatch.setattr(
        macd_alert,
        'track_macd_alerts',
        lambda **kwargs: {
            'trade_date': kwargs['trade_date'],
            'source_trade_date': kwargs['source_trade_date'],
            'tracked_count': 1,
            'cross_confirmed_count': 1,
            'trend_kept_count': 0,
            'trend_weakened_count': 0,
            'data_missing_count': 0,
            'report_generatable': True,
            'report_generation_hint': 'hint',
            'results': [],
        },
    )
    app = FastAPI()
    app.include_router(macd_alert.router)
    client = TestClient(app)

    response = client.post('/track', json={'trade_date': '2026-01-11', 'source_trade_date': '2026-01-10'})

    assert response.status_code == 200
    assert response.json()['cross_confirmed_count'] == 1


def test_list_macd_alert_results_api_returns_rows(monkeypatch):
    from app.api.routes import macd_alert

    monkeypatch.setattr(
        macd_alert,
        'list_macd_alert_results',
        lambda **kwargs: [{'id': 'alert-1', 'trade_date': kwargs['trade_date'], 'stock_code': '000001'}],
    )
    app = FastAPI()
    app.include_router(macd_alert.router)
    client = TestClient(app)

    response = client.get('/results?trade_date=2026-01-10&limit=20&offset=0')

    assert response.status_code == 200
    assert response.json()[0]['id'] == 'alert-1'
