import { t, tl, num, getLang, setLang, weekday, dateLong, hhmm, hhPlus1 } from './i18n.js';
import { loadForecast, normalize } from './data.js';
import { explain } from './trap.js';
import {
  levelOf, LEVEL_KEYS, WHO_STEPS, PROFILES, dayStats, relOf, findWindows, actions, nextSmog,
  schoolDay, schoolDays, DEFAULT_BELLS, DEFAULT_PE, validTime,
} from './advice.js';

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const lvlVar = (pm) => `var(--lvl${levelOf(pm)})`;

const store = {
  get(k, d) { try { const v = localStorage.getItem(`taza.${k}`); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`taza.${k}`, JSON.stringify(v)); } catch { /* ignore */ } },
};

const state = {
  model: null,
  load: null,
  data: null,
  profile: store.get('profile', 'child'),
  tab: 'today',
  sel: null,
  schoolDay: null,
};

function dayName(day) {
  const today = state.data.hours[state.data.nowIndex].time.slice(0, 10);
  const d0 = new Date(`${today}T00:00:00Z`);
  const d1 = new Date(`${day}T00:00:00Z`);
  const diff = Math.round((d1 - d0) / 864e5);
  if (diff === 0) return t('today');
  if (diff === 1) return t('tomorrow');
  return `${weekday(day)}, ${dateLong(day)}`;
}
const rangeTxt = (a, b) => (num(a) === num(b) ? num(a) : `${num(a)}–${num(b)}`);
const span = (from, to) => `${hhmm(from)}–${hhPlus1(to)}`;

// ---------- static texts ----------
function applyStatic() {
  document.documentElement.lang = getLang() === 'kk' ? 'kk' : 'ru';
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $('#lang').textContent = t('lang');
}

// ---------- status line ----------
function renderStatus() {
  const { load, data } = state;
  const ts = `${dateLong(data.fetchedAt.slice(0, 10))}, ${data.fetchedAt.slice(11, 16)}`;
  const key = { live: 'src_live', cache: 'src_cache', snapshot: 'src_snapshot', archive: 'src_archive' }[load.source];
  let html = `<b>${esc(t(key, { t: ts }))}</b>`;
  if (load.source !== 'live' && load.error) html += ` <span class="warn">${esc(t('src_offline'))}</span>`;
  if (data.stale) html += ` <span class="warn">${esc(t('src_stale'))}</span>`;
  if (load.source === 'archive') {
    html += ` <button class="ghost" id="live" type="button">${esc(t('back_live'))}</button>`;
  } else {
    html += ` <button class="ghost" id="refresh" type="button">${esc(t('refresh'))}</button>`;
    html += ` <button class="ghost" id="winter" type="button">${esc(t('show_winter'))}</button>`;
  }
  html += `<span class="note">${esc(t(load.source === 'archive' ? 'archive_note' : 'src_note'))}</span>`;
  $('#status').innerHTML = html;
  if ($('#refresh')) $('#refresh').onclick = () => boot(false);
  if ($('#winter')) $('#winter').onclick = () => boot(true, 'archive');
  if ($('#live')) $('#live').onclick = () => boot(true);
}

// ---------- today ----------
function renderHero() {
  const { hours, nowIndex } = state.data;
  const h = hours[nowIndex];
  const lv = levelOf(h.pm25);
  const stats = dayStats(hours);
  const ratio = h.pm25 / 15;
  $('#hero').style.setProperty('--hero', `var(--lvl${lv})`);
  $('#hero').innerHTML = `
    <p class="kicker">${esc(t('now'))} · ${esc(hhmm(h.time))} · PM2.5</p>
    <div class="big"><span class="value">${num(h.pm25)}</span><span class="unit">${esc(t('pm_unit'))}</span>
      <span class="pill">${esc(t(`lvl_${LEVEL_KEYS[lv]}`))}</span></div>
    <div class="facts">
      <span>${esc(ratio > 1 ? t('who_ratio', { x: num(ratio, 1) }) : t('who_below'))}</span>
      <span>${esc(t(`rel_${relOf(h, stats)}`))}</span>
    </div>`;
}

