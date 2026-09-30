"""Decide whether a candidate model may be registered. Pure functions, no I/O."""

import math

# metric name and absolute floor per model. Floors catch garbage models even with no champion yet.
# Measured over 40 seeds on 10k rows: good uplift Qini min +0.0056 (mean +0.0155), shuffled-label
# max +0.0054. A floor of 0.005 passes all good runs and rejects 39 of 40 shuffled ones. The clf
# floor rejected 20 of 20 shuffled runs, and the pipeline needs both to pass.
RULES = {"clf": ("auc", 0.55), "uplift": ("qini", 0.005)}


def check(model, candidate, champion=None, min_improvement=0.0):
    """Return (passed, reason). Candidate must clear the floor and not lose to the champion."""
    metric, floor = RULES[model]
    value = candidate[metric]
    if not math.isfinite(value):
        return False, f"{model} {metric}={value} is not a finite number"
    if value <= floor:
        return False, f"{model} {metric}={value:.4f} is at or below the floor {floor}"
    if champion is not None and value < champion[metric] + min_improvement:
        return False, f"{model} {metric}={value:.4f} does not beat champion {champion[metric]:.4f}"
    return True, f"{model} {metric}={value:.4f} ok"
