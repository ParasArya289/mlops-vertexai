"""Local training pipeline: data check -> train both -> gate -> register as candidate.

Each function is one step and maps to a KFP component later.
Exit codes: 0 registered a candidate, 1 gate rejected the models, 2 could not run (bad data, crash).
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from src import gate, registry
from src.make_data import FEATURES

MODELS = {"clf": "src.train_clf", "uplift": "src.train_uplift"}


def data_check(path):
    df = pd.read_csv(path)
    needed = FEATURES + ["treatment", "converted", "user_id"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"data check failed: missing columns {missing}")
    if df[needed].isna().any().any():
        raise ValueError("data check failed: nulls present")
    if not 0.4 < df["treatment"].mean() < 0.6:
        raise ValueError(f"data check failed: treatment balance {df['treatment'].mean():.2f}")
    if len(df) < 1000:
        raise ValueError(f"data check failed: only {len(df)} rows")
    if not set(df["treatment"].unique()) <= {0, 1} or not set(df["converted"].unique()) <= {0, 1}:
        raise ValueError("data check failed: treatment and converted must be 0/1")
    test = df["user_id"] % 5 == 0  # the same split training uses
    if df.loc[test, "converted"].nunique() < 2 or df.loc[~test, "converted"].nunique() < 2:
        raise ValueError("data check failed: a split has only one class of converted")


def train(model, data, out):
    proc = subprocess.run([sys.executable, "-m", MODELS[model], "--data", data, "--out", str(out)],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"training {model} failed:\n{proc.stderr[-2000:]}")
    return json.loads((Path(out) / "metrics.json").read_text())


def run(data, root=registry.ROOT, min_improvement=0.0):
    data_check(data)
    with tempfile.TemporaryDirectory() as tmp:
        results = {}
        for model in MODELS:
            out = Path(tmp) / model
            metrics = train(model, data, out)
            champion = registry.get_metrics(model, "champion", root)
            passed, reason = gate.check(model, metrics, champion, min_improvement)
            results[model] = {"passed": passed, "reason": reason, "out": out}
        # Models are served together, so register both or neither.
        if all(r["passed"] for r in results.values()):
            created = []
            try:
                for model, r in results.items():
                    r["version"] = registry.register(model, r["out"], root)
                    created.append((model, r["version"]))
            except Exception:
                for model, version in created:  # undo, so it really is both or neither
                    shutil.rmtree(Path(root) / model / version, ignore_errors=True)
                raise
            for model, r in results.items():
                registry.set_alias(model, "candidate", r["version"], root)
    return {m: {k: v for k, v in r.items() if k != "out"} for m, r in results.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/data.csv")
    ap.add_argument("--registry", default=str(registry.ROOT))
    ap.add_argument("--min-improvement", type=float, default=0.0)
    a = ap.parse_args()
    try:
        res = run(a.data, Path(a.registry), a.min_improvement)
    except (ValueError, RuntimeError, OSError) as e:
        print(f"pipeline could not run: {e}", file=sys.stderr)
        sys.exit(2)
    for r in res.values():
        print(("PASS " if r["passed"] else "REJECT ") + r["reason"], r.get("version", ""))
    sys.exit(0 if all(r["passed"] for r in res.values()) else 1)


if __name__ == "__main__":
    main()
