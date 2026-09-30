import json

import pytest

from src import drift
from src.make_data import FEATURES, make_data


def test_psi_same_vs_shifted():
    a, b = make_data(5000, seed=1), make_data(5000, seed=2)
    shifted = make_data(5000, seed=2, shift_features=True)
    assert drift.psi(a["avg_spend"], b["avg_spend"]) < 0.1
    assert drift.psi(a["avg_spend"], shifted["avg_spend"]) > 0.2


def test_check_flags_only_shifted_features():
    ref, shifted = make_data(5000, seed=1), make_data(5000, seed=2, shift_features=True)
    _, drifted = drift.check(ref, shifted[FEATURES])
    assert set(drifted) == {"age", "avg_spend", "visits_30d"}  # the ones make_data shifts
    _, drifted = drift.check(ref, make_data(5000, seed=2)[FEATURES])
    assert drifted == []


def test_too_few_samples_refuses():
    df = make_data(5000)
    with pytest.raises(ValueError, match="need"):
        drift.check(df, df[FEATURES].head(50))


def test_load_logged_features(tmp_path):
    p = tmp_path / "log.jsonl"
    rows = make_data(10)[FEATURES].to_dict("records")
    p.write_text("".join(json.dumps({"instances": [r]}) + "\n" for r in rows))
    assert len(drift.load_logged_features(p)) == 10


def test_psi_detects_shift_in_binary_feature():
    ref = make_data(10000)["is_member"].to_numpy()
    assert drift.psi(ref, ref[:2000]) < 0.1  # same distribution
    assert drift.psi(ref, [1.0] * 1000) > 0.2  # 40% members -> 100% members


def test_check_rejects_nan_in_logged_features():
    ref, logged = make_data(5000, seed=1), make_data(500, seed=2)[FEATURES].copy()
    logged.loc[0, "age"] = float("nan")
    with pytest.raises(ValueError, match="NaN"):
        drift.check(ref, logged)
