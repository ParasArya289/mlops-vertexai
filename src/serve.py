"""Serving app for one model. Same image serves clf or uplift, chosen by MODEL_TYPE.

Request/response follow the Vertex custom-container contract so it deploys unchanged:
  POST /predict {"instances": [{feature: value, ...}]} -> {"predictions": [float, ...]}
"""
import json
import os
import time
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.make_data import FEATURES
from src.models import TLearner  # noqa: F401  (needed to unpickle TLearner)

MODEL_TYPE = os.environ.get("MODEL_TYPE", "clf")
MODEL_DIR = os.environ.get("MODEL_DIR", f"artifacts/{MODEL_TYPE}")
LOG_PATH = os.environ.get("LOG_PATH", "")  # JSONL now; BigQuery serving_logs later

app = FastAPI()
model = joblib.load(Path(MODEL_DIR) / "model.joblib")
_version_file = Path(MODEL_DIR) / "VERSION"  # written by registry.deploy
MODEL_VERSION = _version_file.read_text().strip() if _version_file.exists() else "unversioned"


class Instance(BaseModel):
    age: float
    tenure_months: float
    avg_spend: float
    visits_30d: float
    is_member: float


class PredictRequest(BaseModel):
    instances: list[Instance] = Field(min_length=1)


def _score(X):
    if MODEL_TYPE == "uplift":
        return model.predict_uplift(X)
    return model.predict_proba(X)[:, 1]


@app.get("/health")
def health():
    return {"status": "ok", "model_type": MODEL_TYPE, "model_version": MODEL_VERSION}


@app.post("/predict")
def predict(req: PredictRequest):
    start = time.perf_counter()
    X = pd.DataFrame([i.model_dump() for i in req.instances])[FEATURES]
    preds = [float(p) for p in _score(X)]
    if LOG_PATH:
        row = {
            "ts": time.time(),
            "model_type": MODEL_TYPE,
            "latency_ms": (time.perf_counter() - start) * 1000,
            "instances": [i.model_dump() for i in req.instances],
            "predictions": preds,
        }
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")
    return {"predictions": preds}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AIP_HTTP_PORT", "8080")))
