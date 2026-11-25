import { t, num, getLang, setLang, weekday, dateLong, hhmm, hhPlus1 } from './i18n.js';
import { loadForecast, normalize } from './data.js';
import { explain } from './trap.js';
import {
  levelOf, LEVEL_KEYS, WHO_STEPS, PROFILES, dayStats, relOf, findWindows, actions, nextSmog,
  schoolDay, schoolDays, groupLessons,
} from './advice.js';
import { computeHouse, HEATER_ORDER } from './calc.js';

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const lvlVar = (pm) => `var(--lvl${levelOf(pm)})`;

const store = {
  get(k, d) { try { const v = localStorage.getItem(`taza.${k}`); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`taza.${k}`, JSON.stringify(v)); } catch { /* ignore */ } },
};

const state = {
  model: null,
  factors: null,
  load: null,
  data: null,
  profile: store.get('profile', 'child'),
  tab: 'today',
  sel: null,
  schoolDay: null,
  house: store.get('house', null),
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
  const key = { live: 'src_live', cache: 'src_cache', snapshot: 'src_snapshot' }[load.source];
  let html = `<b>${esc(t(key, { t: ts }))}</b>`;
  if (load.source !== 'live' && load.error) html += ` <span class="warn">${esc(t('src_offline'))}</span>`;
  if (data.stale) html += ` <span class="warn">${esc(t('src_stale'))}</span>`;
  html += ` <button class="ghost" id="refresh" type="button">${esc(t('refresh'))}</button>`;
  html += `<span class="note">${esc(t('src_note'))}</span>`;
  $('#status').innerHTML = html;
  $('#refresh').onclick = () => boot(false);
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
  const parts = [
    g.wind.value < 1.0 ? t('story_calm', { v: num(g.wind.value, 1) })
      : g.wind.value < 2.0 ? t('story_weak', { v: num(g.wind.value, 1) }) : t('story_wind', { v: num(g.wind.value, 1) }),
    g.temp.value < -2 ? t('story_cold', { v: num(g.temp.value, 1) }) : t('story_mild', { v: num(g.temp.value, 1) }),
    g.blh.value < 150 ? t('story_lid', { v: num(g.blh.value) }) : t('story_high', { v: num(g.blh.value) }),
  ].join('; ');
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
    </article>`;
  el.querySelectorAll('[data-pick]').forEach((b) => {
    b.onclick = () => { state.sel = Number(b.dataset.pick); renderStrip(); renderWhy(); };
  });
}

// ---------- school ----------
function announcement(sd) {
  const groups = groupLessons(sd.lessons);
  const plan = groups.map((g) => `${g.from === g.to ? t('ann_lesson', { n: g.from }) : t('ann_lessons', { from: g.from, to: g.to })} — ${t(`v_${g.verdict}`)}`).join('; ');
  const lines = [t('ann_head'), t('ann_body', { date: dateLong(sd.day), plan })];
  const idx = state.data.hours.findIndex((h) => h.time === `${sd.day}T15:00`);
  if (idx >= 0) {
    const smog = nextSmog(state.data.hours, idx);
    if (smog && smog.from.slice(0, 10) === sd.day) {
      const real = smog.max > 37.5 || smog.hours.some((x) => x.trap?.on);
      lines.push(t(real ? 'ann_smog' : 'ann_dirty', { from: hhmm(smog.from) }));
    }
  }
  lines.push(t('ann_src'));
  return lines.join('\n');
}

function renderSchool() {
  const el = $('#view-school');
  const days = schoolDays(state.data.hours, state.data.nowIndex);
  if (!days.length) { el.innerHTML = `<article class="card"><h2>${esc(t('school_title'))}</h2><p>${esc(t('school_none'))}</p></article>`; return; }
  if (!days.includes(state.schoolDay)) state.schoolDay = days[0];
  const sd = schoolDay(state.data.hours, state.schoolDay);
  const ann = announcement(sd);
  el.innerHTML = `<article class="card">
      <div class="card-head"><h2>${esc(t('school_title'))}</h2><p class="hint">${esc(t('school_hint'))}</p></div>
      <div class="days">${days.map((d) => `<button class="chip" role="radio" data-d="${d}" aria-checked="${d === state.schoolDay}">${esc(dayName(d))}, ${esc(dateLong(d))}</button>`).join('')}</div>
      <ul class="lessons">${sd.lessons.filter((l) => l.verdict).map((l) => `
        <li class="v-${l.verdict}"><span>${esc(t('lesson', { n: l.n }))}</span><span class="tm">${l.from}–${l.to}</span>
        <span class="v">${esc(t(`v_${l.verdict}`))}</span><span class="pm">PM2.5 ${num(l.pm)} · ${num(l.temp)}°</span></li>`).join('')}</ul>
      <p class="hint" style="margin-top:10px">${esc(t('school_rule'))}</p>
    </article>
    <article class="card">
      <div class="ann" id="ann">${esc(ann)}</div>
      <button class="btn" id="copy" type="button">${esc(t('copy_btn'))}</button>
    </article>`;
  el.querySelectorAll('[data-d]').forEach((b) => { b.onclick = () => { state.schoolDay = b.dataset.d; renderSchool(); }; });
  $('#copy').onclick = async () => {
    const btn = $('#copy');
    try {
      await navigator.clipboard.writeText(ann);
      btn.textContent = t('copied');
    } catch {
      const r = document.createRange();
      r.selectNodeContents($('#ann'));
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      let ok = false;
      try { ok = document.execCommand('copy'); } catch { ok = false; }
      btn.textContent = ok ? t('copied') : t('copy_fail');
    }
    setTimeout(() => { btn.textContent = t('copy_btn'); }, 2500);
  };
}

// ---------- home ----------
const DEFAULT_AMOUNT = { coal_stove: 4, coal_advanced: 3, wood_stove: 6, gas_boiler: 2500, electric: 20000 };

function renderHome() {
  const f = state.factors;
  const el = $('#view-home');
  const hs = state.house || { heater: f.defaults.heater, amount: f.defaults.amount, insulate: false, prices: {} };
  state.house = hs;
  const res = computeHouse(f, hs);
  const base = res.base;
  const maxPm = Math.max(...res.options.map((o) => o.pm_kg_high), base.pm_kg_high, 1);
  const unit = (u) => t(`u_${u}`);
  const fmtAmt = (o) => `${num(o.amount, o.unit === 't' ? 1 : 0)} ${unit(o.unit)}`;
  const delta = (o) => {
    if (base.pm_kg === 0) return { txt: t('same'), cls: '' };
    const raw = ((o.pm_kg - base.pm_kg) / base.pm_kg) * 100;
    const d = Math.round(raw);
    if (d === 0) return { txt: t('same'), cls: '' };
    const v = Math.abs(raw) >= 99 && Math.abs(raw) < 100 ? num(Math.floor(Math.abs(raw) * 10) / 10, 1) : num(Math.abs(d));
    return d < 0 ? { txt: t('pm_cut', { v }), cls: 'good' } : { txt: t('pm_more', { v }), cls: 'bad' };
  };
  const srcName = (k) => f.sources[k];
  el.innerHTML = `<article class="card">
      <div class="card-head"><h2>${esc(t('home_title'))}</h2><p class="hint">${esc(t('home_hint'))}</p></div>
      <div class="form">
        <div class="field"><span>${esc(t('heater'))}</span>
          <div class="heaters">${HEATER_ORDER.map((k) => `<button class="chip" role="radio" data-h="${k}" aria-checked="${k === hs.heater}">${esc(t(`h_${k}`))}</button>`).join('')}</div></div>
        <label class="field"><span>${esc(t('amount'))} <span class="est">${esc(t('est'))}</span></span>
          <span class="inrow"><input type="number" id="amount" min="0" step="any" value="${hs.amount}" inputmode="decimal"> ${esc(unit(f.fuels[f.heaters[hs.heater].fuel].unit))}</span></label>
        <label class="check"><input type="checkbox" id="insulate" ${hs.insulate ? 'checked' : ''}> <span>${esc(t('insulate'))} <span class="est">−${num(f.insulation.saving.low * 100)}…${num(f.insulation.saving.high * 100)}% ${esc(t('est'))}</span></span></label>
        <details><summary>${esc(t('prices'))}</summary>
          <div class="prices">${Object.keys(f.fuels).map((k) => `<label class="field"><span>${esc(t(`p_${k}`))}</span>
            <input type="number" min="0" step="any" data-price="${k}" value="${hs.prices?.[k] ?? f.fuels[k].price_kzt}"></label>`).join('')}</div>
          <p class="hint" style="margin-top:8px">${esc(f.price_note)}</p>
        </details>
      </div>
    </article>
    <article class="card">
      <p class="small">${esc(t('res_now'))}</p>
      <div class="bigres">${esc(t('res_kg', { v: num(base.pm_kg, 1) }))}</div>
      <p class="small">${esc(t('res_range', { lo: num(base.pm_kg_low, 1), hi: num(base.pm_kg_high, 1) }))} · ${esc(t('col_cost'))}: ${num(base.cost_kzt)} ₸</p>
      <h2 style="margin-top:16px">${esc(t('res_cmp'))}</h2>
      <div class="opts">${res.options.map((o) => {
        const d = delta(o);
        return `<div class="opt ${o.key === hs.heater && !hs.insulate ? 'cur' : ''}">
          <div class="row"><span class="name">${esc(t(`h_${o.key}`))}${hs.insulate ? esc(t('plus_ins')) : ''}</span><span class="delta ${d.cls}">${esc(d.txt)}</span></div>
          <div class="pmbar"><i style="width:${(o.pm_kg / maxPm) * 100}%"></i></div>
          <div class="row meta"><span>PM2.5 ${num(o.pm_kg, o.pm_kg < 1 ? 2 : 1)} кг (${num(o.pm_kg_low, o.pm_kg_low < 1 ? 2 : 1)}–${num(o.pm_kg_high, o.pm_kg_high < 1 ? 2 : 1)})</span>
            <span>${esc(fmtAmt(o))} · ${num(o.cost_kzt)} ₸</span></div>
        </div>`;
      }).join('')}</div>
      <p class="hint" style="margin-top:12px">${esc(t('home_notes'))}</p>
    </article>
    <article class="card">
      <h2>${esc(t('sources'))}</h2>
      <ul class="srcs">${HEATER_ORDER.map((k) => {
        const h = f.heaters[k];
        return `<li><b>${esc(t(`h_${k}`))}</b>: ${num(h.pm25_g_per_gj.value, 2)} г/ГДж (${num(h.pm25_g_per_gj.low, 2)}–${num(h.pm25_g_per_gj.high, 2)}) — ${esc(srcName(h.pm25_g_per_gj.source))}, ${esc(h.pm25_g_per_gj.ref)}; КПД ${num(h.efficiency.low * 100)}–${num(h.efficiency.high * 100)}% — ${esc(h.efficiency.ref)}</li>`;
      }).join('')}
      ${Object.entries(f.fuels).map(([k, v]) => `<li><b>${esc(t(`p_${k}`).split(',')[0])}</b>: ${esc(v.ncv_gj_per_unit.ref)} — ${esc(srcName(v.ncv_gj_per_unit.source))}</li>`).join('')}
      <li>${esc(f.insulation.saving.ref)} — ${esc(srcName(f.insulation.saving.source))}</li></ul>
    </article>`;

  const save = () => { store.set('house', state.house); renderHome(); };
  el.querySelectorAll('[data-h]').forEach((b) => {
    b.onclick = () => { hs.heater = b.dataset.h; hs.amount = DEFAULT_AMOUNT[hs.heater]; save(); };
  });
  $('#amount').onchange = (e) => { const v = Number(e.target.value); if (v >= 0) { hs.amount = v; save(); } };
  $('#insulate').onchange = (e) => { hs.insulate = e.target.checked; save(); };
  el.querySelectorAll('[data-price]').forEach((inp) => {
    inp.onchange = () => {
      const v = Number(inp.value);
      if (v >= 0) { hs.prices = { ...(hs.prices || {}), [inp.dataset.price]: v }; save(); el.querySelector('details').open = true; }
    };
  });
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
  renderHome();
}

async function boot(preferCache = true) {
  if (!state.model) {
    const [m, f] = await Promise.all([fetch('data/model.json').then((r) => r.json()), fetch('data/factors.json').then((r) => r.json())]);
    state.model = m;
    state.factors = f;
  }
  state.load = await loadForecast({ preferCache });
  state.data = normalize(state.load.raw, state.model);
  state.sel = state.data.nowIndex;
  renderAll();
}

document.querySelectorAll('.tabs button').forEach((b) => { b.onclick = () => showTab(b.dataset.tab); });
window.addEventListener('hashchange', () => {
  const n = location.hash.slice(1);
  if (['today', 'why', 'school', 'home'].includes(n) && n !== state.tab) showTab(n);
});
$('#lang').onclick = () => { setLang(getLang() === 'kk' ? 'ru' : 'kk'); renderAll(); };
applyStatic();
const initial = location.hash.slice(1);
if (['today', 'why', 'school', 'home'].includes(initial)) showTab(initial);
boot().catch((e) => {
  $('#hero').innerHTML = `<p class="loading">Ошибка загрузки: ${esc(e.message || e)}</p>`;
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
