// Runs the browser modules under JavaScriptCore (jsc -m) for tests.
// Usage: jsc -m tests/js_harness.mjs -- <cases.json> <model.json>
import { buildFeatures, predict } from '../js/trap.js';

const [casesPath, modelPath] = (typeof scriptArgs !== "undefined" ? scriptArgs : arguments);
const cases = JSON.parse(read(casesPath));
const model = JSON.parse(read(modelPath));
const s = cases.series;
const out = { series: [], vectors: [] };
for (const c of cases.series_cases) {
  const x = buildFeatures(s.time, s.wind, s.temp, s.blh, c.i);
  out.series.push({ i: c.i, x, ...predict(model, x) });
}
for (const v of cases.vector_cases) out.vectors.push(predict(model, v.x));
print(JSON.stringify(out));
