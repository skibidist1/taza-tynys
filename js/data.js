// Forecast loading: live Open-Meteo -> localStorage cache -> data/snapshot.json.
import { buildFeatures, predict } from './trap.js';

const COMMON = 'latitude=43.24&longitude=76.89&timezone=Asia%2FAlmaty&past_days=1&forecast_days=4';
export const AIR_URL = `https://air-quality-api.open-meteo.com/v1/air-quality?${COMMON}&hourly=pm2_5,pm10,us_aqi`;
export const WX_URL = `https://api.open-meteo.com/v1/forecast?${COMMON}&hourly=temperature_2m,wind_speed_10m,boundary_layer_height&wind_speed_unit=ms`;
const CACHE_KEY = 'taza.forecast.v1';
const TIMEOUT_MS = 9000;
const MAX_CACHE_AGE_MS = 3 * 3600 * 1000; // re-fetch when older than 3 h

async function fetchJson(url) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

export function validRaw(raw) {
  try {
    const a = raw.air.hourly;
    const w = raw.weather.hourly;
    return Array.isArray(a.time) && a.time.length >= 48 && a.pm2_5.length === a.time.length
      && Array.isArray(w.time) && w.temperature_2m.length === w.time.length
      && w.wind_speed_10m.length === w.time.length && w.boundary_layer_height.length === w.time.length
      && typeof raw.fetchedAt === 'string';
  } catch {
    return false;
  }
}

// Local Almaty wall-clock "YYYY-MM-DDTHH:MM" for a UTC offset in seconds.
export function localStamp(ms, offsetSec) {
  return new Date(ms + offsetSec * 1000).toISOString().slice(0, 16);
}

function readCache() {
  try {
    const raw = JSON.parse(localStorage.getItem(CACHE_KEY));
    return validRaw(raw) ? raw : null;
  } catch {
    return null;
  }
}

function writeCache(raw) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(raw)); } catch { /* quota or private mode */ }
}

// Returns { raw, source: 'live' | 'cache' | 'snapshot', error? }
export async function loadForecast({ preferCache = true } = {}) {
  const cached = readCache();
  if (preferCache && cached && Date.now() - (cached.savedMs || 0) < MAX_CACHE_AGE_MS) {
    return { raw: cached, source: 'cache', fresh: true };
  }
  let error = null;
  if (typeof navigator === 'undefined' || navigator.onLine !== false) {
    try {
      const [air, weather] = await Promise.all([fetchJson(AIR_URL), fetchJson(WX_URL)]);
      const raw = { air, weather, savedMs: Date.now(), fetchedAt: localStamp(Date.now(), air.utc_offset_seconds ?? 18000) };
      if (!validRaw(raw)) throw new Error('unexpected API response');
      writeCache(raw);
      return { raw, source: 'live' };
    } catch (e) {
      error = String(e.message || e);
    }
  } else error = 'offline';
  if (cached) return { raw: cached, source: 'cache', error };
  const snap = await (await fetch('data/snapshot.json')).json();
  return { raw: snap, source: 'snapshot', error };
}

// Join air + weather by time, add trap model output, find "now".
export function normalize(raw, model, nowMs = Date.now()) {
  const a = raw.air.hourly;
  const w = raw.weather.hourly;
  const offset = raw.air.utc_offset_seconds ?? 18000;
  const wIndex = new Map(w.time.map((t, i) => [t, i]));
  const wt = w.time;
  const hours = [];
  for (let i = 0; i < a.time.length; i++) {
    const t = a.time[i];
    const j = wIndex.get(t);
    if (j === undefined || a.pm2_5[i] == null) continue;
    const x = buildFeatures(wt, w.wind_speed_10m, w.temperature_2m, w.boundary_layer_height, j);
    const ok = x.every((v) => v !== null && Number.isFinite(v));
    const pr = ok ? predict(model, x) : null;
    hours.push({
      idx: hours.length,
      time: t,
      pm25: a.pm2_5[i],
      pm10: a.pm10?.[i] ?? null,
      aqi: a.us_aqi?.[i] ?? null,
      temp: w.temperature_2m[j],
      wind: w.wind_speed_10m[j],
      blh: w.boundary_layer_height[j],
      x: ok ? x : null,
      trap: pr ? { p: pr.p, on: pr.p >= model.threshold } : null,
    });
  }
  const nowKey = localStamp(nowMs, offset).slice(0, 13);
  let nowIndex = hours.findIndex((h) => h.time.slice(0, 13) === nowKey);
  let stale = false;
  if (nowIndex < 0 || hours.length - nowIndex < 24) {
    // Data does not cover the real "now" (old cache or snapshot): replay it from the moment it was fetched.
    stale = true;
    const fk = raw.fetchedAt.slice(0, 13);
    nowIndex = Math.max(0, hours.findIndex((h) => h.time.slice(0, 13) === fk));
  }
  return { hours, nowIndex, stale, fetchedAt: raw.fetchedAt, offset };
}
