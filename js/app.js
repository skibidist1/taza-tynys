import { t, tl, num, getLang, setLang, weekday, dateLong, hhmm, hhPlus1 } from './i18n.js';
import { loadForecast, loadSensors, initialSensors, buildHours, nearestSensor } from './data.js';
import {
  catOf, CAT_KEYS, EPA_STEPS, PROFILES, findWindows, actions, nextBad, forecastView,
  schoolDay, schoolDays, DEFAULT_BELLS, DEFAULT_PE, validTime,
} from './advice.js';

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const catVar = (pm) => `var(--lvl${catOf(pm)})`;
const store = {
  get(k, d) { try { const v = localStorage.getItem(`taza.${k}`); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`taza.${k}`, JSON.stringify(v)); } catch { /* ignore */ } },
};

// District centres are approximate, for choosing a point quickly.
const PLACES = [
  { key: 'd_almaly', lat: 43.250, lon: 76.905 }, { key: 'd_auezov', lat: 43.225, lon: 76.850 },
  { key: 'd_bostandyk', lat: 43.205, lon: 76.905 }, { key: 'd_zhetysu', lat: 43.290, lon: 76.945 },
  { key: 'd_medeu', lat: 43.245, lon: 76.975 }, { key: 'd_turksib', lat: 43.335, lon: 76.965 },
  { key: 'd_alatau', lat: 43.280, lon: 76.800 }, { key: 'd_nauryzbay', lat: 43.195, lon: 76.795 },
];
const BBOX = { s: 43.12, n: 43.37, w: 76.74, e: 77.07 };
const MAP_W = 360;
const MAP_H = Math.round(MAP_W * ((BBOX.n - BBOX.s) / ((BBOX.e - BBOX.w) * Math.cos((43.25 * Math.PI) / 180))));

const state = {
  model: null, small: null, fcLoad: null, snLoad: null, data: null, mode: 'live', actual: null,
  point: store.get('point', { key: 'd_almaly', lat: 43.250, lon: 76.905 }),
  profile: store.get('profile2', 'sensitive'), tab: 'today', sel: null, schoolDay: null,
  near: null, pmNow: null,
};

function dayName(day) {
  const today = state.data.hours[state.data.nowIndex].time.slice(0, 10);
  const diff = Math.round((new Date(`${day}T00:00:00Z`) - new Date(`${today}T00:00:00Z`)) / 864e5);
  if (diff === 0) return t('today');
  if (diff === 1) return t('tomorrow');
  return `${weekday(day)}, ${dateLong(day)}`;
}
const pointLabel = () => (state.point.name || (state.point.key ? t(state.point.key) : t('place_custom')));
const catName = (pm, l) => (l ? tl(l, `cat_${CAT_KEYS[catOf(pm)]}`) : t(`cat_${CAT_KEYS[catOf(pm)]}`));

function applyStatic() {
  document.documentElement.lang = getLang() === 'kk' ? 'kk' : 'ru';
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $('#lang').textContent = t('lang');
}

// ---------- status ----------
function renderStatus() {
  const { fcLoad, snLoad, data } = state;
  const stamp = (s) => `${dateLong(s.slice(0, 10))}, ${s.slice(11, 16)}`;
  let html;
  if (state.mode === 'archive') {
    html = `<b>${esc(t('src_archive', { t: stamp(data.fetchedAt) }))}</b> <button class="ghost" id="live" type="button">${esc(t('back_live'))}</button>
      <span class="note">${esc(t('archive_note'))}</span>`;
  } else {
    const fk = { live: 'src_live', cache: 'src_cache', snapshot: 'src_snapshot' }[fcLoad.source];
    const sk = { live: 'sn_live', cache: 'sn_cache', snapshot: 'sn_snapshot' }[snLoad.source];
    html = `<b>${esc(t(fk, { t: stamp(data.fetchedAt) }))}</b> · <span>${esc(t(sk, { attr: snLoad.sensors.attribution || '', t: stamp(snLoad.sensors.fetchedAt) }))}</span>`;
    if (fcLoad.source !== 'live' && fcLoad.error) html += ` <span class="warn">${esc(t('src_offline'))}</span>`;
    if (data.stale) html += ` <span class="warn">${esc(t('src_stale'))}</span>`;
    html += ` <button class="ghost" id="refresh" type="button">${esc(t('refresh'))}</button> <button class="ghost" id="winter" type="button">${esc(t('show_winter'))}</button>`;
  }
  $('#status').innerHTML = html;
  if ($('#refresh')) $('#refresh').onclick = () => boot('live', false);
  if ($('#winter')) $('#winter').onclick = () => boot('archive');
  if ($('#live')) $('#live').onclick = () => boot('live');
}

