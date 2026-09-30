import json

from src import loop, registry
from src.make_data import FEATURES, make_data


def _write_log(path, df):
    path.write_text("".join(json.dumps({"instances": [r]}) + "\n" for r in df[FEATURES].to_dict("records")))


def test_drift_triggers_retrain_and_no_drift_does_not(tmp_path):
    ref, root = tmp_path / "ref.csv", tmp_path / "reg"
    make_data(10000, seed=1).to_csv(ref, index=False)
    shifted = make_data(10000, seed=2, shift_features=True)
    shifted.to_csv(tmp_path / "shifted.csv", index=False)

    calm = tmp_path / "calm.jsonl"
    _write_log(calm, make_data(500, seed=3))
    res = loop.run(ref, calm, tmp_path / "shifted.csv", root)
    assert res == {"drifted": [], "retrained": False}
    assert not root.exists()

    drifting = tmp_path / "drifting.jsonl"
    _write_log(drifting, make_data(500, seed=3, shift_features=True))
    res = loop.run(ref, drifting, tmp_path / "shifted.csv", root)
    assert res["retrained"] and "avg_spend" in res["drifted"]
    assert registry.get_aliases("clf", root) == {"candidate": "v1"}  # registered, never auto-promoted
