from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_list_stock_linkage_results_returns_service_rows(monkeypatch):
    from app.api.routes import stock_linkage

    monkeypatch.setattr(
        stock_linkage,
        'list_stock_linkage_results',
        lambda job_id, limit=50, offset=0: [
            {
                'job_id': job_id,
                'a_full_code': '000001.SZ',
                'b_full_code': '000002.SZ',
                'trigger_type': 'single_bar_return',
                'trigger_threshold': 0.04,
                'observation_type': 't_day_high',
                'target_threshold': 0.03,
                'sample_count': 40,
                'hit_count': 12,
                'condition_probability': 0.3,
                'baseline_probability': 0.1,
                'probability_lift': 0.2,
                'lift_multiple': 3.0,
                'trigger_coverage_rate': 0.2,
                'confidence_level': 'high',
                'score': 0.738,
            }
        ],
    )
    app = FastAPI()
    app.include_router(stock_linkage.router)
    client = TestClient(app)

    response = client.get('/backtests/job-1/results')

    assert response.status_code == 200
    assert response.json()[0]['b_full_code'] == '000002.SZ'
    assert response.json()[0]['probability_lift'] == 0.2