// ---------- map ----------
function proj(lat, lon) {
  return [((lon - BBOX.w) / (BBOX.e - BBOX.w)) * MAP_W, ((BBOX.n - lat) / (BBOX.n - BBOX.s)) * MAP_H];
}

function renderPlace() {
  const sensors = state.snLoad.sensors.sensors;
  const [px, py] = proj(state.point.lat, state.point.lon);
  const near = state.near;
  const line = near ? (() => { const [sx, sy] = proj(near.sensor.lat, near.sensor.lon); return `<line x1="${px}" y1="${py}" x2="${sx}" y2="${sy}" class="nline"/>`; })() : '';
  const dots = sensors.filter((s) => s.lat > BBOX.s && s.lat < BBOX.n && s.lon > BBOX.w && s.lon < BBOX.e).map((s) => {
    const [x, y] = proj(s.lat, s.lon);
    return s.ok
      ? `<circle cx="${x}" cy="${y}" r="7" fill="${catVar(s.pm25)}" class="sdot"><title>${esc(s.name)}: ${num(s.pm25, 1)}</title></circle>`
      : `<circle cx="${x}" cy="${y}" r="3" class="sdead"><title>${esc(s.name)}</title></circle>`;
  }).join('');
  const labels = PLACES.map((p) => { const [x, y] = proj(p.lat, p.lon); return `<text x="${x}" y="${y}" class="dlabel">${esc(t(p.key))}</text>`; }).join('');
  $('#place').innerHTML = `<div class="card-head"><h2>${esc(t('place_title'))}</h2><p class="hint">${esc(t('place_hint'))}</p></div>
    <svg class="map" id="map" viewBox="0 0 ${MAP_W} ${MAP_H}" role="img" aria-label="${esc(t('place_title'))}">
      <rect x="0" y="0" width="${MAP_W}" height="${MAP_H}" rx="18" class="mapbg"/>
      ${labels}${line}${dots}
      <g transform="translate(${px},${py})" class="pin"><circle r="9"/><circle r="3" class="pin-c"/></g>
    </svg>
    <div class="days">${PLACES.map((p) => `<button class="chip" role="radio" data-place="${p.key}" aria-checked="${p.key === state.point.key}">${esc(t(p.key))}</button>`).join('')}</div>`;
  $('#map').onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * MAP_W;
    const y = ((e.clientY - r.top) / r.height) * MAP_H;
    setPoint({ key: null, lat: BBOX.n - (y / MAP_H) * (BBOX.n - BBOX.s), lon: BBOX.w + (x / MAP_W) * (BBOX.e - BBOX.w) });
  };
  document.querySelectorAll('[data-place]').forEach((b) => {
    b.onclick = () => { const p = PLACES.find((q) => q.key === b.dataset.place); setPoint({ key: p.key, lat: p.lat, lon: p.lon }); };
  });
}

function setPoint(p) {
  state.point = p;
  if (state.mode === 'live') store.set('point', p);
  compute();
  renderAll();
}

// ---------- today ----------
function renderHero() {
  const { hours, nowIndex } = state.data;
  const cams = hours[nowIndex].cams;
  const pm = state.pmNow;
  const near = state.near;
  const ratio = cams > 0 ? pm / cams : null;
  let cmp = t('cams_close');
  if (ratio && ratio > 1.3) cmp = t('cams_low', { x: num(ratio, 1) });
  else if (ratio && ratio < 1 / 1.3) cmp = t('cams_high', { x: num(1 / ratio, 1) });
  const sn = state.snLoad.sensors;
  $('#hero').style.setProperty('--hero', catVar(pm));
  $('#hero').innerHTML = `
    <p class="kicker">${esc(t('now_title'))} · ${esc(pointLabel())}</p>
    <div class="big"><span class="value">${num(pm)}</span><span class="unit">${esc(t('pm_unit'))}</span><span class="pill">${esc(catName(pm))}</span></div>
    <div class="facts">
      ${near ? `<span>${esc(t('now_sensor', { name: near.sensor.name, km: num(near.km, 1) }))}</span>` : `<span class="warn">${esc(t('no_sensor'))}</span>`}
      ${near && near.km > 5 ? `<span class="warn">${esc(t('sensor_far', { km: num(near.km, 1) }))}</span>` : ''}
      <span>${esc(t('now_city', { m: num(sn.median, 1), n: sn.liveCount ?? 0 }))}</span>
    </div>
    <div class="vs"><span>${esc(t('cams_says', { v: num(cams) }))}</span>${near ? `<b>${esc(cmp)}</b>` : ''}</div>`;
}

