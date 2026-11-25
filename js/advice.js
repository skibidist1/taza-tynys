// Levels, profiles, clean-air windows, actions and school mode. Pure functions, no DOM.
//
// Absolute scale: WHO Global Air Quality Guidelines 2021, PM2.5 24-hour values
// (AQG 15, IT-4 25, IT-3 37.5, IT-2 50, IT-1 75 ug/m3). We apply them to hourly
// CAMS values only as reference marks: they are daily guidelines, and CAMS
// underestimates peaks in the Almaty basin. So every decision also uses the
// relative scale: the cleanest / dirtiest hours of the same day in the forecast.

export const WHO_STEPS = [15, 25, 37.5, 50, 75];
export const LEVEL_KEYS = ['aqg', 'it4', 'it3', 'it2', 'it1', 'over'];

export function levelOf(pm) {
  let i = 0;
  while (i < WHO_STEPS.length && pm > WHO_STEPS[i]) i++;
  return i; // 0..5
}

// limit: hourly CAMS PM2.5 above which we do not suggest outdoor activity for the profile.
// Conservative on purpose because CAMS underestimates peaks.
export const PROFILES = {
  general: { limit: 50, activity: 'walk' },
  child: { limit: 37.5, activity: 'walk_child' },
  sensitive: { limit: 25, activity: 'walk' },
  sport: { limit: 37.5, activity: 'run' },
  pregnancy: { limit: 25, activity: 'walk' },
};

const WAKE_FROM = 7;
const WAKE_TO = 21; // last start hour of a waking window

const hourOf = (h) => Number(h.time.slice(11, 13));
const dayOf = (h) => h.time.slice(0, 10);

function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

// Per-day relative thresholds over waking hours of the whole day (incl. past hours).
export function dayStats(hours) {
  const by = {};
  for (const h of hours) {
    const hr = hourOf(h);
    if (hr < WAKE_FROM || hr > WAKE_TO || h.pm25 == null) continue;
    (by[dayOf(h)] ||= []).push(h.pm25);
  }
  const out = {};
  for (const [d, v] of Object.entries(by)) {
    const s = [...v].sort((a, b) => a - b);
    out[d] = { q33: quantile(s, 1 / 3), q50: quantile(s, 0.5), q67: quantile(s, 2 / 3), min: s[0], max: s[s.length - 1] };
  }
  return out;
}

// Relative rank of an hour within its day: 'best' | 'mid' | 'worst'.
export function relOf(h, stats) {
  const s = stats[dayOf(h)];
  if (!s) return 'mid';
  if (h.pm25 <= s.q33) return 'best';
  if (h.pm25 >= s.q67) return 'worst';
  return 'mid';
}

function runs(list, pred) {
  const out = [];
  let cur = null;
  for (const h of list) {
    if (pred(h)) {
      if (cur && h.idx === cur.end + 1 && dayOf(h) === cur.day) {
        cur.end = h.idx;
        cur.hours.push(h);
      } else {
        cur = { start: h.idx, end: h.idx, day: dayOf(h), hours: [h] };
        out.push(cur);
      }
    } else cur = null;
  }
  for (const r of out) {
    r.mean = r.hours.reduce((a, h) => a + h.pm25, 0) / r.hours.length;
    r.max = Math.max(...r.hours.map((h) => h.pm25));
    r.from = r.hours[0].time;
    r.to = r.hours[r.hours.length - 1].time; // last hour start; window ends +1h
  }
  return out;
}

// Clean-air windows for a profile in the horizon [nowIndex, nowIndex + 72).
export function findWindows(hours, nowIndex, profileKey, horizon = 72) {
  const prof = PROFILES[profileKey] || PROFILES.general;
  const stats = dayStats(hours);
  const view = hours.slice(nowIndex, nowIndex + horizon);
  const waking = view.filter((h) => hourOf(h) >= WAKE_FROM && hourOf(h) <= WAKE_TO);
  const good = runs(waking, (h) => relOf(h, stats) === 'best' && h.pm25 <= prof.limit && !h.trap?.on);
  // best window per day, ranked by cleanliness; keep chronological order
  const perDay = {};
  for (const w of good) {
    if (!perDay[w.day] || w.mean < perDay[w.day].mean) perDay[w.day] = w;
  }
  // only days with enough waking hours left in the horizon
  const days = [...new Set(waking.map(dayOf))].filter((d) => waking.filter((h) => dayOf(h) === d).length >= 4);
  return days.map((d) => {
    if (perDay[d]) return { day: d, ok: true, window: perDay[d] };
    // No window under the profile limit: report the least bad waking run.
    const rel = runs(waking.filter((h) => dayOf(h) === d), (h) => relOf(h, stats) === 'best');
    rel.sort((a, b) => a.mean - b.mean);
    return { day: d, ok: false, window: rel[0] || null };
  });
}

// Next smog period (relative worst of the day or IT-2+), from now within 24 h.
export function nextSmog(hours, nowIndex) {
  const stats = dayStats(hours);
  const view = hours.slice(nowIndex, nowIndex + 24);
  const bad = runs(view, (h) => relOf(h, stats) === 'worst' || levelOf(h.pm25) >= 3 || h.trap?.on);
  const long = bad.filter((r) => r.hours.length >= 2);
  return long[0] || bad[0] || null;
}

// Best hour to air the flat within the next 12 waking hours.
export function bestVentHour(hours, nowIndex) {
  const view = hours.slice(nowIndex, nowIndex + 12).filter((h) => hourOf(h) >= WAKE_FROM && hourOf(h) <= 22);
  if (!view.length) return null;
  return view.reduce((a, b) => (b.pm25 < a.pm25 ? b : a));
}