function renderProfiles() {
  const el = $('#profiles');
  el.innerHTML = `<span class="lbl">${esc(t('profile'))}</span>${Object.keys(PROFILES).map((k) => `
    <button class="chip" role="radio" data-p="${k}" aria-checked="${k === state.profile}">${esc(t(`prof_${k}`))}</button>`).join('')}`;
  el.querySelectorAll('.chip').forEach((b) => {
    b.onclick = () => {
      state.profile = b.dataset.p;
      store.set('profile', state.profile);
      renderToday();
    };
  });
}

function renderActions() {
  const { hours, nowIndex } = state.data;
  const acts = actions(hours, nowIndex, state.profile);
  const items = acts.map((a) => {
    switch (a.key) {
      case 'vent_now': return t('vent_now', { pm: num(a.pm) });
      case 'vent_later': return t('vent_later', { t: hhmm(a.time), pm: num(a.pm) });
      case 'vent_short': return t('vent_short');
      case 'activity_window': return t('activity_window', { act: t(`act_${a.activity}`), from: `${dayName(a.from.slice(0, 10)).toLowerCase()} ${hhmm(a.from)}`, to: hhPlus1(a.to), pm: num(a.pm) });
      case 'activity_none': return t('activity_none', { act: t(`act_${a.activity}`), limit: num(a.limit, 1) });
      default: {
        const smog = a.smog
          ? t(a.smog.max > 37.5 || a.smog.trap ? 'smog_span' : 'dirty_span', { from: hhmm(a.smog.from), to: hhPlus1(a.smog.to), max: num(a.smog.max) })
          : t('smog_none');
        return `${smog}<span class="sub2">${esc(t(a.key))}</span>`;
      }
    }
  });
  $('#actions').innerHTML = `<h2>${esc(t('actions_title'))}</h2>
    <ol class="acts">${items.map((s, i) => `<li><span>${i < 2 ? esc(s) : s}</span></li>`).join('')}</ol>
    <p class="ref">${esc(t('who_ref'))}</p>`;
}

function renderStrip() {
  const { hours, nowIndex } = state.data;
  const view = hours.slice(nowIndex, nowIndex + 72);
  const wins = findWindows(hours, nowIndex, state.profile);
  const inWin = new Set();
  wins.filter((w) => w.ok).forEach((w) => w.window.hours.forEach((h) => inWin.add(h.idx)));
  const max = Math.max(60, ...view.map((h) => h.pm25));
  const byDay = [];
  for (const h of view) {
    const d = h.time.slice(0, 10);
    if (!byDay.length || byDay[byDay.length - 1].day !== d) byDay.push({ day: d, hours: [] });
    byDay[byDay.length - 1].hours.push(h);
  }
  if (state.sel === null || state.sel < nowIndex || state.sel >= nowIndex + 72) state.sel = nowIndex;
  $('#strip').innerHTML = byDay.map((g) => `
    <div class="day">
      <div class="day-label">${esc(dayName(g.day))}</div>
      <div class="bars">${g.hours.map((h) => {
        const cls = ['h', h.idx === nowIndex ? 'now' : '', h.idx === state.sel ? 'sel' : '', inWin.has(h.idx) ? 'window' : '', h.trap?.on ? 'trap' : ''].join(' ');
        const pct = Math.max(3, (h.pm25 / max) * 100);
        return `<button class="${cls}" data-i="${h.idx}" style="--c:${lvlVar(h.pm25)}" aria-label="${esc(hhmm(h.time))} PM2.5 ${num(h.pm25)}">
          <span class="bar" style="height:${pct}%"></span><span class="win"></span></button>`;
      }).join('')}</div>
      <div class="ticks">${g.hours.map((h) => `<span>${Number(h.time.slice(11, 13)) % 3 === 0 ? Number(h.time.slice(11, 13)) : ''}</span>`).join('')}</div>
    </div>`).join('');
  $('#strip').querySelectorAll('.h').forEach((b) => {
    b.onclick = () => { state.sel = Number(b.dataset.i); renderStrip(); renderWhy(); };
  });
  renderHourDetail();
}

