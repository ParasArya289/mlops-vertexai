import numpy as np

from src.make_data import make_data


def test_deterministic():
    assert make_data(1000, seed=1).equals(make_data(1000, seed=1))


def test_treatment_balanced_and_no_nulls():
    df = make_data(5000)
    assert not df.isna().any().any()
    assert 0.45 < df["treatment"].mean() < 0.55


def test_shift_features_moves_distribution():
    base, shifted = make_data(5000), make_data(5000, shift_features=True)
    assert shifted["avg_spend"].mean() > base["avg_spend"].mean() * 1.5


def test_shuffle_labels_kills_signal():
    base, shuf = make_data(20000), make_data(20000, shuffle_labels=True)
    corr = lambda d: abs(np.corrcoef(d["visits_30d"], d["converted"])[0, 1])
    assert corr(base) > 0.03 and corr(shuf) < corr(base)
    assert base["converted"].mean() == shuf["converted"].mean()
