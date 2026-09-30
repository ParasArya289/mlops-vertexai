import os

import pytest

from src import gate, pipeline, registry
from src.make_data import make_data


def test_gate_floor_and_champion():
    assert gate.check("clf", {"auc": 0.65})[0]
    assert not gate.check("clf", {"auc": 0.50})[0]  # below floor
    assert not gate.check("uplift", {"qini": -0.003})[0]
    assert not gate.check("clf", {"auc": 0.60}, champion={"auc": 0.65})[0]  # loses to champion
    assert gate.check("clf", {"auc": 0.65}, champion={"auc": 0.65})[0]  # equal passes by default
    assert not gate.check("clf", {"auc": 0.65}, champion={"auc": 0.65}, min_improvement=0.01)[0]


def test_registry_versions_and_aliases(tmp_path):
    src = tmp_path / "art"
    src.mkdir()
    (src / "metrics.json").write_text('{"auc": 0.7}')
    assert registry.register("clf", src, tmp_path / "r") == "v1"
    assert registry.register("clf", src, tmp_path / "r") == "v2"
    registry.set_alias("clf", "champion", "v1", tmp_path / "r")
    assert registry.get_metrics("clf", "champion", tmp_path / "r") == {"auc": 0.7}
    assert registry.get_metrics("clf", "candidate", tmp_path / "r") is None
    with pytest.raises(ValueError):
        registry.set_alias("clf", "champion", "v9", tmp_path / "r")


def test_data_check_rejects_nulls(tmp_path):
    df = make_data(2000)
    df.loc[0, "age"] = None
    df.to_csv(tmp_path / "d.csv", index=False)
    with pytest.raises(ValueError, match="nulls"):
        pipeline.data_check(tmp_path / "d.csv")


def test_shuffled_model_rejected_good_model_registered(tmp_path):
    good, bad, root = tmp_path / "good.csv", tmp_path / "bad.csv", tmp_path / "reg"
    make_data(10000).to_csv(good, index=False)
    make_data(10000, shuffle_labels=True).to_csv(bad, index=False)

    res = pipeline.run(str(good), root)
    assert all(r["passed"] for r in res.values())
    for m in ("clf", "uplift"):
        registry.set_alias(m, "champion", registry.get_aliases(m, root)["candidate"], root)

    res = pipeline.run(str(bad), root)
    assert not any(r["passed"] for r in res.values())
    assert registry.get_aliases("clf", root)["candidate"] == "v1"  # nothing new registered
    assert not (root / "clf" / "v2").exists()


def test_promote_and_rollback(tmp_path):
    root, art = tmp_path / "r", tmp_path / "art"
    art.mkdir()
    (art / "metrics.json").write_text("{}")
    for _ in range(3):
        registry.register("clf", art, root)
    with pytest.raises(ValueError, match="previous"):
        registry.rollback("clf", root)
    registry.set_alias("clf", "champion", "v1", root)
    registry.set_alias("clf", "candidate", "v2", root)
    registry.promote("clf", root=root)  # candidate v2 becomes champion
    assert registry.get_aliases("clf", root)["champion"] == "v2"
    registry.rollback("clf", root)
    assert registry.get_aliases("clf", root)["champion"] == "v1"


def test_deploy_copies_champion_and_writes_version(tmp_path):
    root, target, art = tmp_path / "r", tmp_path / "deployed", tmp_path / "art"
    art.mkdir()
    (art / "model.joblib").write_text("v1-bytes")
    registry.register("clf", art, root)
    (art / "model.joblib").write_text("v2-bytes")
    registry.register("clf", art, root)
    registry.set_alias("clf", "champion", "v1", root)

    assert registry.deploy("clf", root, target) == "v1"
    assert (target / "clf" / "model.joblib").read_text() == "v1-bytes"
    assert (target / "clf" / "VERSION").read_text() == "v1"

    registry.promote("clf", "v2", root)
    registry.deploy("clf", root, target)  # replaces the previous deployment
    assert (target / "clf" / "model.joblib").read_text() == "v2-bytes"
    assert not (target / "clf.tmp").exists()


def test_gate_rejects_nan_metrics():
    assert not gate.check("clf", {"auc": float("nan")})[0]
    assert not gate.check("uplift", {"qini": float("nan")}, {"qini": 0.01})[0]


def test_shuffled_model_rejected_with_no_champion(tmp_path):
    bad = tmp_path / "bad.csv"
    make_data(10000, seed=5, shuffle_labels=True).to_csv(bad, index=False)
    res = pipeline.run(str(bad), tmp_path / "reg")
    assert not any(r["passed"] for r in res.values())
    assert not (tmp_path / "reg").exists()


def test_register_failure_leaves_nothing_registered(tmp_path, monkeypatch):
    good, root = tmp_path / "good.csv", tmp_path / "reg"
    make_data(10000).to_csv(good, index=False)
    real = registry.register

    def flaky(model, art, root_):
        if model == "uplift":
            raise OSError("disk full")
        return real(model, art, root_)

    monkeypatch.setattr(registry, "register", flaky)
    with pytest.raises(OSError):
        pipeline.run(str(good), root)
    assert not (root / "clf" / "v1").exists()
    assert registry.get_aliases("clf", root) == {}


def test_data_check_rules(tmp_path):
    def check(df):
        df.to_csv(tmp_path / "d.csv", index=False)
        pipeline.data_check(tmp_path / "d.csv")

    check(make_data(2000))
    with pytest.raises(ValueError, match="missing columns"):
        check(make_data(2000).drop(columns=["age"]))
    with pytest.raises(ValueError, match="only 500 rows"):
        check(make_data(500))
    skewed = make_data(2000)
    skewed["treatment"] = (skewed.index % 10 == 0).astype(int)
    with pytest.raises(ValueError, match="balance"):
        check(skewed)
    nonbinary = make_data(2000)
    nonbinary["converted"] = nonbinary["converted"] * 2
    with pytest.raises(ValueError, match="0/1"):
        check(nonbinary)
    one_class = make_data(2000)
    one_class["converted"] = 0
    with pytest.raises(ValueError, match="one class"):
        check(one_class)


def test_registry_guards_and_atomic_files(tmp_path):
    root, art = tmp_path / "r", tmp_path / "art"
    art.mkdir()
    (art / "metrics.json").write_text("{}")
    registry.register("clf", art, root)
    (root / "clf" / "vtmp").mkdir()  # stray dir must not break numbering
    assert registry.register("clf", art, root) == "v2"
    with pytest.raises(ValueError, match="no candidate"):
        registry.promote("clf", root=root)
    with pytest.raises(ValueError, match="no champion"):
        registry.deploy("clf", root, tmp_path / "d")
    registry.set_alias("clf", "champion", "v1", root)
    assert not list((root / "clf").glob("*.tmp"))


def test_cli_exit_codes_for_errors(tmp_path):
    import subprocess
    import sys

    def code(*args):
        return subprocess.run([sys.executable, "-m", *args], capture_output=True, text=True, check=False).returncode

    assert code("src.pipeline", "--data", str(tmp_path / "nope.csv")) == 2
    assert code("src.drift", "--log", str(tmp_path / "nope.jsonl")) == 2
    assert code("src.loop", "--log", str(tmp_path / "nope.jsonl")) == 2
    assert code("src.registry", "--help") == 2
    empty = {"REGISTRY_DIR": str(tmp_path / "empty")}
    proc = subprocess.run([sys.executable, "-m", "src.registry", "promote", "clf"], env={**os.environ, **empty},
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 2 and "no candidate" in proc.stderr
