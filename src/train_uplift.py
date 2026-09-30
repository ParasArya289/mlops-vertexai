import argparse

from src.common import load_split, qini_coefficient, save_artifacts
from src.make_data import FEATURES
from src.models import TLearner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/data.csv")
    ap.add_argument("--out", default="artifacts/uplift")
    a = ap.parse_args()

    train, test = load_split(a.data)
    model = TLearner().fit(train[FEATURES], train["converted"], train["treatment"])
    qini = qini_coefficient(test["converted"], test["treatment"], model.predict_uplift(test[FEATURES]))
    save_artifacts(a.out, model, {"model": "uplift", "qini": qini, "n_train": len(train)})


if __name__ == "__main__":
    main()