function renderHourDetail() {
  const h = state.data.hours[state.sel];
  $('#hour-detail').textContent = t('hour_detail', {
    t: `${dayName(h.time.slice(0, 10))} ${hhmm(h.time)}`, pm: num(h.pm25), pm10: num(h.pm10), temp: num(h.temp, 1),
    wind: num(h.wind, 1), blh: num(h.blh), p: h.trap ? num(h.trap.p * 100) : '—',
  });
}

function renderWindows() {
  const { hours, nowIndex } = state.data;
  const prof = PROFILES[state.profile];
  const wins = findWindows(hours, nowIndex, state.profile);
  $('#windows').innerHTML = `<div class="card-head"><h2>${esc(t('windows_title'))} · ${esc(t(`prof_${state.profile}`))}</h2>
    <p class="hint">${esc(t('windows_hint', { limit: num(prof.limit, 1) }))}</p></div>
    <ul class="wins">${wins.map((w) => {
      if (w.ok) {
        return `<li><span class="d">${esc(dayName(w.day))}</span><span class="tm">${esc(span(w.window.from, w.window.to))}</span>
          <span class="small">PM2.5 ${rangeTxt(Math.min(...w.window.hours.map((h) => h.pm25)), w.window.max)}</span></li>`;
      }
      const txt = w.window ? t('win_none', { from: hhmm(w.window.from), to: hhPlus1(w.window.to) }) : t('win_none_short');
      return `<li class="bad"><span class="d">${esc(dayName(w.day))}</span><span class="small">${esc(txt)}</span></li>`;
    }).join('')}</ul>`;
}

function renderLegend() {
  const bounds = [0, ...WHO_STEPS];
  $('#legend').innerHTML = `<h2>${esc(t('legend_title'))}</h2>
    <div class="lg">${LEVEL_KEYS.map((k, i) => `<div style="background:var(--lvl${i})"><b>${i < 5 ? `${num(bounds[i], 1)}–${num(bounds[i + 1], 1)}` : `> ${num(75)}`}</b>${esc(t(`lvl_${k}`))}</div>`).join('')}</div>
    <p class="hint" style="margin-top:8px">${esc(t('legend_note'))} AQG 15 · IT-4 25 · IT-3 37,5 · IT-2 50 · IT-1 75.</p>`;
}

