"""Train and evaluate the 48-hour PM2.5 forecast on REAL measurements.

Data: pipeline/history/ground_8876.json (OpenAQ archive station 8876 + CAMS + weather).
Heating-season hours only (October-March).
Split with a gap: train targets < 2025-02-01; test origins >= 2025-02-03 (48 h gap, no shared hours),
test = Feb-Mar 2025 and Oct-Nov 2025.
CAMS in the archive is close to an analysis, while the app uses a real CAMS *forecast*. To avoid
overtrusting it we add horizon-dependent noise to the CAMS feature (train and test) and to the CAMS
baseline: log-noise sigma(h) = 0.10 + 0.20*h/48 (ASSUMPTION, Open-Meteo has no archived CAMS forecasts
for this period).
School decisions are evaluated on school hours only (target 8:00-14:59, Mon-Fri), with equal-share
comparisons and day-block bootstrap intervals.
Writes data/forecast_model.json, evals/forecast_report.md, tests/forecast_cases.json.
Usage: python3 pipeline/fetch_ground.py && python3 pipeline/train_forecast.py
"""
import json
import pathlib
import sys
from datetime import date, datetime

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from forecast_features import FEATURES, HORIZON, features, interval, predict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
L2 = 1.0
EPA = [9.0, 35.4, 55.4, 125.4, 225.4]
LIMIT = 35.4                       # PE decision boundary (top of EPA "Moderate")
BUCKETS = [(1, 6), (7, 12), (13, 24), (25, 48)]
TRAIN_END = "2025-02-01T00:00"     # train targets strictly before
TEST_START = "2025-02-03T00:00"    # test origins from (48 h gap)
SEED = 11
N_CANDIDATES = [3, 4, 5, 6]   # sensor 'now' only for the nearest hours (current/next lessons)
SHARES = [0.3, 0.4, 0.5]


def heating(t):
    return int(t[5:7]) in (10, 11, 12, 1, 2, 3)


def test_month(t):
    return ("2025-02" <= t[:7] <= "2025-03") or ("2025-10" <= t[:7] <= "2025-11")


def school_hour(t):
    d = datetime.fromisoformat(t)
    return d.weekday() < 5 and 8 <= d.hour <= 14


def cams_sigma(h):
    return 0.10 + 0.20 * h / 48


def load():
    h = json.loads((ROOT / "pipeline" / "history" / "ground_8876.json").read_text())["hourly"]
    h["pm25"] = [None if v is None or v < 0 else v for v in h["pm25"]]  # negative = instrument flag
    return h


def build(h, origin_ok, target_ok, rng):
    """Rows per horizon k: X, y_log, now, cams_forecast, y, target_time."""
    n = len(h["time"])
    data = {k: [[], [], [], [], [], []] for k in range(1, HORIZON + 1)}
    for t in range(n):
        if h["pm25"][t] is None or not heating(h["time"][t]) or not origin_ok(h["time"][t]):
            continue
        for k in range(1, HORIZON + 1):
            j = t + k
            if j >= n or h["pm25"][j] is None or not heating(h["time"][j]) or not target_ok(h["time"][j]):
                continue
            if any(h[v][j] is None for v in ("cams", "t850", "temp", "wind")):
                continue
            cams_fc = h["cams"][j] * float(np.exp(rng.normal(0, cams_sigma(k))))
            x = features(h["pm25"][t], cams_fc, h["t850"][j], h["temp"][j], h["wind"][j], int(h["time"][j][11:13]))
            d = data[k]
            for lst, v in zip(d, (x, np.log1p(h["pm25"][j]), h["pm25"][t], cams_fc, h["pm25"][j], h["time"][j])):
                lst.append(v)
    return {k: [np.array(a) for a in v] for k, v in data.items()}


def ridge(X, y, mean, std):
    Z = (X - mean) / std
    Z1 = np.c_[Z, np.ones(len(Z))]
    reg = L2 * np.eye(Z1.shape[1])
    reg[-1, -1] = 0
    w = np.linalg.solve(Z1.T @ Z1 + reg, Z1.T @ y)
    return w[:-1], w[-1]


def fit(tr):
    allX = np.vstack([tr[k][0] for k in tr if len(tr[k][0])])
    mean, std = allX.mean(0), allX.std(0)
    std[std == 0] = 1
    hz = []
    for k in range(1, HORIZON + 1):
        c, b = ridge(tr[k][0], tr[k][1], mean, std)
        resid = tr[k][1] - (((tr[k][0] - mean) / std) @ c + b)
        hz.append({"h": k, "coef": [round(float(v), 6) for v in c], "intercept": round(float(b), 6),
                   "smear": round(float(np.mean(np.exp(resid))), 6),
                   # 80% prediction interval in log space (residual quantiles on train)
                   "q10": round(float(np.quantile(resid, 0.10)), 6), "q90": round(float(np.quantile(resid, 0.90)), 6)})
    return {"version": 2, "kind": "ridge_per_horizon_log1p", "features": FEATURES,
            "mean": [round(float(v), 6) for v in mean], "std": [round(float(v), 6) for v in std], "horizons": hz}