function renderProfiles() {
  const el = $('#profiles');
  el.innerHTML = `<span class="lbl">${esc(t('profile'))}</span>${Object.keys(PROFILES).map((k) => `
    <button class="chip" role="radio" data-p="${k}" aria-checked="${k === state.profile}">${esc(t(`prof_${k}`))}</button>`).join('')}
    ${state.profile === 'sensitive' ? `<span class="lbl small">${esc(t('prof_sensitive_hint'))}</span>` : ''}`;
  el.querySelectorAll('[data-p]').forEach((b) => {
    b.onclick = () => { state.profile = b.dataset.p; store.set('profile2', state.profile); renderToday(); renderSchool(); };
  });
}

function renderActions() {
  const { hours, nowIndex } = state.data;
  const items = actions(hours, nowIndex, state.profile).map((a) => {
    if (a.key === 'vent_now') return esc(t('vent_now', { pm: num(a.pm) }));
    if (a.key === 'vent_later') return esc(t('vent_later', { t: hhmm(a.time), pm: num(a.pm) }));
    if (a.key === 'vent_short') return esc(t('vent_short'));
    if (a.key === 'activity_window') return esc(t('activity_window', { from: `${dayName(a.from.slice(0, 10)).toLowerCase()} ${hhmm(a.from)}`, to: hhPlus1(a.to), pm: num(a.pm) }));
    if (a.key === 'activity_none') return esc(t('activity_none', { limit: num(a.limit, 1) }));
    const bad = a.bad ? `<span class="sub2">${esc(t('bad_span', { from: hhmm(a.bad.from), to: hhPlus1(a.bad.to), max: num(a.bad.max) }))}</span>` : '';
    return `${esc(t(a.key))}${bad}`;
  });
  $('#actions').innerHTML = `<h2>${esc(t('actions_title'))}</h2>
    <ol class="acts">${items.map((s) => `<li><span>${s}</span></li>`).join('')}</ol>
    <p class="ref">${esc(t('refs'))}</p>`;
}

function renderStrip() {
  const { hours, nowIndex } = state.data;
  const view = forecastView(hours, nowIndex);
  const inWin = new Set();
  findWindows(hours, nowIndex, state.profile).filter((w) => w.ok).forEach((w) => w.window.hours.forEach((h) => inWin.add(h.idx)));
  const act = state.actual;
  const max = Math.max(60, ...view.map((h) => h.fc), ...(act ? view.map((h) => act[h.time] ?? 0) : []));
  const byDay = [];
  for (const h of view) {
    const d = h.time.slice(0, 10);
    if (!byDay.length || byDay[byDay.length - 1].day !== d) byDay.push({ day: d, hours: [] });
    byDay[byDay.length - 1].hours.push(h);
  }
  if (state.sel === null || !view.some((h) => h.idx === state.sel)) state.sel = nowIndex;
  $('#strip').innerHTML = byDay.map((g) => `
    <div class="day"><div class="day-label">${esc(dayName(g.day))}</div>
      <div class="bars">${g.hours.map((h) => {
        const cls = ['h', h.idx === nowIndex ? 'now' : '', h.idx === state.sel ? 'sel' : '', inWin.has(h.idx) ? 'window' : ''].join(' ');
        const a = act && act[h.time] != null ? `<span class="act" style="bottom:${Math.min(100, (act[h.time] / max) * 100)}%"></span>` : '';
        return `<button class="${cls}" data-i="${h.idx}" style="--c:${catVar(h.fc)}" aria-label="${esc(hhmm(h.time))} PM2.5 ${num(h.fc)}">
          ${a}<span class="bar" style="height:${Math.max(3, (h.fc / max) * 100)}%"></span><span class="win"></span></button>`;
      }).join('')}</div>
      <div class="ticks">${g.hours.map((h) => `<span>${Number(h.time.slice(11, 13)) % 3 === 0 ? Number(h.time.slice(11, 13)) : ''}</span>`).join('')}</div>
    </div>`).join('');
  $('#strip').querySelectorAll('.h').forEach((b) => { b.onclick = () => { state.sel = Number(b.dataset.i); renderStrip(); renderWhy(); }; });
  $('#mark-actual').hidden = !act;
  const h = state.data.hours[state.sel];
  $('#hour-detail').textContent = t('hour_detail', {
    t: `${dayName(h.time.slice(0, 10))} ${hhmm(h.time)}`, fc: num(h.fc), cams: num(h.cams), inv: num(h.inv, 1), wind: num(h.wind, 1), blh: num(h.blh),
  });
}

