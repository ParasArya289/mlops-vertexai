"""Facade: calls the classifier and uplift models in parallel and merges the results."""
import asyncio
import logging
import math
import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

CLF_URL = os.environ.get("CLF_URL", "http://localhost:8081/predict")
UPLIFT_URL = os.environ.get("UPLIFT_URL", "http://localhost:8082/predict")
TIMEOUT_S = float(os.environ.get("TIMEOUT_S", "2.0"))
UPLIFT_THRESHOLD = float(os.environ.get("UPLIFT_THRESHOLD", "0.02"))

log = logging.getLogger("facade")
app = FastAPI()
client = httpx.AsyncClient(timeout=TIMEOUT_S)


class Features(BaseModel):
    age: float
    tenure_months: float
    avg_spend: float
    visits_30d: float
    is_member: float


async def _predict(url: str, features: Features) -> float:
    r = await client.post(url, json={"instances": [features.model_dump()]})
    r.raise_for_status()
    return r.json()["predictions"][0]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
async def recommend(features: Features):
    clf, uplift = await asyncio.gather(
        _predict(CLF_URL, features), _predict(UPLIFT_URL, features), return_exceptions=True
    )
    if isinstance(clf, BaseException):  # gather returns CancelledError as a value too
        log.error("classifier failed: %r", clf)
        raise HTTPException(503, "classifier unavailable")
    bad_uplift = isinstance(uplift, BaseException) or not isinstance(uplift, (int, float)) or math.isnan(uplift)
    if bad_uplift:
        log.warning("uplift failed, degrading to classification only: %r", uplift)
        return {"p_convert": clf, "uplift": None, "recommendation": "unknown", "degraded": True}
    rec = "treat" if uplift > UPLIFT_THRESHOLD else "do_not_treat"
    return {"p_convert": clf, "uplift": uplift, "recommendation": rec, "degraded": False}
