// "Weather trap" model: P(CAMS PM2.5 > 45 ug/m3) for an hour.
// Pure functions, no DOM. Python twin: pipeline/trap_features.py
// (tests/test_model.py runs this file with JavaScriptCore and compares).

export const FEATURES = [
  'wind_12h', 'temp_24h', 'blh_12h',
  'hour_sin', 'hour_cos', 'hour_sin2', 'hour_cos2', 'weekend',
];

export function rollingMean(values, i, k) {
  let sum = 0;
  let n = 0;
  for (let j = Math.max(0, i - k + 1); j <= i; j++) {
    const v = values[j];
    if (v !== null && v !== undefined && !Number.isNaN(v)) { sum += v; n++; }
  }
  return n ? sum / n : null;
}

// times: "YYYY-MM-DDTHH:MM" local Almaty strings.
export function buildFeatures(times, wind, temp, blh, i) {
  const t = times[i];
  const h = Number(t.slice(11, 13));
  const [y, m, d] = t.slice(0, 10).split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay(); // 0 = Sunday
  const logBlh = blh.map((b) => (b === null || b === undefined ? null : Math.log(b + 10)));
  const a = (2 * Math.PI * h) / 24;
  return [
    rollingMean(wind, i, 12),
    rollingMean(temp, i, 24),
    rollingMean(logBlh, i, 12),
    Math.sin(a), Math.cos(a),
    Math.sin(2 * a), Math.cos(2 * a),
    dow === 0 || dow === 6 ? 1 : 0,
  ];
}

export function predict(model, x) {
  let z = model.intercept;
  const contrib = x.map((xi, k) => {
    const v = (model.coef[k] * (xi - model.mean[k])) / model.std[k];
    z += v;
    return v;
  });
  return { p: 1 / (1 + Math.exp(-z)), contrib };
}

// Group contributions for the explanation UI.
export function explain(model, x) {
  const { p, contrib } = predict(model, x);
  const typicalBlh = Math.exp(model.mean[2]) - 10;
  return {
    p,
    trap: p >= model.threshold,
    groups: [
      { key: 'wind', value: x[0], typical: model.mean[0], logit: contrib[0] },
      { key: 'temp', value: x[1], typical: model.mean[1], logit: contrib[1] },
      { key: 'blh', value: Math.exp(x[2]) - 10, typical: typicalBlh, logit: contrib[2] },
      { key: 'hour', value: null, typical: null, logit: contrib[3] + contrib[4] + contrib[5] + contrib[6] },
      { key: 'weekend', value: x[7], typical: null, logit: contrib[7] },
    ],
  };
}