function renderWindows() {
  const { hours, nowIndex } = state.data;
  const prof = PROFILES[state.profile];
  const wins = findWindows(hours, nowIndex, state.profile);
  const rng = (a, b) => (num(a) === num(b) ? num(a) : `${num(a)}–${num(b)}`);
  $('#windows').innerHTML = `<div class="card-head"><h2>${esc(t('windows_title'))} · ${esc(t(`prof_${state.profile}`))}</h2>
    <p class="hint">${esc(t('windows_hint', { limit: num(prof.limit, 1) }))}</p></div>
    <ul class="wins">${wins.map((w) => (w.ok
      ? `<li><span class="d">${esc(dayName(w.day))}</span><span class="tm">${esc(`${hhmm(w.window.from)}–${hhPlus1(w.window.to)}`)}</span><span class="small">PM2.5 ${rng(w.window.min, w.window.max)}</span></li>`
      : `<li class="bad"><span class="d">${esc(dayName(w.day))}</span><span class="small">${esc(w.window ? t('win_none', { from: hhmm(w.window.from), to: hhPlus1(w.window.to) }) : t('win_none_short'))}</span></li>`)).join('')}</ul>`;
}

function renderLegend() {
  const b = [0, ...EPA_STEPS];
  $('#legend').innerHTML = `<h2>${esc(t('legend_title'))}</h2>
    <div class="lg">${CAT_KEYS.map((k, i) => `<div style="background:var(--lvl${i})"><b>${i < 5 ? `${num(b[i], 1)}–${num(b[i + 1], 1)}` : `> ${num(225.4, 1)}`}</b>${esc(t(`cat_${k}`))}</div>`).join('')}</div>`;
}

function renderToday() {
  renderPlace();
  renderHero();
  renderProfiles();
  renderActions();
  renderStrip();
  renderWindows();
  renderLegend();
}

