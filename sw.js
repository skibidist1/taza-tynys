// Service worker: versioned cache for the app shell and local data, network for Open-Meteo
// (the app itself keeps the last forecast in localStorage).
// VERSION = hash of the cached files; scripts/check.py verifies it, `--fix-sw` rewrites it.
const VERSION = 'taza-7087e290dd';
const ASSETS = [
  './',
  'index.html',
  'styles.css',
  'manifest.webmanifest',
  'js/app.js',
  'js/i18n.js',
  'js/data.js',
  'js/forecast.js',
  'js/advice.js',
  'data/forecast_model.json',
  'data/sensors_snapshot.json',
  'data/small_sample.json',
  'data/almaty_districts.json',
  'data/snapshot.json',
  'data/demo_winter.json',
  'icons/icon.svg',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Stale-while-revalidate: answer from cache at once (works offline), refresh the cache in background.
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Network only: other origins (Open-Meteo) and our own /api/ (live sensors must never come from this cache;
  // the app keeps its own dated copy in localStorage).
  if (e.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.includes('/api/')) return;
  e.respondWith(caches.open(VERSION).then(async (cache) => {
    const hit = await cache.match(e.request, { ignoreSearch: true });
    const net = fetch(e.request).then((res) => {
      if (res.ok) cache.put(e.request, res.clone());
      return res;
    }).catch(() => null);
    if (hit) { e.waitUntil(net); return hit; }
    return (await net) || (await cache.match('index.html')) || Response.error();
  }));
});