def flat(model, rows):
    """All (horizon, row) pairs as flat arrays incl. model forecast and 80% interval."""
    out = {k: [] for k in ("h", "fc", "med", "lo", "hi", "now", "cams", "y", "t")}
    for k in range(1, HORIZON + 1):
        X, _, now, cams, y, tt = rows[k]
        if not len(X):
            continue
        m = model["horizons"][k - 1]
        z = ((X - np.array(model["mean"])) / np.array(model["std"])) @ np.array(m["coef"]) + m["intercept"]
        out["h"].append(np.full(len(y), k))
        out["fc"].append(np.maximum(np.exp(z) * m["smear"] - 1, 0))
        out["med"].append(np.maximum(np.expm1(z), 0))
        out["lo"].append(np.maximum(np.expm1(z + m["q10"]), 0))
        out["hi"].append(np.maximum(np.expm1(z + m["q90"]), 0))
        for key, v in (("now", now), ("cams", cams), ("y", y), ("t", tt)):
            out[key].append(v)
    return {k: np.concatenate(v) for k, v in out.items()}


def rules(F, n_hours):
    with_now = np.where(F["h"] <= n_hours, np.maximum(F["fc"], F["now"]), F["fc"])
    return {"model": F["fc"], "model_median": F["med"], "with_now": with_now, "persistence": F["now"], "cams": F["cams"],
            "max_pers_cams": np.maximum(F["now"], F["cams"])}


def dec_metrics(score, y, thr=LIMIT):
    ind, bad = score > thr, y > LIMIT
    return {"indoor_share": float(ind.mean()), "recall": float((ind & bad).sum() / max(bad.sum(), 1)),
            "precision": float((ind & bad).sum() / max(ind.sum(), 1)), "accuracy": float((ind == bad).mean()),
            "missed_dirty_share": float((~ind & bad).mean())}


def recall_at_share(score, y, share):
    thr = np.quantile(score, 1 - share)
    ind, bad = score > thr, y > LIMIT
    return float((ind & bad).sum() / max(bad.sum(), 1))


