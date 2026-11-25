"""Features of the 48-hour PM2.5 forecast. Python twin of js/forecast.js (tests/test_forecast.py).

For an origin hour t (now, with a real sensor value) and a target hour t+h:
  log_pm_now  ln(1 + PM2.5 measured now)
  log_cams    ln(1 + CAMS PM2.5 forecast for t+h)
  inversion   T(850 hPa) - T(2 m) at t+h, degC; > 0 means warmer air aloft = temperature inversion
  wind        wind speed 10 m at t+h, m/s
  hour_*      daily cycle of the target hour (two harmonics)
Boundary layer height is shown in the app but not used: on real data it added no accuracy
and its coefficient flipped sign (collinear with inversion and hour), see evals/forecast_report.md.
Target: ln(1 + PM2.5 measured at t+h). One ridge regression per horizon h = 1..48;
back-transform with Duan smearing (mean of exp(residuals) on train), otherwise log models
predict the median and miss smog peaks.
"""
import math

FEATURES = ["log_pm_now", "log_cams", "inversion", "wind", "hour_sin", "hour_cos", "hour_sin2", "hour_cos2"]
HORIZON = 48


def features(pm_now, cams, t850, temp, wind, hour):
    a = 2 * math.pi * hour / 24
    return [
        math.log1p(max(pm_now, 0.0)),
        math.log1p(max(cams, 0.0)),
        t850 - temp,
        wind,
        math.sin(a), math.cos(a), math.sin(2 * a), math.cos(2 * a),
    ]


def predict(model, h, x):
    """PM2.5 forecast (ug/m3) for horizon h and per-feature contributions in log space."""
    m = model["horizons"][h - 1]
    z = m["intercept"]
    contrib = []
    for xi, mu, sd, c in zip(x, model["mean"], model["std"], m["coef"]):
        v = c * (xi - mu) / sd
        contrib.append(v)
        z += v
    return max(math.exp(z) * m.get("smear", 1.0) - 1.0, 0.0), contrib
