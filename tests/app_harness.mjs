// Runs app logic (no DOM) on data/snapshot.json under JavaScriptCore.
import { normalize } from '../js/data.js';
import { PROFILES, actions, findWindows, schoolDays, schoolDay, levelOf, DEFAULT_BELLS, DEFAULT_PE } from '../js/advice.js';
import { DICT } from '../js/i18n.js';

const args = typeof scriptArgs !== 'undefined' ? scriptArgs : arguments;
const snap = JSON.parse(read(args[0]));
const model = JSON.parse(read(args[1]));
// "now" = the moment the snapshot was fetched
const nowMs = Date.parse(snap.fetchedAt);
const d = normalize(snap, model, nowMs);
const out = { n: d.hours.length, nowIndex: d.nowIndex, stale: d.stale, nowTime: d.hours[d.nowIndex].time, profiles: {}, school: [] };
for (const p of Object.keys(PROFILES)) {
  out.profiles[p] = { actions: actions(d.hours, d.nowIndex, p).map((a) => a.key), windows: findWindows(d.hours, d.nowIndex, p).map((w) => [w.day, w.ok, w.window && w.window.from]) };
}
for (const shift of [1, 2]) {
  for (const day of schoolDays(d.hours, d.nowIndex, DEFAULT_BELLS[shift])) {
    for (const group of ['junior', 'senior']) {
      const sd = schoolDay(d.hours, day, DEFAULT_BELLS[shift], DEFAULT_PE[shift], group);
      out.school.push({ shift, day, group, lessons: sd.lessons.map((l) => ({ n: l.n, pe: l.pe, verdict: l.verdict, reason: l.reason, pm: l.pm, trap: l.trap })) });
    }
  }
}
// winter archive: school decisions on a real smog day
const winter = JSON.parse(read(args[2]));
const w = normalize(winter, model, Date.parse(winter.fetchedAt));
out.winterSchool = ['junior', 'senior'].map((g) => schoolDay(w.hours, w.hours[w.nowIndex].time.slice(0, 10), DEFAULT_BELLS[1], [1, 2, 3, 4, 5, 6, 7], g).lessons.map((l) => l.verdict));
out.trapAll = d.hours.every((h) => h.trap && h.trap.p >= 0 && h.trap.p <= 1);
out.levels = [0, 15, 15.1, 25, 37.5, 37.6, 50, 75, 80].map(levelOf);
// stale replay: a "now" far after the snapshot must fall back to fetchedAt
const late = normalize(snap, model, nowMs + 10 * 864e5);
out.lateStale = late.stale;
out.lateNow = late.hours[late.nowIndex].time;
out.keys = { ru: Object.keys(DICT.ru), kk: Object.keys(DICT.kk) };
print(JSON.stringify(out));
