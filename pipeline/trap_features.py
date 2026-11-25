"""Feature construction for the "weather trap" model.

This file is the Python twin of js/trap.js (buildFeatures / predict).
Any change here must be mirrored there; tests/test_model.py checks both
on the same inputs.
"""
import math
from datetime import datetime

FEATURES = [
    "wind_12h",   # mean wind speed 10 m over the last 12 h incl. current, m/s
    "temp_24h",   # mean air temperature 2 m over the last 24 h, degC
    "blh_12h",    # mean of ln(BLH + 10 m) over the last 12 h
    "hour_sin", "hour_cos",     # daily cycle, 1st harmonic
    "hour_sin2", "hour_cos2",   # daily cycle, 2nd harmonic (morning + evening peaks)
    "weekend",    # 1 on Saturday/Sunday
]


def rolling_mean(values, i, k):
    """Mean of values[max(0, i-k+1) .. i], skipping None."""
    window = [v for v in values[max(0, i - k + 1): i + 1] if v is not None]
    return sum(window) / len(window) if window else None


def build_features(times, wind, temp, blh, i):
    """Feature vector (list, FEATURES order) for hour i of hourly series.

    times: ISO local strings "YYYY-MM-DDTHH:MM" (Asia/Almaty).
    """
    t = datetime.fromisoformat(times[i])
    h = t.hour
    log_blh = [None if b is None else math.log(b + 10.0) for b in blh]
    a = 2 * math.pi * h / 24
    return [
        rolling_mean(wind, i, 12),
        rolling_mean(temp, i, 24),
        rolling_mean(log_blh, i, 12),
        math.sin(a), math.cos(a),
        math.sin(2 * a), math.cos(2 * a),
        1.0 if t.weekday() >= 5 else 0.0,
    ]


def predict(model, x):
    """Probability of a trap hour and per-feature logit contributions."""
    contrib = []
    z = model["intercept"]
    for xi, m, s, c in zip(x, model["mean"], model["std"], model["coef"]):
        v = c * (xi - m) / s
        contrib.append(v)
        z += v
    return 1.0 / (1.0 + math.exp(-z)), contrib
