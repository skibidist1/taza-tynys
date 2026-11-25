// Runs app logic (no DOM) on data/snapshot.json under JavaScriptCore.
import { normalize } from '../js/data.js';
import { PROFILES, actions, findWindows, schoolDays, schoolDay, groupLessons, levelOf } from '../js/advice.js';
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
for (const day of schoolDays(d.hours, d.nowIndex)) {
  const sd = schoolDay(d.hours, day);
  out.school.push({ day, verdicts: sd.lessons.map((l) => l.verdict), groups: groupLessons(sd.lessons) });
}
out.trapAll = d.hours.every((h) => h.trap && h.trap.p >= 0 && h.trap.p <= 1);
out.levels = [0, 15, 15.1, 25, 37.5, 37.6, 50, 75, 80].map(levelOf);
// stale replay: a "now" far after the snapshot must fall back to fetchedAt
const late = normalize(snap, model, nowMs + 10 * 864e5);
out.lateStale = late.stale;
out.lateNow = late.hours[late.nowIndex].time;
out.keys = { ru: Object.keys(DICT.ru), kk: Object.keys(DICT.kk) };
print(JSON.stringify(out));
