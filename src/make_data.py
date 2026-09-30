"""Generate a small synthetic uplift dataset. Deterministic for a given seed."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["age", "tenure_months", "avg_spend", "visits_30d", "is_member"]


def make_data(n=10_000, seed=42, shuffle_labels=False, shift_features=False):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "user_id": np.arange(n),
            "age": rng.normal(40, 12, n).clip(18, 80),
            "tenure_months": rng.exponential(24, n).clip(0, 120),
            "avg_spend": rng.gamma(2.0, 30.0, n),
            "visits_30d": rng.poisson(5, n).astype(float),
            "is_member": rng.binomial(1, 0.4, n).astype(float),
        }
    )
    if shift_features:
        # Simulated drift: same schema, different distribution.
        df["age"] = (df["age"] + 15).clip(18, 80)
        df["avg_spend"] = df["avg_spend"] * 2.0
        df["visits_30d"] = df["visits_30d"] + 4

    df["treatment"] = rng.binomial(1, 0.5, n)

    # Known ground truth: baseline conversion plus a treatment effect.
    base_logit = -2.0 + 0.01 * df["avg_spend"] + 0.1 * df["visits_30d"] + 0.5 * df["is_member"]
    effect_logit = 0.8 * df["is_member"] - 0.02 * (df["age"] - 40)
    p0 = 1 / (1 + np.exp(-base_logit))
    p1 = 1 / (1 + np.exp(-(base_logit + effect_logit)))
    df["true_uplift"] = p1 - p0

    p = np.where(df["treatment"] == 1, p1, p0)
    df["converted"] = rng.binomial(1, p)

    if shuffle_labels:
        # Destroys signal, used to test that the pipeline rejects a bad model.
        df["converted"] = rng.permutation(df["converted"].to_numpy())
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/data.csv")
    ap.add_argument("--shuffle-labels", action="store_true")
    ap.add_argument("--shift-features", action="store_true")
    a = ap.parse_args()

    df = make_data(a.rows, a.seed, a.shuffle_labels, a.shift_features)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"wrote {len(df)} rows to {out} (conv rate {df['converted'].mean():.3f})")


if __name__ == "__main__":
    main()