// ---------- why ----------
function renderWhy() {
  const el = $('#view-why');
  const { hours, nowIndex } = state.data;
  const h = hours[state.sel ?? nowIndex];
  const view = forecastView(hours, nowIndex).filter((x) => x.h > 0);
  const worst = view.reduce((a, b) => (b.fc > a.fc ? b : a), view[0]);
  const picks = [{ k: 'pick_now', i: nowIndex }, ...(worst ? [{ k: 'pick_worst', i: worst.idx, tm: `${dayName(worst.time.slice(0, 10)).toLowerCase()} ${hhmm(worst.time)}` }] : [])];
  const phys = [
    h.inv != null ? t(h.inv > 0 ? 'inv_yes' : 'inv_no', { v: num(Math.abs(h.inv), 1) }) : '',
    t('wind_txt', { v: num(h.wind, 1) }),
    t('blh_txt', { v: num(h.blh) }),
  ].filter(Boolean);
  let contribHtml = `<p class="small">${esc(t('why_now'))}</p>`;
  if (h.contrib) {
    const c = h.contrib;
    const groups = [['log_pm_now', c[0]], ['log_cams', c[1]], ['inversion', c[2]], ['wind', c[3]], ['hour', c[4] + c[5] + c[6] + c[7]]];
    const maxAbs = Math.max(0.6, ...groups.map((g) => Math.abs(g[1])));
    const dir = (v) => (Math.abs(v) < 0.05 ? t('neutral') : v > 0 ? t('raises') : t('lowers'));
    contribHtml = `<p class="hint">${esc(t('contrib_hint', { h: h.h }))}</p><div class="factors">${groups.map(([k, v]) => `
      <div class="factor"><div class="top2"><span>${esc(t(`f_${k}`))}</span><span class="eff">${esc(dir(v))}</span></div>
      <div class="fbar"><span class="mid"></span><span class="fill ${v > 0 ? 'up' : 'down'}" style="width:${(Math.abs(v) / maxAbs) * 50}%"></span></div></div>`).join('')}</div>`;
  }
  el.innerHTML = `
    <div class="profiles">${picks.map((p) => `<button class="chip" role="radio" data-pick="${p.i}" aria-checked="${p.i === h.idx}">${esc(t(p.k, { t: p.tm }))}</button>`).join('')}</div>
    <article class="card gauge">
      <p class="hint">${esc(t('why_for', { t: `${dayName(h.time.slice(0, 10))} ${hhmm(h.time)}` }))}</p>
      <h2>${esc(t('why_title'))}</h2>
      <div class="pct" style="color:${catVar(h.fc)}">${num(h.fc)} <span class="unit">${esc(t('pm_unit'))}</span></div>
      <p class="story">${esc(t('why_fc', { fc: num(h.fc), cat: catName(h.fc), cams: num(h.cams) }))}</p>
      ${phys.map((p) => `<p>${esc(p)}</p>`).join('')}
    </article>
    <article class="card">
      <div class="wx">
        <div><b>${h.inv == null ? '—' : `${h.inv > 0 ? '+' : ''}${num(h.inv, 1)}°`}</b><span>T850 − T2м</span></div>
        <div><b>${num(h.wind, 1)}</b><span>м/с</span></div>
        <div><b>${num(h.blh)}</b><span>м · BLH</span></div>
      </div>
      <h2 style="margin-top:14px">${esc(t('contrib_title'))}</h2>
      ${contribHtml}
    </article>
    <article class="card td">
      <h2>${esc(t('td_title'))}</h2>
      <p style="margin-top:6px">${esc(t('td_steps'))}</p>
      <p class="tdnum">${esc(t('td_num'))}</p>
      <p class="small">${esc(t('td_caveat'))}</p>
      <p class="ref">${esc(t('td_src'))}</p>
    </article>`;
  el.querySelectorAll('[data-pick]').forEach((b) => { b.onclick = () => { state.sel = Number(b.dataset.pick); renderStrip(); renderWhy(); }; });
}

// ---------- school ----------
function schoolCfg() {
  const c = store.get('school2', null) || {};
  return {
    shift: c.shift === 2 ? 2 : 1,
    bells: { 1: c.bells?.[1] || DEFAULT_BELLS[1], 2: c.bells?.[2] || DEFAULT_BELLS[2] },
    pe: { 1: c.pe?.[1] || DEFAULT_PE[1], 2: c.pe?.[2] || DEFAULT_PE[2] },
  };
}

function announcement(sd, lang) {
  const lines = [tl(lang, 'ann_head'), tl(lang, 'ann_intro', { date: dateLong(sd.day, lang) })];
  const pe = sd.lessons.filter((l) => l.pe && l.verdict);
  if (!pe.length) lines.push(tl(lang, 'ann_none'));
  for (const l of pe) {
    lines.push(`• ${tl(lang, 'ann_item', {
      n: l.n, from: l.from, to: l.to, verdict: tl(lang, `v_${l.verdict}`),
      reason: tl(lang, l.reason, { pm: num(l.pm), cat: catName(l.pm, lang) }),
    })}`);
  }
  const last = sd.lessons[sd.lessons.length - 1];
  if (last) {
    const endH = Number(last.to.slice(0, 2)) + (Number(last.to.slice(3, 5)) > 0 ? 1 : 0);
    const idx = state.data.hours.findIndex((h) => h.time === `${sd.day}T${String(endH).padStart(2, '0')}:00`);
    if (idx >= 0) {
      const bad = nextBad(state.data.hours, idx, 35.4);
      if (bad && bad.from.slice(0, 10) === sd.day) lines.push(tl(lang, 'ann_bad', { from: hhmm(bad.from), limit: num(35.4, 1) }));
    }
  }
  lines.push(tl(lang, 'ann_src'));
  return lines.join('\n');
}

async function copyText(text, btn, label) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = t('copied');
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch { ok = false; }
    ta.remove();
    btn.textContent = ok ? t('copied') : t('copy_fail');
  }
  setTimeout(() => { btn.textContent = label; }, 2500);
}

