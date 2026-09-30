"""Shared data loading and metrics. Local CSV now; BigQuery/GCS swap in here later."""
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load_split(path="data/data.csv"):
    """Deterministic split by user_id so train/test never overlap across runs."""
    df = pd.read_csv(path)
    is_test = df["user_id"] % 5 == 0
    return df[~is_test], df[is_test]


def qini_coefficient(y, treatment, uplift_score):
    """Area between the Qini curve and the random-targeting line, normalised by n."""
    order = np.argsort(-np.asarray(uplift_score))
    y, t = np.asarray(y)[order], np.asarray(treatment)[order]
    n_t, n_c = np.cumsum(t), np.cumsum(1 - t)
    y_t, y_c = np.cumsum(y * t), np.cumsum(y * (1 - t))
    curve = y_t - y_c * np.divide(n_t, n_c, out=np.zeros(len(y)), where=n_c > 0)
    random_line = curve[-1] * np.arange(1, len(y) + 1) / len(y)
    return float(np.sum(curve - random_line) / len(y) ** 2)


def save_artifacts(out_dir, model, metrics):
    import joblib

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "model.joblib")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))
