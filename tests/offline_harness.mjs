// Fallback chains with stubbed fetch/localStorage: live -> cache -> bundled snapshot.
const args = typeof scriptArgs !== 'undefined' ? scriptArgs : arguments;
const snapText = read(args[0]);
const sensText = read(args[1]);
const snap = JSON.parse(snapText);
const mem = {};
globalThis.localStorage = { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = String(v); } };
let online = false;
const resp = (obj) => ({ ok: true, status: 200, json: async () => obj });
globalThis.fetch = async (url) => {
  if (url === 'data/snapshot.json') return resp(JSON.parse(snapText));
  if (url === 'data/sensors_snapshot.json') return resp(JSON.parse(sensText));
  if (!online) throw new Error('network down');
  if (url.includes('air-quality-api.open-meteo.com')) return resp(snap.air);
  if (url.includes('api.open-meteo.com')) return resp(snap.weather);
  if (url === 'api/sensors') { const s = JSON.parse(sensText); delete s.snapshot; return resp(s); }
  throw new Error(`unexpected ${url}`);
};
globalThis.AbortController = class { constructor() { this.signal = {}; } abort() {} };
globalThis.setTimeout = globalThis.setTimeout || (() => 0);
globalThis.clearTimeout = globalThis.clearTimeout || (() => {});
const { loadForecast, loadSensors } = await import('../js/data.js');
const out = {};
out.fcOffline = (await loadForecast()).source;
out.snOffline = (await loadSensors()).source;
online = true;
const r1 = await loadForecast({ preferCache: false }); out.fcOnline = r1.source; if (r1.error) out.err = r1.error;
out.snOnline = (await loadSensors({ preferCache: false })).source;
online = false;
out.fcCached = (await loadForecast({ preferCache: false })).source;
out.snCached = (await loadSensors({ preferCache: false })).source;
print(JSON.stringify(out));
