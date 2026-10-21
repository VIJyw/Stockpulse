"""API contract tests against a small loaded database."""
from helpers import make_env
from api.app import create_app
from stockpulse.pipeline import run_day


def client():
    db, incoming = make_env()
    for _ in range(4):
        run_day(db, incoming_dir=incoming)
    url = db.url
    db.close()
    return create_app(url).test_client()


def test_health_and_core_endpoints():
    c = client()
    assert c.get("/health").get_json()["status"] == "ok"

    low = c.get("/low-stock?limit=5").get_json()
    assert low["as_of"] == "2026-06-04" and len(low["items"]) <= 5
    covers = [i["days_of_cover"] or 0 for i in low["items"] if not i["stockout"]]
    assert covers == sorted(covers)

    status = c.get("/pipeline-status").get_json()
    assert status["last_run"]["status"] == "success"
    assert status["latest_data_date"] == "2026-06-04"


def test_sku_detail_and_404():
    c = client()
    body = c.get("/sku/SKU00001").get_json()
    assert body["product"]["sku"] == "SKU00001" and len(body["sales_trend_14d"]) == 4
    assert c.get("/sku/NOPE").status_code == 404