function renderSchool() {
  const el = $('#view-school');
  const cfg = schoolCfg();
  const bells = cfg.bells[cfg.shift];
  const pe = cfg.pe[cfg.shift];
  const save = () => { store.set('school2', cfg); renderSchool(); };
  const thr = 35.4;
  const days = schoolDays(state.data.hours, state.data.nowIndex, bells);
  if (!days.includes(state.schoolDay)) state.schoolDay = days[0] || null;
  const sd = state.schoolDay ? schoolDay(state.data.hours, state.schoolDay, bells, pe, thr) : null;
  const chip = (attr, val, cur, label) => `<button class="chip" role="radio" ${attr}="${val}" aria-checked="${val === cur}">${esc(label)}</button>`;
  const row = (l) => {
    const res = l.pe && l.verdict
      ? `<span class="v">${esc(t(`v_${l.verdict}`))}</span><span class="why2">${esc(t(l.reason, { pm: num(l.pm), cat: catName(l.pm) }))}</span>`
      : `<span class="pm">${l.verdict ? `PM2.5 ${num(l.pm)} · ${num(l.temp)}°` : esc(t('r_nodata'))}</span>`;
    return `<li class="${l.pe && l.verdict ? `v-${l.verdict}` : 'plain'}">
      <span class="ln">${esc(t('lesson', { n: l.n }))}<span class="tm">${l.from}–${l.to}</span></span>
      <label class="pe"><input type="checkbox" data-pe="${l.n}" ${l.pe ? 'checked' : ''}> ${esc(t('pe_label'))}</label>
      <span class="res">${res}</span></li>`;
  };
  el.innerHTML = `<article class="card">
      <div class="card-head"><h2>${esc(t('school_title'))}</h2><p class="hint">${esc(t('school_hint'))}</p>
        <p class="hint">${esc(t('school_point', { p: pointLabel() }))}</p></div>
      <div class="days">${chip('data-shift', 1, cfg.shift, t('shift_1'))}${chip('data-shift', 2, cfg.shift, t('shift_2'))}</div>
      ${days.length ? `<div class="days">${days.map((d) => chip('data-d', d, state.schoolDay, `${dayName(d)}${dayName(d).includes(dateLong(d)) ? '' : `, ${dateLong(d)}`}`)).join('')}</div>` : `<p>${esc(t('school_none'))}</p>`}
      ${sd ? `<ul class="lessons">${sd.lessons.map(row).join('')}</ul>` : ''}
      ${sd && !pe.length ? `<p class="hint" style="margin-top:8px">${esc(t('no_pe'))}</p>` : ''}
      <details class="bells"><summary>${esc(t('bells_edit'))}</summary>
        <div class="bell-list">${bells.map(([a, b], i) => `<div class="bell"><span>${esc(t('lesson', { n: i + 1 }))}</span>
          <input type="time" data-bell="${i}" data-k="0" value="${a}" required> – <input type="time" data-bell="${i}" data-k="1" value="${b}" required></div>`).join('')}</div>
        <div class="days"><button class="ghost" id="bell-add" type="button">${esc(t('bells_add'))}</button>
          <button class="ghost" id="bell-rm" type="button">${esc(t('bells_remove'))}</button>
          <button class="ghost" id="bell-reset" type="button">${esc(t('bells_reset'))}</button></div>
      </details>
    </article>
    ${sd ? `<article class="card"><h2>${esc(t('ann_title'))}</h2>
      <div class="ann">${esc(announcement(sd, 'ru'))}</div><button class="btn" id="copy-ru" type="button">${esc(t('copy_ru'))}</button>
      <div class="ann">${esc(announcement(sd, 'kk'))}</div><button class="btn" id="copy-kk" type="button">${esc(t('copy_kk'))}</button>
    </article>` : ''}
    <article class="card"><p class="small">${esc(t('school_method', { thr: num(thr, 1) }))}</p><p class="ref">${esc(t('refs'))}</p></article>`;

  el.querySelectorAll('[data-shift]').forEach((b) => { b.onclick = () => { cfg.shift = Number(b.dataset.shift); state.schoolDay = null; save(); }; });
  el.querySelectorAll('[data-d]').forEach((b) => { b.onclick = () => { state.schoolDay = b.dataset.d; renderSchool(); }; });
  el.querySelectorAll('[data-pe]').forEach((c) => {
    c.onchange = () => {
      const set = new Set(cfg.pe[cfg.shift]);
      if (c.checked) set.add(Number(c.dataset.pe)); else set.delete(Number(c.dataset.pe));
      cfg.pe[cfg.shift] = [...set].sort((a, b) => a - b);
      save();
    };
  });
  const keepOpen = () => { const d = el.querySelector('details.bells'); if (d) d.open = true; };
  el.querySelectorAll('[data-bell]').forEach((inp) => {
    inp.onchange = () => {
      if (!validTime(inp.value)) return;
      const nb = cfg.bells[cfg.shift].map((x) => [...x]);
      nb[Number(inp.dataset.bell)][Number(inp.dataset.k)] = inp.value;
      cfg.bells[cfg.shift] = nb;
      save();
      keepOpen();
    };
  });
  $('#bell-add').onclick = () => {
    const nb = cfg.bells[cfg.shift].map((x) => [...x]);
    const last = nb[nb.length - 1] || ['08:00', '08:00'];
    const m = Number(last[1].slice(0, 2)) * 60 + Number(last[1].slice(3)) + 10;
    const f = (x) => `${String(Math.floor(x / 60) % 24).padStart(2, '0')}:${String(x % 60).padStart(2, '0')}`;
    nb.push([f(m), f(m + 45)]);
    cfg.bells[cfg.shift] = nb;
    save();
    keepOpen();
  };
  $('#bell-rm').onclick = () => {
    if (cfg.bells[cfg.shift].length <= 1) return;
    cfg.bells[cfg.shift] = cfg.bells[cfg.shift].slice(0, -1);
    cfg.pe[cfg.shift] = cfg.pe[cfg.shift].filter((n) => n <= cfg.bells[cfg.shift].length);
    save();
    keepOpen();
  };
  $('#bell-reset').onclick = () => { cfg.bells[cfg.shift] = DEFAULT_BELLS[cfg.shift]; cfg.pe[cfg.shift] = DEFAULT_PE[cfg.shift]; save(); };
  if (sd) {
    $('#copy-ru').onclick = () => copyText(announcement(sd, 'ru'), $('#copy-ru'), t('copy_ru'));
    $('#copy-kk').onclick = () => copyText(announcement(sd, 'kk'), $('#copy-kk'), t('copy_kk'));
  }
}

