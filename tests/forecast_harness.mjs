// Runs js/forecast.js under JavaScriptCore on tests/forecast_cases.json.
import { features, predict } from '../js/forecast.js';

const args = typeof scriptArgs !== 'undefined' ? scriptArgs : arguments;
const cases = JSON.parse(read(args[0]));
const model = JSON.parse(read(args[1]));
const raw = [[80, 40, -2, -6, 0.8, 20], [15, 25, 1, -3, 1.5, 13], [150, 60, 4, -10, 0.3, 21], [5, 10, -8, 2, 3.5, 14]];
print(JSON.stringify(cases.map((c, i) => {
  const x = features(...raw[i]);
  return { h: c.h, x, ...predict(model, c.h, x) };
})));
