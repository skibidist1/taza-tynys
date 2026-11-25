// Data: real sensors (/api/sensors -> cache -> data/sensors_snapshot.json),
// CAMS + weather forecast (Open-Meteo -> cache -> data/snapshot.json), and the 48-hour forecast.
import { features, predict, HORIZON } from './forecast.js';

// CAMS and weather are requested at the selected school point (rounded to ~1 km for caching).
export function forecastUrls(point = { lat: 43.24, lon: 76.89 }) {
  const common = `latitude=${point.lat.toFixed(2)}&longitude=${point.lon.toFixed(2)}&timezone=Asia%2FAlmaty&past_days=1&forecast_days=3`;
  return {
    air: `https://air-quality-api.open-meteo.com/v1/air-quality?${common}&hourly=pm2_5,pm10,us_aqi`,
    wx: `https://api.open-meteo.com/v1/forecast?${common}&hourly=temperature_2m,temperature_850hPa,wind_speed_10m,boundary_layer_height&wind_speed_unit=ms`,
  };
}
export const SENSORS_URL = 'api/sensors';
const FC_KEY = 'taza.forecast.v2';
const SN_KEY = 'taza.sensors.v1';
const TIMEOUT_MS = 9000;
const FC_FRESH_MS = 3 * 3600 * 1000;
const SN_FRESH_MS = 10 * 60 * 1000;

async function fetchJson(url, timeoutMs = TIMEOUT_MS) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

const cacheGet = (k, valid) => {
  try { const v = JSON.parse(localStorage.getItem(k)); return valid(v) ? v : null; } catch { return null; }
};
const cacheSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* quota / private mode */ } };

export function validRaw(raw) {
  try {
    const a = raw.air.hourly;
    const w = raw.weather.hourly;
    return Array.isArray(a.time) && a.time.length >= 48 && a.pm2_5.length === a.time.length
      && Array.isArray(w.time) && ['temperature_2m', 'temperature_850hPa', 'wind_speed_10m', 'boundary_layer_height'].every((k) => w[k].length === w.time.length)
      && typeof raw.fetchedAt === 'string';
  } catch {
    return false;
  }
}

export function validSensors(s) {
  if (!s || !Array.isArray(s.sensors) || typeof s.fetchedAt !== 'string') return false;
  // an empty answer because the sources were down must not overwrite a good cache
  if (!s.liveCount && s.errors && s.errors.length) return false;
  return s.sensors.every((x) => typeof x.lat === 'number' && typeof x.lon === 'number');
}

export function localStamp(ms, offsetSec) {
  return new Date(ms + offsetSec * 1000).toISOString().slice(0, 16);
}

async function chain(url, key, freshMs, valid, wrap, fallbackUrl, preferCache) {
  const cached = cacheGet(key, valid);
  if (preferCache && cached && Date.now() - (cached.savedMs || 0) < freshMs) return { data: cached, source: 'cache', fresh: true };
  let error = null;
  try {
    const data = await wrap(url);
    if (!valid(data)) throw new Error('unexpected response');
    data.savedMs = Date.now();
    cacheSet(key, data);
    return { data, source: 'live' };
  } catch (e) {
    error = String(e.message || e);
  }
  if (cached) return { data: cached, source: 'cache', error };
  const snap = await (await fetch(fallbackUrl)).json();
  return { data: snap, source: 'snapshot', error };
}

export async function loadForecast({ preferCache = true, point } = {}) {
  const urls = forecastUrls(point);
  const key = point ? `${FC_KEY}.${point.lat.toFixed(2)},${point.lon.toFixed(2)}` : FC_KEY;
  const r = await chain(null, key, FC_FRESH_MS, validRaw, async () => {
    const [air, weather] = await Promise.all([fetchJson(urls.air), fetchJson(urls.wx)]);
    return { air, weather, fetchedAt: localStamp(Date.now(), air.utc_offset_seconds ?? 18000) };
  }, 'data/snapshot.json', preferCache);
  return { raw: r.data, source: r.source, error: r.error, fresh: r.fresh };
}

export const SENSORS_TIMEOUT_MS = 18000; // a cold serverless start can take ~9 s

// Instant first paint: cached sensors (any age) or the bundled snapshot; refresh separately.
export async function initialSensors() {
  const cached = cacheGet(SN_KEY, validSensors);
  if (cached) return { sensors: cached, source: 'cache' };
  return { sensors: await (await fetch('data/sensors_snapshot.json')).json(), source: 'snapshot' };
}

export async function loadSensors({ preferCache = true } = {}) {
  const r = await chain(SENSORS_URL, SN_KEY, SN_FRESH_MS, validSensors, (u) => fetchJson(u, SENSORS_TIMEOUT_MS), 'data/sensors_snapshot.json', preferCache);
  return { sensors: r.data, source: r.data.snapshot && r.source === 'live' ? 'snapshot' : r.source, error: r.error, fresh: r.fresh };
}

// ---- geography -----------------------------------------------------------

export function distanceKm(a, b) {
  const R = 6371;
  const toR = (d) => (d * Math.PI) / 180;
  const dLat = toR(b.lat - a.lat);
  const dLon = toR(b.lon - a.lon);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toR(a.lat)) * Math.cos(toR(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

export function nearestSensor(sensors, point) {
  let best = null;
  for (const s of sensors) {
    if (!s.ok) continue;
    const d = distanceKm(point, s);
    if (!best || d < best.km) best = { sensor: s, km: d };
  }
  return best;
}

// ---- hours + forecast ----------------------------------------------------

// Join CAMS + weather by hour; from "now" run the 48-hour forecast starting at pmNow (real sensor).
export function buildHours(raw, model, pmNow, nowMs = Date.now()) {
  const a = raw.air.hourly;
  const w = raw.weather.hourly;
  const offset = raw.air.utc_offset_seconds ?? 18000;
  const wi = new Map(w.time.map((t, i) => [t, i]));
  const hours = [];
  for (let i = 0; i < a.time.length; i++) {
    const j = wi.get(a.time[i]);
    if (j === undefined) continue;
    const temp = w.temperature_2m[j];
    const t850 = w.temperature_850hPa[j];
    hours.push({
      idx: hours.length, time: a.time[i], cams: a.pm2_5[i], temp, t850,
      inv: t850 != null && temp != null ? t850 - temp : null,
      wind: w.wind_speed_10m[j], blh: w.boundary_layer_height[j], fc: null, h: null, contrib: null,
    });
  }
  const nowKey = localStamp(nowMs, offset).slice(0, 13);
  let nowIndex = hours.findIndex((h) => h.time.slice(0, 13) === nowKey);
  let stale = false;
  if (nowIndex < 0) {
    // the data does not contain the real current hour (old cache/snapshot): replay from the fetch time, marked stale
    stale = true;
    nowIndex = Math.max(0, hours.findIndex((h) => h.time.slice(0, 13) === raw.fetchedAt.slice(0, 13)));
  }
  const now = hours[nowIndex];
  if (pmNow != null) {
    now.fc = pmNow;
    now.h = 0;
    for (let k = 1; k <= HORIZON && nowIndex + k < hours.length; k++) {
      const hr = hours[nowIndex + k];
      if ([hr.cams, hr.t850, hr.temp, hr.wind].some((v) => v == null)) continue;
      const x = features(pmNow, hr.cams, hr.t850, hr.temp, hr.wind, Number(hr.time.slice(11, 13)));
      const p = predict(model, k, x);
      hr.fc = p.pm;
      hr.h = k;
      hr.contrib = p.contrib;
    }
  }
  return { hours, nowIndex, stale, fetchedAt: raw.fetchedAt, offset };
}
