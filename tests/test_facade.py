import httpx
from fastapi.testclient import TestClient

from api import main

FEATURES = {"age": 30, "tenure_months": 12, "avg_spend": 80, "visits_30d": 7, "is_member": 1}


def _use(handler):
    main.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=1)
    return TestClient(main.app)


def _ok(request):
    value = 0.5 if request.url == httpx.URL(main.CLF_URL) else 0.1
    return httpx.Response(200, json={"predictions": [value]})


def test_combined_response():
    r = _use(_ok).post("/recommend", json=FEATURES).json()
    assert r == {"p_convert": 0.5, "uplift": 0.1, "recommendation": "treat", "degraded": False}


def test_uplift_down_falls_back():
    def handler(request):
        if request.url == httpx.URL(main.UPLIFT_URL):
            raise httpx.ReadTimeout("slow", request=request)
        return _ok(request)

    r = _use(handler).post("/recommend", json=FEATURES)
    assert r.status_code == 200
    assert r.json() == {"p_convert": 0.5, "uplift": None, "recommendation": "unknown", "degraded": True}


def test_classifier_down_is_503():
    def handler(request):
        if request.url == httpx.URL(main.CLF_URL):
            return httpx.Response(500)
        return _ok(request)

    assert _use(handler).post("/recommend", json=FEATURES).status_code == 503


def test_null_or_nan_uplift_degrades_instead_of_500():
    def handler(request):
        if request.url == httpx.URL(main.UPLIFT_URL):
            return httpx.Response(200, json={"predictions": [None]})
        return _ok(request)

    r = _use(handler).post("/recommend", json=FEATURES)
    assert r.status_code == 200 and r.json()["degraded"] is True


def test_empty_instances_rejected_by_serve_contract():
    from pydantic import ValidationError

    from src.serve import PredictRequest

    try:
        PredictRequest(instances=[])
        raise AssertionError("expected a validation error")
    except ValidationError:
        pass