// Three actions for "now". Returns keys + params; texts are in i18n.
export function actions(hours, nowIndex, profileKey) {
  const prof = PROFILES[profileKey] || PROFILES.general;
  const now = hours[nowIndex];
  const stats = dayStats(hours);
  const rel = relOf(now, stats);
  const out = [];

  // 1. Ventilation
  const vent = bestVentHour(hours, nowIndex);
  if (now.pm25 <= 37.5 && rel !== 'worst' && (!vent || now.pm25 <= vent.pm25 * 1.15)) {
    out.push({ key: 'vent_now', pm: now.pm25 });
  } else if (vent && vent.idx !== now.idx) {
    out.push({ key: 'vent_later', time: vent.time, pm: vent.pm25 });
  } else {
    out.push({ key: 'vent_short', pm: now.pm25 });
  }

  // 2. Activity window for the profile
  const wins = findWindows(hours, nowIndex, profileKey, 36);
  const w = wins.find((x) => x.ok);
  if (w) out.push({ key: 'activity_window', activity: prof.activity, from: w.window.from, to: w.window.to, pm: w.window.max });
  else out.push({ key: 'activity_none', activity: prof.activity, limit: prof.limit });

  // 3. Protection: next smog period + profile-specific advice
  const smog = nextSmog(hours, nowIndex);
  out.push({ key: `protect_${profileKey in PROFILES ? profileKey : 'general'}`, smog: smog ? { from: smog.from, to: smog.to, max: smog.max, trap: smog.hours.some((h) => h.trap?.on) } : null });
  return out;
}

// ---- School mode -------------------------------------------------------
//
// Outdoor PE decision per lesson. Thresholds are WHO 2021 PM2.5 24-hour interim
// targets applied to hourly CAMS values (IT-4 25, IT-3 37.5 ug/m3); juniors
// (grades 1-4) get the stricter rule because children are more vulnerable to
// air pollution (WHO, "Air pollution and child health: prescribing clean air", 2018).

export const DEFAULT_BELLS = {
  1: [['08:00', '08:45'], ['08:55', '09:40'], ['09:50', '10:35'], ['10:55', '11:40'], ['11:50', '12:35'], ['12:45', '13:30'], ['13:40', '14:25']],
  2: [['13:30', '14:15'], ['14:25', '15:10'], ['15:20', '16:05'], ['16:15', '17:00'], ['17:10', '17:55'], ['18:05', '18:50']],
};
export const DEFAULT_PE = { 1: [3], 2: [2] };
export const SCHOOL_RULES = {
  senior: { outdoor: 25, light: 37.5, relWorstIndoor: false },
  junior: { outdoor: 25, light: null, relWorstIndoor: true },
};

const toMin = (s) => Number(s.slice(0, 2)) * 60 + Number(s.slice(3, 5));
export const validTime = (s) => /^([01]\d|2[0-3]):[0-5]\d$/.test(s);

// Decision for one lesson. Returns { verdict: 'yes'|'light'|'no'|null, reason, pm, thr, trap, temp }
export function lessonVerdict(hours, stats, day, from, to, group) {
  const rule = SCHOOL_RULES[group] || SCHOOL_RULES.senior;
  const hs = hours.filter((h) => dayOf(h) === day && (hourOf(h) + 1) * 60 > toMin(from) && hourOf(h) * 60 < toMin(to));
  if (!hs.length) return { verdict: null, reason: 'r_nodata' };
  const worst = hs.reduce((a, b) => (b.pm25 > a.pm25 ? b : a));
  const pm = worst.pm25;
  const trap = hs.some((h) => h.trap?.on);
  const temp = Math.min(...hs.map((h) => h.temp));
  const base = { pm, trap, temp };
  if (trap) return { ...base, verdict: 'no', reason: 'r_trap' };
  if (rule.light === null) {
    if (pm > rule.outdoor) return { ...base, verdict: 'no', reason: 'r_pm', thr: rule.outdoor };
    if (rule.relWorstIndoor && relOf(worst, stats) === 'worst') return { ...base, verdict: 'no', reason: 'r_rel' };
    return { ...base, verdict: 'yes', reason: 'r_ok', thr: rule.outdoor };
  }
  if (pm > rule.light) return { ...base, verdict: 'no', reason: 'r_pm', thr: rule.light };
  if (pm > rule.outdoor) return { ...base, verdict: 'light', reason: 'r_light', thr: rule.outdoor };
  return { ...base, verdict: 'yes', reason: 'r_ok', thr: rule.outdoor };
}

// bells: [[from, to], ...]; pe: lesson numbers (1-based) with PE
export function schoolDay(hours, day, bells, pe, group) {
  const stats = dayStats(hours);
  const lessons = bells.map(([from, to], i) => {
    const n = i + 1;
    const isPe = pe.includes(n);
    return { n, from, to, pe: isPe, ...lessonVerdict(hours, stats, day, from, to, group) };
  });
  return { day, group, lessons };
}

export function schoolDays(hours, nowIndex, bells) {
  const lastStart = bells.length ? Math.max(...bells.map((b) => toMin(b[0]))) : 0;
  const lastEnd = bells.length ? Math.max(...bells.map((b) => toMin(b[1]))) : 0;
  const out = [];
  const view = hours.slice(nowIndex, nowIndex + 72);
  for (const h of view) {
    const d = dayOf(h);
    if (out.includes(d)) continue;
    const [y, m, dd] = d.split('-').map(Number);
    const dow = new Date(Date.UTC(y, m - 1, dd)).getUTCDay();
    if (dow === 0 || dow === 6) continue;
    if (hours.some((x) => dayOf(x) === d && hourOf(x) === Math.floor(lastStart / 60))) out.push(d);
  }
  const now = hours[nowIndex];
  if (out[0] === dayOf(now) && hourOf(now) * 60 >= lastEnd) out.shift();
  return out;
}
