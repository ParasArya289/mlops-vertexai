"""Close the loop: check serving logs for drift and, if found, run the training pipeline.

Retraining only registers a `candidate`. Promoting it to champion stays a deliberate human step.
Exit codes: 0 no drift, 1 drift and a candidate was registered, 2 could not run (too little
traffic, bad data, crash), 3 drift but the pipeline rejected the retrain.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from src import drift, pipeline, registry


def run(reference, log, retrain_data, root=registry.ROOT, threshold=drift.THRESHOLD):
    _, drifted = drift.check(pd.read_csv(reference), drift.load_logged_features(log), threshold)
    if not drifted:
        return {"drifted": [], "retrained": False}
    results = pipeline.run(retrain_data, root)
    return {"drifted": drifted, "retrained": True, "results": results}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", default="data/data.csv")
    ap.add_argument("--log", default="logs/clf.jsonl")
    ap.add_argument("--retrain-data", default="data/data.csv")
    ap.add_argument("--registry", default=str(registry.ROOT))
    a = ap.parse_args()
    try:
        res = run(a.reference, a.log, a.retrain_data, Path(a.registry))
    except (ValueError, RuntimeError, OSError, KeyError) as e:
        print(f"loop could not run: {e}", file=sys.stderr)
        sys.exit(2)
    if not res["retrained"]:
        print("no drift, nothing to do")
        sys.exit(0)
    print("drift in " + ", ".join(res["drifted"]) + ", retrained")
    for r in res["results"].values():
        print(("PASS " if r["passed"] else "REJECT ") + r["reason"], r.get("version", ""))
    sys.exit(1 if all(r["passed"] for r in res["results"].values()) else 3)


if __name__ == "__main__":
    main()
