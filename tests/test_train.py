import json
import subprocess
import sys

from src.make_data import make_data


def _run(module, data, out):
    subprocess.run([sys.executable, "-m", module, "--data", str(data), "--out", str(out)], check=True, capture_output=True)
    return json.loads((out / "metrics.json").read_text())


def test_training_runs_and_shuffle_is_worse(tmp_path):
    good, bad = tmp_path / "good.csv", tmp_path / "bad.csv"
    make_data(10000).to_csv(good, index=False)
    make_data(10000, shuffle_labels=True).to_csv(bad, index=False)

    g = _run("src.train_clf", good, tmp_path / "g_clf")
    b = _run("src.train_clf", bad, tmp_path / "b_clf")
    assert (tmp_path / "g_clf" / "model.joblib").exists()
    assert g["auc"] > 0.6 > b["auc"] - 0.05

    gu = _run("src.train_uplift", good, tmp_path / "g_up")
    bu = _run("src.train_uplift", bad, tmp_path / "b_up")
    assert gu["qini"] > bu["qini"]
