// 48-hour PM2.5 forecast from the current real sensor value. Pure functions, no DOM.
// Python twin: pipeline/forecast_features.py (tests/test_forecast.py runs both on the same inputs).

export const FEATURES = ['log_pm_now', 'log_cams', 'inversion', 'wind', 'hour_sin', 'hour_cos', 'hour_sin2', 'hour_cos2'];
export const HORIZON = 48;

export function features(pmNow, cams, t850, temp, wind, hour) {
  const a = (2 * Math.PI * hour) / 24;
  return [
    Math.log1p(Math.max(pmNow, 0)),
    Math.log1p(Math.max(cams, 0)),
    t850 - temp,
    wind,
    Math.sin(a), Math.cos(a), Math.sin(2 * a), Math.cos(2 * a),
  ];
}

// h = 1..48. Returns { pm, contrib } (contributions in log space, FEATURES order).
export function predict(model, h, x) {
  const m = model.horizons[h - 1];
  let z = m.intercept;
  const contrib = x.map((xi, k) => {
    const v = (m.coef[k] * (xi - model.mean[k])) / model.std[k];
    z += v;
    return v;
  });
  // Duan smearing: log-space regression predicts the median; smear turns it into the mean.
  // lo/hi: 80% interval from residual quantiles on the training period.
  return {
    pm: Math.max(Math.exp(z) * (m.smear ?? 1) - 1, 0),
    median: Math.max(Math.expm1(z), 0),
    lo: Math.max(Math.expm1(z + (m.q10 ?? 0)), 0),
    hi: Math.max(Math.expm1(z + (m.q90 ?? 0)), 0),
    contrib,
  };
}