function renderToday() {
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
  const h = state.data.hours[state.sel ?? state.data.nowIndex];
  const m = state.model;
  if (!h.x) { el.innerHTML = `<article class="card"><p>—</p></article>`; return; }
  const ex = explain(m, h.x);
  const g = Object.fromEntries(ex.groups.map((x) => [x.key, x]));
  const sign = (v, eps) => (v > eps ? 'up' : v < -eps ? 'down' : 'n');
  const partList = [
    t(`story_wind_${sign(g.wind.logit, 0.1)}`, { v: num(g.wind.value, 1) }),
    t(`story_temp_${sign(g.temp.logit, 0.1)}`, { v: num(g.temp.value, 1) }),
    t(`story_blh_${sign(g.blh.logit, 0.1)}`, { v: num(g.blh.value) }),
  ];
  const hs = sign(g.hour.logit, 0.3);
  if (hs !== 'n') partList.push(t(`story_hour_${hs}`, { t: hhmm(h.time) }));
  const parts = partList.join('; ');
  const story = ex.trap ? t('why_story_on', { parts }) : t('why_story_off', { parts });
  const maxAbs = Math.max(1.2, ...ex.groups.map((x) => Math.abs(x.logit)));
  const valText = (x) => {
    if (x.key === 'wind') return t('f_val_wind', { v: num(x.value, 1), typ: num(x.typical, 1) });
    if (x.key === 'temp') return t('f_val_temp', { v: num(x.value, 1), typ: num(x.typical, 1) });
    if (x.key === 'blh') return t('f_val_blh', { v: num(x.value), typ: num(x.typical) });
    if (x.key === 'hour') return `${hhmm(h.time)} — ${t('f_val_hour')}`;
    return t(`f_val_weekend_${x.value}`);
  };
  const dir = (v) => (Math.abs(v) < 0.1 ? t('neutral') : v > 0 ? t('raises') : t('lowers'));
  const mt = m.metrics;
  const { hours, nowIndex } = state.data;
  const next24 = hours.slice(nowIndex, nowIndex + 24).filter((x) => x.trap);
  const worst = next24.reduce((a, b) => (b.trap.p > a.trap.p ? b : a), next24[0]);
  const picks = [{ k: 'pick_now', i: nowIndex }, ...(worst && worst.idx !== nowIndex ? [{ k: 'pick_worst', i: worst.idx, tm: hhmm(worst.time) }] : [])];
  el.innerHTML = `
    <div class="profiles">${picks.map((p) => `<button class="chip" role="radio" data-pick="${p.i}" aria-checked="${p.i === h.idx}">${esc(t(p.k, { t: p.tm }))}</button>`).join('')}</div>
    <article class="card gauge">
      <p class="hint">${esc(t('why_for', { t: `${dayName(h.time.slice(0, 10))} ${hhmm(h.time)}` }))}</p>
      <h2>${esc(ex.trap ? t('trap_on') : t('trap_off'))}</h2>
      <div class="pct">${num(ex.p * 100)}%</div>
      <div class="track" aria-hidden="true"><span class="thr" style="left:${m.threshold * 100}%"></span><span class="dot" style="left:${ex.p * 100}%"></span></div>
      <p class="small">${esc(t('trap_prob', { p: num(ex.p * 100) }))}</p>
      <p class="story">${esc(story)}</p>
    </article>
    <article class="card">
      <div class="wx">
        <div><b>${num(h.wind, 1)}</b><span>м/с</span></div>
        <div><b>${num(h.temp, 1)}°</b><span>°C</span></div>
        <div><b>${num(h.blh)}</b><span>м · BLH</span></div>
      </div>
      <div class="factors" style="margin-top:14px">${ex.groups.map((x) => {
        const w = (Math.abs(x.logit) / maxAbs) * 50;
        return `<div class="factor">
          <div class="top2"><span>${esc(t(`f_${x.key}`))}</span><span class="eff">${esc(dir(x.logit))}</span></div>
          <div class="fbar"><span class="mid"></span><span class="fill ${x.logit > 0 ? 'up' : 'down'}" style="width:${w}%"></span></div>
          <span class="val">${esc(valText(x))}</span></div>`;
      }).join('')}</div>
    </article>
    <article class="card">
      <h2>${esc(t('model_title'))}</h2>
      <p class="small" style="margin-top:6px">${esc(t('model_text', {
        auc: num(mt.auc, 2), base_t: num(mt.baseline_temp_only_auc, 2), base_h: num(mt.baseline_hour_only_auc, 2),
        prec: num(mt.precision, 2), rec: num(mt.recall, 2),
      }))}</p>
      <p class="small" style="margin-top:6px"><a href="evals/trap_report.md">${esc(t('model_report'))}</a></p>
    </article>
    <article class="card td">
      <h2>${esc(t('td_title'))}</h2>
      <p style="margin-top:6px">${esc(t('td_steps'))}</p>
      <p class="tdnum">${esc(t('td_num'))}</p>
      <p class="small">${esc(t('td_caveat'))}</p>
      <p class="ref">${esc(t('td_src'))}</p>
    </article>`;
  el.querySelectorAll('[data-pick]').forEach((b) => {
    b.onclick = () => { state.sel = Number(b.dataset.pick); renderStrip(); renderWhy(); };
  });
}

