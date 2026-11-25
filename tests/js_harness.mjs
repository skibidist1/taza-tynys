// Runs the browser modules under JavaScriptCore (jsc -m) for tests.
// Usage: jsc -m tests/js_harness.mjs -- <cases.json> <model.json> [factors.json]
import { buildFeatures, predict } from '../js/trap.js';
import { computeHouse } from '../js/calc.js';

const [casesPath, modelPath, factorsPath] = (typeof scriptArgs !== "undefined" ? scriptArgs : arguments);
const cases = JSON.parse(read(casesPath));
const model = JSON.parse(read(modelPath));
const s = cases.series;
const out = { series: [], vectors: [], calc: null };
for (const c of cases.series_cases) {
  const x = buildFeatures(s.time, s.wind, s.temp, s.blh, c.i);
  out.series.push({ i: c.i, x, ...predict(model, x) });
}
for (const v of cases.vector_cases) out.vectors.push(predict(model, v.x));
if (factorsPath) {
  const f = JSON.parse(read(factorsPath));
  out.calc = computeHouse(f, { heater: 'coal_stove', amount: 4, insulate: false });
}
print(JSON.stringify(out));
