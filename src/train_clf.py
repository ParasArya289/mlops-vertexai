import argparse

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from src.common import load_split, save_artifacts
from src.make_data import FEATURES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/data.csv")
    ap.add_argument("--out", default="artifacts/clf")
    a = ap.parse_args()

    train, test = load_split(a.data)
    model = LogisticRegression(max_iter=1000).fit(train[FEATURES], train["converted"])
    auc = roc_auc_score(test["converted"], model.predict_proba(test[FEATURES])[:, 1])
    save_artifacts(a.out, model, {"model": "clf", "auc": auc, "n_train": len(train)})


if __name__ == "__main__":
    main()