// ---------- school ----------
function schoolCfg() {
  const c = store.get('school', null) || {};
  return {
    shift: c.shift === 2 ? 2 : 1,
    group: c.group === 'junior' ? 'junior' : 'senior',
    bells: { 1: c.bells?.[1] || DEFAULT_BELLS[1], 2: c.bells?.[2] || DEFAULT_BELLS[2] },
    pe: { 1: c.pe?.[1] || DEFAULT_PE[1], 2: c.pe?.[2] || DEFAULT_PE[2] },
  };
}

function announcement(sd, lang) {
  const g = tl(lang, `g_${sd.group}`);
  const lines = [tl(lang, 'ann_head'), tl(lang, 'ann_intro', { date: dateLong(sd.day, lang), group: g })];
  const pe = sd.lessons.filter((l) => l.pe && l.verdict);
  if (!pe.length) lines.push(tl(lang, 'ann_none'));
  for (const l of pe) {
    lines.push(`• ${tl(lang, 'ann_item', {
      n: l.n, from: l.from, to: l.to, verdict: tl(lang, `v_${l.verdict}`),
      reason: tl(lang, l.reason, { pm: num(l.pm), thr: num(l.thr, 1), group: g }),
    })}`);
  }
  const last = sd.lessons[sd.lessons.length - 1];
  if (last) {
    const endH = Number(last.to.slice(0, 2)) + (Number(last.to.slice(3, 5)) > 0 ? 1 : 0);
    const endHour = `${sd.day}T${String(endH).padStart(2, '0')}:00`;
    const idx = state.data.hours.findIndex((h) => h.time === endHour);
    if (idx >= 0) {
      const smog = nextSmog(state.data.hours, idx);
      if (smog && smog.from.slice(0, 10) === sd.day) {
        const real = smog.max > 37.5 || smog.hours.some((x) => x.trap?.on);
        lines.push(tl(lang, real ? 'ann_smog' : 'ann_dirty', { from: hhmm(smog.from) }));
      }
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
  const save = () => { store.set('school', cfg); renderSchool(); };
  const days = schoolDays(state.data.hours, state.data.nowIndex, bells);
  if (!days.includes(state.schoolDay)) state.schoolDay = days[0] || null;
  const sd = state.schoolDay ? schoolDay(state.data.hours, state.schoolDay, bells, pe, cfg.group) : null;
  const chip = (attr, val, cur, label) => `<button class="chip" role="radio" ${attr}="${val}" aria-checked="${val === cur}">${esc(label)}</button>`;
  const row = (l) => {
    const verdict = l.pe && l.verdict
      ? `<span class="v">${esc(t(`v_${l.verdict}`))}</span><span class="why2">${esc(t(l.reason, { pm: num(l.pm), thr: num(l.thr, 1), group: t(`g_${cfg.group}`) }))}</span>`
      : `<span class="pm">${l.verdict ? `PM2.5 ${num(l.pm)} · ${num(l.temp)}°` : esc(t('r_nodata'))}</span>`;
    return `<li class="${l.pe && l.verdict ? `v-${l.verdict}` : 'plain'}">
      <span class="ln">${esc(t('lesson', { n: l.n }))}<span class="tm">${l.from}–${l.to}</span></span>
      <label class="pe"><input type="checkbox" data-pe="${l.n}" ${l.pe ? 'checked' : ''}> ${esc(t('pe_label'))}</label>
      <span class="res">${verdict}</span></li>`;
  };
  el.innerHTML = `<article class="card">
      <div class="card-head"><h2>${esc(t('school_title'))}</h2><p class="hint">${esc(t('school_hint'))}</p></div>
      <div class="days">${chip('data-shift', 1, cfg.shift, t('shift_1'))}${chip('data-shift', 2, cfg.shift, t('shift_2'))}
        <span class="sep"></span>${chip('data-group', 'junior', cfg.group, t('g_junior_chip'))}${chip('data-group', 'senior', cfg.group, t('g_senior_chip'))}</div>
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
    ${sd ? `<article class="card">
      <h2>${esc(t('ann_title'))}</h2>
      <div class="ann" id="ann-ru">${esc(announcement(sd, 'ru'))}</div>
      <button class="btn" id="copy-ru" type="button">${esc(t('copy_ru'))}</button>
      <div class="ann" id="ann-kk">${esc(announcement(sd, 'kk'))}</div>
      <button class="btn" id="copy-kk" type="button">${esc(t('copy_kk'))}</button>
    </article>` : ''}
    <article class="card"><p class="small">${esc(t('school_method'))}</p></article>`;

  el.querySelectorAll('[data-shift]').forEach((b) => { b.onclick = () => { cfg.shift = Number(b.dataset.shift); state.schoolDay = null; save(); }; });
  el.querySelectorAll('[data-group]').forEach((b) => { b.onclick = () => { cfg.group = b.dataset.group; save(); }; });
  el.querySelectorAll('[data-d]').forEach((b) => { b.onclick = () => { state.schoolDay = b.dataset.d; renderSchool(); }; });
  el.querySelectorAll('[data-pe]').forEach((c) => {
    c.onchange = () => {
      const n = Number(c.dataset.pe);
      const set = new Set(cfg.pe[cfg.shift]);
      if (c.checked) set.add(n); else set.delete(n);
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
  $('#bell-reset').onclick = () => {
    cfg.bells[cfg.shift] = DEFAULT_BELLS[cfg.shift];
    cfg.pe[cfg.shift] = DEFAULT_PE[cfg.shift];
    save();
  };
  if (sd) {
    $('#copy-ru').onclick = () => copyText(announcement(sd, 'ru'), $('#copy-ru'), t('copy_ru'));
    $('#copy-kk').onclick = () => copyText(announcement(sd, 'kk'), $('#copy-kk'), t('copy_kk'));
  }
}

// ---------- tabs & boot ----------
function showTab(name) {
  state.tab = name;
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  document.querySelectorAll('.view').forEach((v) => { v.hidden = v.dataset.view !== name; });
  if (location.hash !== `#${name}`) history.replaceState(null, '', `#${name}`);
}

function renderAll() {
  applyStatic();
  if (!state.data) return;
  renderStatus();
  renderToday();
  renderWhy();
  renderSchool();
}

async function boot(preferCache = true, mode = 'live') {
  if (!state.model) {
    state.model = await fetch('data/model.json').then((r) => r.json());
  }
  if (mode === 'archive') {
    // Real winter smog episode from the Open-Meteo archive, replayed as if "now" were its morning.
    const raw = await fetch('data/demo_winter.json').then((r) => r.json());
    state.load = { raw, source: 'archive' };
    state.data = normalize(raw, state.model, Date.parse(raw.fetchedAt));
  } else {
    state.load = await loadForecast({ preferCache });
    state.data = normalize(state.load.raw, state.model);
  }
  state.schoolDay = null;
  state.sel = state.data.nowIndex;
  renderAll();
}

document.querySelectorAll('.tabs button').forEach((b) => { b.onclick = () => showTab(b.dataset.tab); });
window.addEventListener('hashchange', () => {
  const n = location.hash.slice(1);
  if (['today', 'why', 'school'].includes(n) && n !== state.tab) showTab(n);
});
$('#lang').onclick = () => { setLang(getLang() === 'kk' ? 'ru' : 'kk'); renderAll(); };
applyStatic();
const initial = location.hash.slice(1);
if (['today', 'why', 'school'].includes(initial)) showTab(initial);
boot(true, new URLSearchParams(location.search).get('demo') === 'winter' ? 'archive' : 'live').catch((e) => {
  $('#hero').innerHTML = `<p class="loading">Ошибка загрузки: ${esc(e.message || e)}</p>`;
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