// ---------- honesty ----------
function renderHonest() {
  const m = state.model.metrics;
  const f1 = (v) => num(v, 1);
  const pk = m.peaks_over_100;
  const small = state.small?.results || [];
  const okSensors = state.snLoad.sensors.sensors.filter((s) => s.ok);
  $('#view-honest').innerHTML = `
    <article class="card"><h2>${esc(t('h_title'))}</h2><p class="small" style="margin-top:6px">${esc(t('h_intro'))}</p></article>
    <article class="card"><h2>${esc(t('h_cams_title'))}</h2>
      <p class="tdnum">${esc(t('h_cams', { n: pk.n, g: num(pk.ground_median), c: num(pk.cams_median), x: num(pk.ground_median / pk.cams_median, 1) }))}</p></article>
    <article class="card"><h2>${esc(t('h_fc_title'))}</h2><p class="hint">${esc(t('h_fc_hint', { test: m.test }))}</p>
      <table class="tbl"><thead><tr><th>${esc(t('h_col_h'))}</th><th>${esc(t('h_col_model'))}</th><th>${esc(t('h_col_pers'))}</th><th>${esc(t('h_col_cams'))}</th></tr></thead>
      <tbody>${Object.entries(m.buckets).map(([b, v]) => `<tr><td>${esc(b)}</td><td><b>${f1(v.model)}</b></td><td>${f1(v.persistence)}</td><td>${f1(v.cams)}</td></tr>`).join('')}
      <tr><td><b>1–48</b></td><td><b>${f1(m.mae_model)}</b></td><td>${f1(m.mae_persistence)}</td><td>${f1(m.mae_cams)}</td></tr></tbody></table>
      <p class="small" style="margin-top:10px"><b>${esc(t('h_peaks', { m: f1(m.mae_peaks_over_100.model), p: f1(m.mae_peaks_over_100.persistence), c: f1(m.mae_peaks_over_100.cams) }))}</b></p>
      <p class="small" style="margin-top:10px">${esc(t('h_dec', { m: num(m.decision_acc.model * 100), p: num(m.decision_acc.persistence * 100), c: num(m.decision_acc.cams * 100) }))}</p></article>
    <article class="card"><h2>${esc(t('h_small_title'))}</h2><p class="hint">${esc(t('h_small_hint'))}</p>
      ${small.length ? `<table class="tbl"><thead><tr><th>${esc(t('h_col_sensor'))}</th><th>${esc(t('h_col_model'))}</th><th>${esc(t('h_col_pers'))}</th><th>${esc(t('h_col_cams'))}</th></tr></thead>
      <tbody>${small.map((r) => `<tr><td>${esc(r.sensor)}</td><td><b>${f1(r.mae.model)}</b></td><td>${f1(r.mae.persistence)}</td><td>${f1(r.mae.cams)}</td></tr>`).join('')}</tbody></table>` : '<p>—</p>'}</article>
    <article class="card"><h2>${esc(t('h_sensors_title'))}</h2><p class="small">${esc(t('h_sensors', { n: okSensors.length }))}</p></article>
    <article class="card"><h2>${esc(t('h_limits_title'))}</h2><p class="small">${esc(t('h_limits'))}</p></article>
    <article class="card"><h2>${esc(t('h_sources_title'))}</h2><p class="small">${esc(t('h_sources'))}</p><p class="ref">${esc(t('h_reports'))}</p></article>`;
}

