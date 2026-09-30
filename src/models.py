"""Model definitions. Lives in src/ so training and serving import the same class."""
from sklearn.linear_model import LogisticRegression


class TLearner:
    """Two logistic regressions, one per arm. uplift = P(y|treated) - P(y|control)."""

    def __init__(self):
        self.m1 = LogisticRegression(max_iter=1000)
        self.m0 = LogisticRegression(max_iter=1000)

    def fit(self, X, y, treatment):
        t = treatment == 1
        self.m1.fit(X[t], y[t])
        self.m0.fit(X[~t], y[~t])
        return self

    def predict_uplift(self, X):
        return self.m1.predict_proba(X)[:, 1] - self.m0.predict_proba(X)[:, 1]