def boot(fn, days, rng, n=400):
    uniq = np.unique(days)
    idx = {d: np.where(days == d)[0] for d in uniq}
    vals = []
    for _ in range(n):
        pick = np.concatenate([idx[d] for d in rng.choice(uniq, len(uniq))])
        vals.append(fn(pick))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def main():
    rng = np.random.default_rng(SEED)
    h = load()
    tr = build(h, lambda t: t < TRAIN_END, lambda t: t < TRAIN_END, rng)
    te = build(h, lambda t: t >= TEST_START and test_month(t), test_month, rng)
    model = fit(tr)

    # choose N (hours with max(forecast, sensor now)) on TRAIN school hours by balanced accuracy
    Ftr = flat(model, tr)
    s_tr = np.array([school_hour(t) for t in Ftr["t"]])
    best = None
    for n_h in N_CANDIDATES:
        sc = rules(Ftr, n_h)["with_now"][s_tr]
        m = dec_metrics(sc, Ftr["y"][s_tr])
        tnr = 1 - ((sc > LIMIT) & (Ftr["y"][s_tr] <= LIMIT)).sum() / max((Ftr["y"][s_tr] <= LIMIT).sum(), 1)
        bal = (m["recall"] + tnr) / 2
        if best is None or bal > best[0] + 1e-9:
            best = (bal, n_h)
    n_hours = best[1]
    model["school_rule_hours"] = n_hours
    model["decision_threshold"] = LIMIT

    F = flat(model, te)
    y, hh = F["y"], F["h"]
    R = rules(F, n_hours)
    days = np.array([t[:10] for t in F["t"]])

    def mae(v, mask=None):
        mask = np.ones(len(y), bool) if mask is None else mask
        return float(np.abs(v[mask] - y[mask]).mean())
    buckets = {f"{lo}-{hi}": {k: round(mae(R[k], (hh >= lo) & (hh <= hi)), 2) for k in ("model", "persistence", "cams", "max_pers_cams")}
               for lo, hi in BUCKETS}
    peaks = y > 100
    sch = np.array([school_hour(t) for t in F["t"]])
    ys, ds = y[sch], days[sch]
    decisions = {}
    for k, v in R.items():
        sv = v[sch]
        m = dec_metrics(sv, ys)
        m["recall_ci"] = boot(lambda ix, sv=sv: dec_metrics(sv[ix], ys[ix])["recall"], ds, rng)
        m["accuracy_ci"] = boot(lambda ix, sv=sv: dec_metrics(sv[ix], ys[ix])["accuracy"], ds, rng)
        m["recall_at_share"] = {f"{int(s * 100)}": round(recall_at_share(sv, ys, s), 3) for s in SHARES}
        m["recall_at_share_ci"] = {f"{int(s * 100)}": boot(lambda ix, sv=sv, s=s: recall_at_share(sv[ix], ys[ix], s), ds, rng) for s in SHARES}
        decisions[k] = {a: (round(b, 3) if isinstance(b, float) else b) for a, b in m.items()}
    coverage = float(((y >= F["lo"]) & (y <= F["hi"])).mean())
    ratio = float(np.median(y / np.maximum(F["cams"], 1)))
    pk_g = y[peaks]
    pk_c = np.array([h["cams"][h["time"].index(t)] for t in F["t"][peaks]]) if peaks.any() else np.array([1])
    model["metrics"] = {
        "test": "Feb-Mar 2025 + Oct-Nov 2025, 48 h gap after training, OpenAQ 8876",
        "mae": {k: round(mae(R[k]), 2) for k in ("model", "persistence", "cams", "max_pers_cams")},
        "mae_peaks": {k: round(mae(R[k], peaks), 1) for k in ("model", "persistence", "cams", "max_pers_cams")},
        "buckets": buckets,
        "interval80_coverage": round(coverage, 3),
        "school_hours": {"n": int(sch.sum()), "dirty_share": round(float((ys > LIMIT).mean()), 3), "decisions": decisions},
        "school_rule_hours": n_hours,
        "peaks_over_100": {"n": int(peaks.sum()), "ground_median": round(float(np.median(pk_g)), 1), "cams_median": round(float(np.median(pk_c)), 1)},
        "median_ratio_ground_to_cams": round(ratio, 2),
        "cams_noise": "log sigma(h) = 0.10 + 0.20*h/48 (assumption)",
    }
    model["trained_on"] = "OpenAQ 8876 (Almaty), heating hours, targets before 2025-02-01"
    model["generated"] = date.today().isoformat()
    (ROOT / "data" / "forecast_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1) + "\n")

    cases = []
    for k, x in ((1, features(80, 40, -2, -6, 0.8, 20)), (6, features(15, 25, 1, -3, 1.5, 13)),
                 (24, features(150, 60, 4, -10, 0.3, 21)), (48, features(5, 10, -8, 2, 3.5, 14))):
        p, contrib = predict(model, k, x)
        med, lo, hi = interval(model, k, x)
        cases.append({"h": k, "x": x, "p": p, "median": med, "lo": lo, "hi": hi, "contrib": contrib})
    (ROOT / "tests" / "forecast_cases.json").write_text(json.dumps(cases, indent=1) + "\n")
    write_report(model, tr, te)
    print(json.dumps({k: model["metrics"][k] for k in ("mae", "mae_peaks", "interval80_coverage", "school_rule_hours")}, ensure_ascii=False))
    for k, v in decisions.items():
        if k == "with_now":
            continue
        print(f"{k:14s} indoor {v['indoor_share']:.2f} recall {v['recall']:.2f} {v['recall_ci']} acc {v['accuracy']:.2f} rec@40 {v['recall_at_share']['40']}")


def f(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def pct(v):
    return f"{100 * v:.0f}%"


def write_report(model, tr, te):
    m = model["metrics"]
    names = {"model": "Модель, среднее (в приложении)", "with_now": f"Модель + датчик на первые {m['school_rule_hours']} ч (правило школы)", "model_median": "Модель, медиана (для сравнения)",
             "persistence": "«Будет как сейчас»", "cams": "CAMS (с шумом прогноза)", "max_pers_cams": "max(«как сейчас», CAMS)"}
    sh = m["school_hours"]
    L = [
        "# Прогноз PM2.5 на 48 часов: оценка на реальных измерениях",
        "",
        f"Сгенерировано `pipeline/train_forecast.py` ({model['generated']}). Воспроизвести: `python3 pipeline/fetch_ground.py && python3 pipeline/train_forecast.py`.",
        "",
        "## Данные и разбиение",
        "",
        "- Реальный PM2.5: открытый архив OpenAQ на S3, станция `locationid=8876` (Алматы, 43,2529 с. ш., 76,9312 в. д.); провайдер в архиве не указан.",
        "- CAMS: `air-quality-api.open-meteo.com`; погода (T2м, T850, ветер): `historical-forecast-api.open-meteo.com`. Только отопительный сезон.",
        "- **Обучение:** цели до 01.02.2025. **Тест:** точки старта с 03.02.2025 (зазор 48 ч, ни один час не общий), февраль–март и октябрь–ноябрь 2025.",
        f"- **Шум CAMS:** в архиве CAMS близок к анализу, а в приложении это прогноз. Поэтому к признаку CAMS и к бейзлайну CAMS добавлен шум, растущий с горизонтом: {m['cams_noise']}. Архивных прогнозов CAMS за этот период в Open-Meteo нет, величина шума — допущение.",
        "",
        "## Ошибка прогноза (MAE, мкг/м³, все часы теста)",
        "",
        "| Горизонт, ч | Модель | «Как сейчас» | CAMS | max(«как сейчас», CAMS) |",
        "|---|---|---|---|---|",
    ]
    for b, d in m["buckets"].items():
        L.append(f"| {b} | **{f(d['model'])}** | {f(d['persistence'])} | {f(d['cams'])} | {f(d['max_pers_cams'])} |")
    a = m["mae"]
    L.append(f"| **все 1–48** | **{f(a['model'])}** | {f(a['persistence'])} | {f(a['cams'])} | {f(a['max_pers_cams'])} |")
    p = m["mae_peaks"]
    L.append(f"| только факт > 100 | {f(p['model'])} | {f(p['persistence'])} | {f(p['cams'])} | {f(p['max_pers_cams'])} |")
    L += ["", f"80% интервал прогноза (квантили остатков на обучении) накрыл факт в **{pct(m['interval80_coverage'])}** тестовых случаев.", "",
          "## Решение «физкультура на улице или в зале» — только школьные часы",
          "",
          f"Цели 8:00–14:59 в будни, горизонты 1–48 ч: {sh['n']} пар, доля грязных часов (факт > 35,4) {pct(sh['dirty_share'])}. "
          "Правило школы: на ближайшие N часов берём большее из прогноза и текущего датчика (урок, который идёт сейчас или вот-вот начнётся), дальше — только прогноз модели. "
          f"N подбирали на обучении по сбалансированной точности из {N_CANDIDATES}: N = {m['school_rule_hours']}. "
          "Прежняя версия брала большее ко всем 48 часам — завтрашние уроки решались по сегодняшнему датчику; это было неверно, правило исправлено. "
          "В приложении используется среднее прогноза («осторожно»); медиана («сбалансированно») показана для сравнения. Интервалы — бутстрэп целыми днями (95%).",
          "",
          "| Правило | Доля уроков в зале | Поймано грязных часов | Точность | Precision |",
          "|---|---|---|---|---|"]
    for k, nm in names.items():
        d = sh["decisions"][k]
        L.append(f"| {nm} | {pct(d['indoor_share'])} | **{pct(d['recall'])}** ({pct(d['recall_ci'][0])}–{pct(d['recall_ci'][1])}) | "
                 f"{pct(d['accuracy'])} ({pct(d['accuracy_ci'][0])}–{pct(d['accuracy_ci'][1])}) | {pct(d['precision'])} |")
    L += ["", "### Честное сравнение: при одинаковой доле уроков в зале",
          "",
          "У правил разная доля уроков в зале, поэтому «поймано больше» может означать просто «чаще отправляет в зал». "
          "Ниже порог каждого правила сдвинут так, чтобы все отправляли в зал одинаковую долю уроков.",
          "",
          "| Правило | 30% в зале | 40% в зале | 50% в зале |", "|---|---|---|---|"]
    for k, nm in names.items():
        d = sh["decisions"][k]
        cells = [f"{pct(d['recall_at_share'][s])} ({pct(d['recall_at_share_ci'][s][0])}–{pct(d['recall_at_share_ci'][s][1])})" for s in ("30", "40", "50")]
        L.append(f"| {nm} | " + " | ".join(cells) + " |")
    L += ["", "## Как читать честно", "",
          "- Одна станция, один сезон обучения; в приложении модель стартует от дешёвых датчиков.",
          "- Соседние часы автокоррелированы: интервалы считаются бутстрэпом по дням, а не по часам.",
          "- Погодные признаки в обучении из архива прогнозов, а шум CAMS — допущение; на живых данных ошибка может быть выше.",
          "- В сильный смог модель сглаживает пики; поэтому в ближайшие часы школа опирается и на текущий датчик.",
          "- Малая выборка на живых датчиках — `evals/small_sample.md`.", ""]
    (ROOT / "evals" / "forecast_report.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