// ---------- tabs, compute, boot ----------
const TABS = ['today', 'why', 'school', 'honest'];
function showTab(name) {
  state.tab = name;
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  document.querySelectorAll('.view').forEach((v) => { v.hidden = v.dataset.view !== name; });
  if (location.hash !== `#${name}`) history.replaceState(null, '', `${location.search}#${name}`);
}

function compute() {
  const raw = state.fcLoad.raw;
  const sensors = state.snLoad.sensors.sensors;
  state.near = nearestSensor(sensors, state.point);
  const nowMs = state.mode === 'archive' ? Date.parse(raw.fetchedAt) : Date.now();
  const probe = buildHours(raw, state.model, null, nowMs);
  state.pmNow = state.near ? state.near.sensor.pm25 : probe.hours[probe.nowIndex].cams;
  state.data = buildHours(raw, state.model, state.pmNow, nowMs);
  if (state.sel === null || state.sel < state.data.nowIndex) state.sel = state.data.nowIndex;
}

function renderAll() {
  applyStatic();
  if (!state.data) return;
  renderStatus();
  renderToday();
  renderWhy();
  renderSchool();
  renderHonest();
}

async function boot(mode = 'live', preferCache = true) {
  if (!state.model) {
    state.model = await fetch('data/forecast_model.json').then((r) => r.json());
    state.small = await fetch('data/small_sample.json').then((r) => (r.ok ? r.json() : null)).catch(() => null);
  }
  state.mode = mode;
  if (mode === 'archive') {
    const demo = await fetch('data/demo_winter.json').then((r) => r.json());
    state.fcLoad = { raw: demo, source: 'archive' };
    state.snLoad = { sensors: demo.sensors, source: 'archive' };
    state.actual = Object.fromEntries(demo.actual.time.map((tm, i) => [tm, demo.actual.pm25[i]]));
    state.point = { key: null, name: 'OpenAQ 8876', lat: 43.2529, lon: 76.9312 };
  } else {
    // First paint from cached/bundled sensors, then refresh them without blocking the screen.
    [state.fcLoad, state.snLoad] = await Promise.all([loadForecast({ preferCache }), initialSensors()]);
    state.actual = null;
    state.point = store.get('point', { key: 'd_almaly', lat: 43.250, lon: 76.905 });
  }
  state.sel = null;
  state.schoolDay = null;
  compute();
  renderAll();
  if (mode === 'live') refreshSensors(preferCache);
}

async function refreshSensors(preferCache) {
  const r = await loadSensors({ preferCache }).catch(() => null);
  if (!r || state.mode !== 'live') return;
  if (r.source === 'snapshot' && state.snLoad.source === 'cache') return; // keep the newer cached copy
  state.snLoad = r;
  compute();
  renderAll();
}

document.querySelectorAll('.tabs button').forEach((b) => { b.onclick = () => showTab(b.dataset.tab); });
window.addEventListener('hashchange', () => { const n = location.hash.slice(1); if (TABS.includes(n) && n !== state.tab) showTab(n); });
$('#lang').onclick = () => { setLang(getLang() === 'kk' ? 'ru' : 'kk'); renderAll(); };
applyStatic();
if (TABS.includes(location.hash.slice(1))) showTab(location.hash.slice(1));
boot(new URLSearchParams(location.search).get('demo') === 'winter' ? 'archive' : 'live').catch((e) => {
  $('#hero').innerHTML = `<p class="loading">Ошибка загрузки: ${esc(e.message || e)}</p>`;
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
