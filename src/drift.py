"""Drift check: compare features seen in serving logs against the training data using PSI.

PSI rule of thumb: < 0.1 stable, 0.1-0.2 moderate, > 0.2 significant drift.
Exit codes: 0 no drift, 1 drift, 2 could not run (too few requests, bad data, missing file).
"""
import argparse
import json
import sys

import numpy as np
import pandas as pd

from src.make_data import FEATURES

THRESHOLD = 0.2
MIN_SAMPLES = 200


def psi(reference, current, bins=10, max_discrete=5):
    """Population Stability Index.

    Continuous features use bin edges from the reference quantiles. Features with few distinct
    values (binary flags) use one bin per value, plus an "unseen" bin, since quantile edges collapse
    to a single bin for them and would always report 0.
    """
    values = np.unique(reference)
    if len(values) <= max_discrete:
        ref = np.array([np.mean(reference == v) for v in values] + [0.0])
        cur = np.array([np.mean(current == v) for v in values] + [np.mean(~np.isin(current, values))])
    else:
        edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)))
        edges[0], edges[-1] = -np.inf, np.inf
        ref = np.histogram(reference, edges)[0] / len(reference)
        cur = np.histogram(current, edges)[0] / len(current)
    ref, cur = np.clip(ref, 1e-4, None), np.clip(cur, 1e-4, None)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def load_logged_features(log_path):
    rows = []
    with open(log_path) as f:
        for line in f:
            rows.extend(json.loads(line)["instances"])
    return pd.DataFrame(rows, columns=FEATURES)


def check(reference, logged, threshold=THRESHOLD, min_samples=MIN_SAMPLES):
    """Return {feature: psi} and the list of drifted features."""
    if logged[FEATURES].isna().any().any() or reference[FEATURES].isna().any().any():
        raise ValueError("NaN in feature data: fix the source before trusting a drift score")
    if len(logged) < min_samples:
        raise ValueError(f"only {len(logged)} logged requests, need {min_samples} for a stable PSI")
    scores = {f: psi(reference[f].to_numpy(), logged[f].to_numpy()) for f in FEATURES}
    return scores, [f for f, s in scores.items() if s > threshold]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", default="data/data.csv")
    ap.add_argument("--log", default="logs/clf.jsonl")
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    a = ap.parse_args()
    try:
        scores, drifted = check(pd.read_csv(a.reference), load_logged_features(a.log), a.threshold)
    except (ValueError, OSError, KeyError) as e:
        print(f"drift check could not run: {e!r}", file=sys.stderr)
        sys.exit(2)
    for f, s in scores.items():
        print(f"{f:15s} psi={s:.3f} {'DRIFT' if f in drifted else 'ok'}")
    print("ALERT: drift detected in " + ", ".join(drifted) if drifted else "no drift")
    sys.exit(1 if drifted else 0)


if __name__ == "__main__":
    main()
