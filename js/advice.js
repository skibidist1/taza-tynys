// Categories, profiles, clean-air windows, actions and school mode. Pure functions, no DOM.
//
// Scale: US EPA AQI categories for PM2.5 (breakpoints revised in 2024, ug/m3):
//   Good <= 9.0, Moderate <= 35.4, Unhealthy for Sensitive Groups <= 55.4,
//   Unhealthy <= 125.4, Very Unhealthy <= 225.4, Hazardous above.
// Activity guidance follows the EPA "Air Quality Guide for Particle Pollution" and the
// "Air Quality Flag Program" school activity chart; texts are in i18n.js (cat_*_general/sensitive).
// The categories are defined for 24-hour averages; we apply them to hourly values as a guide.
// WHO 2021 24-hour guideline (15) and interim targets are shown as reference marks.

export const EPA_STEPS = [9.0, 35.4, 55.4, 125.4, 225.4];
export const CAT_KEYS = ['good', 'moderate', 'usg', 'unhealthy', 'very', 'hazardous'];
export const WHO = { aqg: 15, it4: 25, it3: 37.5, it2: 50, it1: 75 };

export function catOf(pm) {
  let i = 0;
  while (i < EPA_STEPS.length && pm > EPA_STEPS[i]) i++;
  return i;
}

// Outdoor activity limit per profile (top of the EPA category where no change is advised for it).
export const PROFILES = {
  general: { limit: 55.4 },   // EPA: general public reduces exertion from "Unhealthy"
  sensitive: { limit: 35.4 }, // EPA: sensitive groups (children, asthma, heart, pregnancy...) reduce from "USG"
};

const WAKE_FROM = 7;
const WAKE_TO = 21;
const hourOf = (h) => Number(h.time.slice(11, 13));
const dayOf = (h) => h.time.slice(0, 10);

