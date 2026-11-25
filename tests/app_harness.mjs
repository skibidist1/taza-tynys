// App logic (no DOM) on real snapshots and the winter archive, under JavaScriptCore.
import { buildHours, nearestSensor, distanceKm } from '../js/data.js';
import { PROFILES, actions, findWindows, schoolDays, schoolDay, catOf, DEFAULT_BELLS, DEFAULT_PE, forecastView } from '../js/advice.js';
import { DICT } from '../js/i18n.js';

const args = typeof scriptArgs !== 'undefined' ? scriptArgs : arguments;
const [snapP, sensP, modelP, demoP] = args;
const snap = JSON.parse(read(snapP));
const sens = JSON.parse(read(sensP));
const model = JSON.parse(read(modelP));
const demo = JSON.parse(read(demoP));
const out = {};
const point = { lat: 43.25, lon: 76.905 };
const near = nearestSensor(sens.sensors, point);
out.near = near && { id: near.sensor.id, km: near.km, ok: near.sensor.ok };
out.nearAllOk = sens.sensors.filter((s) => !s.ok).every((s) => !near || s.id !== near.sensor.id);
const d = buildHours(snap, model, near ? near.sensor.pm25 : 20, Date.parse(snap.fetchedAt));
const view = forecastView(d.hours, d.nowIndex);
out.n = d.hours.length; out.nowIndex = d.nowIndex; out.stale = d.stale; out.viewLen = view.length;
out.fcOk = view.every((h) => Number.isFinite(h.fc) && h.fc >= 0);
out.profiles = {};
for (const p of Object.keys(PROFILES)) out.profiles[p] = { actions: actions(d.hours, d.nowIndex, p).map((a) => a.key), windows: findWindows(d.hours, d.nowIndex, p).length };
out.school = [];
for (const shift of [1, 2]) for (const day of schoolDays(d.hours, d.nowIndex, DEFAULT_BELLS[shift])) {
  const sd = schoolDay(d.hours, day, DEFAULT_BELLS[shift], DEFAULT_PE[shift]);
  out.school.push(sd.lessons.map((l) => ({ v: l.verdict, pm: l.pm ?? null })));
}
out.cats = [0, 9, 9.1, 35.4, 35.5, 55.4, 55.5, 125.4, 125.5, 225.4, 226].map(catOf);
const w = buildHours(demo, model, demo.sensors.sensors[0].pm25, Date.parse(demo.fetchedAt));
out.winterNow = w.hours[w.nowIndex].fc;
out.winterCams = w.hours[w.nowIndex].cams;
const wd = schoolDays(w.hours, w.nowIndex, DEFAULT_BELLS[1]);
out.winterSchool = schoolDay(w.hours, wd[0], DEFAULT_BELLS[1], [1, 2, 3, 4, 5, 6, 7]).lessons.map((l) => l.verdict);
out.dist = distanceKm({ lat: 43.25, lon: 76.9 }, { lat: 43.26, lon: 76.9 });
out.keys = { ru: Object.keys(DICT.ru), kk: Object.keys(DICT.kk) };
print(JSON.stringify(out));