function quantile(sorted, q) {
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

// Relative thirds of forecast values per day (waking hours within the forecast).
export function dayStats(hours) {
  const by = {};
  for (const h of hours) {
    if (h.fc == null || hourOf(h) < WAKE_FROM || hourOf(h) > WAKE_TO) continue;
    (by[dayOf(h)] ||= []).push(h.fc);
  }
  const out = {};
  for (const [d, v] of Object.entries(by)) {
    const s = [...v].sort((a, b) => a - b);
    out[d] = { q33: quantile(s, 1 / 3), q67: quantile(s, 2 / 3) };
  }
  return out;
}

export function relOf(h, stats) {
  const s = stats[dayOf(h)];
  if (!s || h.fc == null) return 'mid';
  if (h.fc <= s.q33) return 'best';
  if (h.fc >= s.q67) return 'worst';
  return 'mid';
}

function runs(list, pred, crossDay = false) {
  const out = [];
  let cur = null;
  for (const h of list) {
    if (pred(h)) {
      if (cur && h.idx === cur.end + 1 && (crossDay || dayOf(h) === cur.day)) { cur.end = h.idx; cur.hours.push(h); } else { cur = { start: h.idx, end: h.idx, day: dayOf(h), hours: [h] }; out.push(cur); }
    } else cur = null;
  }
  for (const r of out) {
    r.mean = r.hours.reduce((a, h) => a + h.fc, 0) / r.hours.length;
    r.max = Math.max(...r.hours.map((h) => h.fc));
    r.min = Math.min(...r.hours.map((h) => h.fc));
    r.from = r.hours[0].time;
    r.to = r.hours[r.hours.length - 1].time;
  }
  return out;
}

export function forecastView(hours, nowIndex, horizon = 48) {
  return hours.slice(nowIndex, nowIndex + horizon + 1).filter((h) => h.fc != null);
}

// Clean-air windows for a profile within the 48-hour forecast.
export function findWindows(hours, nowIndex, profileKey) {
  const prof = PROFILES[profileKey] || PROFILES.general;
  const stats = dayStats(hours);
  const waking = forecastView(hours, nowIndex).filter((h) => hourOf(h) >= WAKE_FROM && hourOf(h) <= WAKE_TO);
  const good = runs(waking, (h) => relOf(h, stats) !== 'worst' && h.fc <= prof.limit);
  const perDay = {};
  for (const w of good) if (!perDay[w.day] || w.mean < perDay[w.day].mean || (w.mean === perDay[w.day].mean && w.hours.length > perDay[w.day].hours.length)) perDay[w.day] = w;
  const days = [...new Set(waking.map(dayOf))].filter((d) => waking.filter((h) => dayOf(h) === d).length >= 4);
  return days.map((d) => {
    if (perDay[d]) return { day: d, ok: true, window: perDay[d] };
    const rel = runs(waking.filter((h) => dayOf(h) === d), (h) => relOf(h, stats) === 'best').sort((a, b) => a.mean - b.mean);
    return { day: d, ok: false, window: rel[0] || null };
  });
}

// Next whole episode above the limit within the 48-hour forecast (may span midnight).
export function nextBad(hours, nowIndex, limit = 35.4) {
  const view = forecastView(hours, nowIndex, 48);
  const bad = runs(view, (h) => h.fc > limit, true);
  return bad.find((r) => r.hours.length >= 2) || bad[0] || null;
}

// Best hour to air the room: waking hours of the next 24 h, never inside the bad episode.
export function bestVentHour(hours, nowIndex, badIdx = new Set()) {
  const view = forecastView(hours, nowIndex, 24).filter((h) => hourOf(h) >= WAKE_FROM && hourOf(h) <= 22 && !badIdx.has(h.idx));
  return view.length ? view.reduce((a, b) => (b.fc < a.fc ? b : a)) : null;
}

// One consistent plan: the ventilation advice never points inside the "windows closed" episode.
export function actions(hours, nowIndex, profileKey) {
  const prof = PROFILES[profileKey] || PROFILES.general;
  const now = hours[nowIndex];
  const out = [];
  const bad = nextBad(hours, nowIndex, prof.limit);
  const badIdx = new Set(bad ? bad.hours.map((h) => h.idx) : []);
  const vent = bestVentHour(hours, nowIndex, badIdx);
  const nowOk = !badIdx.has(now.idx) && now.fc <= prof.limit;
  if (nowOk && (!vent || now.fc <= vent.fc * 1.15)) out.push({ key: 'vent_now', pm: now.fc, bad });
  else if (bad) out.push({ key: 'vent_plan', bad, vent });
  else if (vent && vent.idx !== now.idx) out.push({ key: 'vent_later', time: vent.time, pm: vent.fc });
  else out.push({ key: 'vent_short' });
  // the cleanest window by mean forecast over the next 48 hours
  const w = findWindows(hours, nowIndex, profileKey).filter((x) => x.ok).sort((a, b) => a.window.mean - b.window.mean)[0];
  if (w) out.push({ key: 'activity_window', from: w.window.from, to: w.window.to, pm: w.window.max });
  else out.push({ key: 'activity_none', limit: prof.limit });
  out.push({ key: `cat_${CAT_KEYS[catOf(now.fc)]}_${profileKey}` });
  return out;
}

// ---- School mode -------------------------------------------------------
//
// PE is prolonged/heavy exertion. EPA Flag Program chart: orange (USG, > 35.4) -> sensitive students
// make activities shorter and less intense; red (Unhealthy, > 55.4) and above -> move activities indoors.
// The decision uses the worst forecast hour of the lesson. Lessons already over get 'r_past'.

export const DEFAULT_BELLS = {
  1: [['08:00', '08:45'], ['08:55', '09:40'], ['09:50', '10:35'], ['10:55', '11:40'], ['11:50', '12:35'], ['12:45', '13:30'], ['13:40', '14:25']],
  2: [['13:30', '14:15'], ['14:25', '15:10'], ['15:20', '16:05'], ['16:15', '17:00'], ['17:10', '17:55'], ['18:05', '18:50']],
};
export const DEFAULT_PE = { 1: [3], 2: [2] };

const toMin = (s) => Number(s.slice(0, 2)) * 60 + Number(s.slice(3, 5));
export const validTime = (s) => /^([01]\d|2[0-3]):[0-5]\d$/.test(s);

export function lessonVerdict(hours, day, from, to, lightFrom, nowTime = null) {
  if (nowTime && `${day}T${to}` <= nowTime) return { verdict: null, reason: 'r_past' };
  const hs = hours.filter((h) => dayOf(h) === day && h.fc != null && (hourOf(h) + 1) * 60 > toMin(from) && hourOf(h) * 60 < toMin(to));
  if (!hs.length) return { verdict: null, reason: 'r_nodata' };
  const pm = Math.max(...hs.map((h) => h.fc));
  const cat = catOf(pm);
  const temp = Math.min(...hs.map((h) => h.temp));
  const base = { pm, cat, temp };
  if (pm > 55.4) return { ...base, verdict: 'no', reason: 'r_unhealthy' };
  if (pm > lightFrom) return { ...base, verdict: 'light', reason: 'r_usg' };
  return { ...base, verdict: 'yes', reason: 'r_ok' };
}

export function schoolDay(hours, day, bells, pe, lightFrom = 35.4, nowTime = null) {
  return {
    day,
    lessons: bells.map(([from, to], i) => ({ n: i + 1, from, to, pe: pe.includes(i + 1), ...lessonVerdict(hours, day, from, to, lightFrom, nowTime) })),
  };
}

export function schoolDays(hours, nowIndex, bells) {
  const lastStart = bells.length ? Math.max(...bells.map((b) => toMin(b[0]))) : 0;
  const lastEnd = bells.length ? Math.max(...bells.map((b) => toMin(b[1]))) : 0;
  const out = [];
  for (const h of forecastView(hours, nowIndex)) {
    const d = dayOf(h);
    if (out.includes(d)) continue;
    const [y, m, dd] = d.split('-').map(Number);
    const dow = new Date(Date.UTC(y, m - 1, dd)).getUTCDay();
    if (dow === 0 || dow === 6) continue;
    if (hours.some((x) => dayOf(x) === d && x.fc != null && hourOf(x) === Math.floor(lastStart / 60))) out.push(d);
  }
  const now = hours[nowIndex];
  if (out[0] === dayOf(now) && hourOf(now) * 60 >= lastEnd) out.shift();
  return out;
}
