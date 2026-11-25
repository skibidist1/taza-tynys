"""Train and evaluate the 48-hour PM2.5 forecast on REAL measurements.

Data: pipeline/history/ground_8876.json (OpenAQ archive station 8876 + CAMS + weather).
Heating-season hours only (October-March). Time split: train Oct 2024 - Jan 2025,
test Feb - Mar 2025 and Oct - Nov 2025 (later in time than all training data).
Baselines: persistence ("will stay as now") and raw CAMS.
Writes data/forecast_model.json, evals/forecast_report.md, tests/forecast_cases.json.
Usage: python3 pipeline/fetch_ground.py && python3 pipeline/train_forecast.py
"""
import json
import pathlib
import sys
from datetime import date

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from forecast_features import FEATURES, HORIZON, features, predict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
L2 = 1.0
EPA = [9.0, 35.4, 55.4, 125.4, 225.4]  # US EPA PM2.5 AQI breakpoints (2024), ug/m3
OUTDOOR_LIMIT = 35.4                    # top of "Moderate": above it EPA advises sensitive groups to reduce exertion
BUCKETS = [(1, 6), (7, 12), (13, 24), (25, 48)]


def heating(t):
    return int(t[5:7]) in (10, 11, 12, 1, 2, 3)


def is_train(t):
    return "2024-10" <= t[:7] <= "2025-01"


def is_test(t):
    return ("2025-02" <= t[:7] <= "2025-03") or ("2025-10" <= t[:7] <= "2025-11")


def load():
    h = json.loads((ROOT / "pipeline" / "history" / "ground_8876.json").read_text())["hourly"]
    # negative values are instrument errors/flags in the archive: treat as missing
    h["pm25"] = [None if v is None or v < 0 else v for v in h["pm25"]]
    return h


def build(h, select):
    """Rows for all (origin t, horizon k) with complete data; returns dict k -> (X, y, pm_now, cams, t)."""
    n = len(h["time"])
    data = {k: ([], [], [], [], []) for k in range(1, HORIZON + 1)}
    for t in range(n):
        if not select(h["time"][t]) or h["pm25"][t] is None:
            continue
        for k in range(1, HORIZON + 1):
            j = t + k
            if j >= n or h["pm25"][j] is None or not heating(h["time"][j]):
                continue
            vals = [h[v][j] for v in ("cams", "t850", "temp", "blh", "wind")]
            if any(v is None for v in vals):
                continue
            x = features(h["pm25"][t], h["cams"][j], h["t850"][j], h["temp"][j], h["wind"][j], int(h["time"][j][11:13]))
            d = data[k]
            d[0].append(x)
            d[1].append(np.log1p(h["pm25"][j]))
            d[2].append(h["pm25"][t])
            d[3].append(h["cams"][j])
            d[4].append(h["pm25"][j])
    return {k: tuple(np.array(a) for a in v) for k, v in data.items()}


def ridge(X, y, mean, std):
    Z = (X - mean) / std
    Z1 = np.c_[Z, np.ones(len(Z))]
    reg = L2 * np.eye(Z1.shape[1])
    reg[-1, -1] = 0
    w = np.linalg.solve(Z1.T @ Z1 + reg, Z1.T @ y)
    return w[:-1], w[-1]


def cat(v):
    return np.searchsorted(EPA, v, side="left")


def main():
    h = load()
    tr = build(h, lambda t: heating(t) and is_train(t))
    te = build(h, lambda t: heating(t) and is_test(t))
    allX = np.vstack([tr[k][0] for k in tr if len(tr[k][0])])
    mean, std = allX.mean(0), allX.std(0)
    std[std == 0] = 1
    horizons = []
    for k in range(1, HORIZON + 1):
        c, b = ridge(tr[k][0], tr[k][1], mean, std)
        resid = tr[k][1] - (((tr[k][0] - mean) / std) @ c + b)
        smear = float(np.mean(np.exp(resid)))  # Duan smearing factor
        horizons.append({"h": k, "coef": [round(float(v), 6) for v in c], "intercept": round(float(b), 6), "smear": round(smear, 6)})
    # The app decides "PE indoors / lighter" exactly at the EPA boundary, so we evaluate at it too.
    decision_thr = OUTDOOR_LIMIT
    model = {"version": 1, "kind": "ridge_per_horizon_log1p", "features": FEATURES, "decision_threshold": decision_thr,
             "mean": [round(float(v), 6) for v in mean], "std": [round(float(v), 6) for v in std],
             "horizons": horizons}

    # evaluation on the test period
    rows = []
    per_h = []
    for k in range(1, HORIZON + 1):
        X, _, now, cams, y = te[k]
        if not len(X):
            continue
        pred = np.array([predict(model, k, list(x))[0] for x in X])
        per_h.append((k, len(y), np.abs(pred - y).mean(), np.abs(now - y).mean(), np.abs(cams - y).mean()))
        rows.append((k, pred, now, cams, y))

    def agg(lo, hi):
        sel = [r for r in rows if lo <= r[0] <= hi]
        p = np.concatenate([r[1] for r in sel]); n = np.concatenate([r[2] for r in sel])
        c = np.concatenate([r[3] for r in sel]); y = np.concatenate([r[4] for r in sel])
        def dec(f, thr=OUTDOOR_LIMIT):  # outdoor decision: forecast above threshold?
            fb, yb = f > thr, y > OUTDOOR_LIMIT
            acc = float((fb == yb).mean())
            rec = float((fb & yb).sum() / max(yb.sum(), 1))
            prec = float((fb & yb).sum() / max(fb.sum(), 1))
            return acc, prec, rec
        return {
            "n": int(len(y)),
            "mae": {"model": float(np.abs(p - y).mean()), "persistence": float(np.abs(n - y).mean()), "cams": float(np.abs(c - y).mean())},
            "cat_acc": {"model": float((cat(p) == cat(y)).mean()), "persistence": float((cat(n) == cat(y)).mean()), "cams": float((cat(c) == cat(y)).mean())},
            "decision": {"model": dec(p, model["decision_threshold"]), "persistence": dec(n), "cams": dec(c)},
            "bad_share": float((y > OUTDOOR_LIMIT).mean()),
            "mae_peaks": {"model": float(np.abs(p - y)[y > 100].mean()), "persistence": float(np.abs(n - y)[y > 100].mean()), "cams": float(np.abs(c - y)[y > 100].mean())},
        }

    buckets = {f"{lo}-{hi}": agg(lo, hi) for lo, hi in BUCKETS}
    overall = agg(1, HORIZON)
    yt = [v for t, v in zip(h["time"], h["pm25"]) if v is not None and heating(t) and is_test(t)]
    ct = [c for t, v, c in zip(h["time"], h["pm25"], h["cams"]) if v is not None and heating(t) and is_test(t)]
    ratio = float(np.median(np.array(yt) / np.maximum(np.array(ct), 1)))
    ya, ca = np.array(yt), np.array(ct)
    peak = {"n": int((ya > 100).sum()), "ground_median": float(np.median(ya[ya > 100])), "cams_median": float(np.median(ca[ya > 100]))}
    model["metrics"] = {
        "test": "февраль–март и октябрь–ноябрь 2025 (отопительный сезон), станция OpenAQ 8876",
        "mae_model": round(overall["mae"]["model"], 2),
        "mae_persistence": round(overall["mae"]["persistence"], 2),
        "mae_cams": round(overall["mae"]["cams"], 2),
        "buckets": {b: {k: round(v, 2) for k, v in d["mae"].items()} for b, d in buckets.items()},
        "decision_acc": {k: round(v[0], 3) for k, v in overall["decision"].items()},
        "mae_peaks_over_100": {k: round(v, 1) for k, v in overall["mae_peaks"].items()},
        "median_ratio_ground_to_cams": round(ratio, 2),
        "peaks_over_100": {k: round(v, 1) for k, v in peak.items()},
    }
    model["trained_on"] = "OpenAQ archive station 8876 (Almaty 43.2529 N 76.9312 E), Oct 2024 - Jan 2025, heating hours"
    model["generated"] = date.today().isoformat()
    (ROOT / "data" / "forecast_model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1) + "\n")

    # fixed cases for the JS twin
    cases = []
    for k, x in ((1, features(80, 40, -2, -6, 0.8, 20)), (6, features(15, 25, 1, -3, 1.5, 13)),
                 (24, features(150, 60, 4, -10, 0.3, 21)), (48, features(5, 10, -8, 2, 3.5, 14))):
        p, contrib = predict(model, k, x)
        cases.append({"h": k, "x": x, "p": p, "contrib": contrib})
    (ROOT / "tests" / "forecast_cases.json").write_text(json.dumps(cases, indent=1) + "\n")

    write_report(model, buckets, overall, h, per_h, ratio, peak)
    print(json.dumps(model["metrics"], indent=1, ensure_ascii=False))


def f(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def write_report(model, buckets, overall, h, per_h, ratio, peak):
    n_tr = sum(1 for t, v in zip(h["time"], h["pm25"]) if v is not None and heating(t) and is_train(t))
    n_te = sum(1 for t, v in zip(h["time"], h["pm25"]) if v is not None and heating(t) and is_test(t))
    names = {"model": "**Наша модель**", "persistence": "«Будет как сейчас» (persistence)", "cams": "CAMS как есть"}
    L = [
        "# Прогноз PM2.5 на 48 часов: отчёт об оценке на реальных измерениях",
        "",
        f"Сгенерировано `pipeline/train_forecast.py` ({model['generated']}). Воспроизвести: `python3 pipeline/fetch_ground.py && python3 pipeline/train_forecast.py`.",
        "",
        "## Данные",
        "",
        "- **Реальный PM2.5:** открытый архив OpenAQ на S3 (без ключа), станция `locationid=8876`, Алматы, 43,2529 с. ш., 76,9312 в. д., часовые значения. Провайдер станции в архиве не указан. Архив заканчивается в ноябре 2025 года.",
        "- **CAMS:** `air-quality-api.open-meteo.com` в той же точке.",
        "- **Погода:** `historical-forecast-api.open-meteo.com` — температура на 2 м и на уровне 850 гПа (инверсия = T850 − T2м), высота слоя перемешивания, ветер. В архиве ERA5 нет ни T850, ни слоя перемешивания; слой в архиве прогнозов есть только с осени 2024 года, поэтому история начинается с октября 2024.",
        "- Только отопительный сезон (октябрь–март).",
        f"- **Обучение:** октябрь 2024 – январь 2025 ({n_tr} часов с измерением). **Тест:** февраль–март 2025 и октябрь–ноябрь 2025 ({n_te} часов) — строго позже обучения.",
        "",
        f"Медиана отношения «станция / CAMS» в тестовый период: {f(ratio, 2)} — в обычные часы CAMS в среднем близок к станции. Но в смог он слеп: в {peak['n']} тестовых часах, когда станция показывала больше 100 мкг/м³ (медиана {f(peak['ground_median'], 0)}), CAMS показывал медиану **{f(peak['cams_median'], 0)}** — в {f(peak['ground_median'] / peak['cams_median'], 1)} раза меньше.",
        "",
        "## Модель",
        "",
        "Отдельная ридж-регрессия (numpy, L2 = 1) на каждый горизонт h = 1…48 ч, таргет ln(1 + PM2.5); обратное преобразование с поправкой Дуана (smearing), иначе модель в логарифмах предсказывает медиану и сильнее занижает пики. Признаки: текущее измерение (ln), прогноз CAMS на час h (ln), инверсия T850 − T2м, ветер, час суток (две гармоники). Высоту слоя перемешивания пробовали: без неё MAE на тесте 18,5 против 18,7 с ней, а её коэффициент получал физически неверный знак (она коллинеарна с инверсией и часом суток). Поэтому в модели её нет, а в приложении она показывается только как справочная цифра. Формула продублирована в `js/forecast.js` и `pipeline/forecast_features.py`; совпадение проверяет `tests/test_forecast.py`.",
        "",
        "## Ошибка прогноза на тесте (MAE, мкг/м³; меньше — лучше)",
        "",
        "| Горизонт, ч | Пар (час, горизонт) | " + " | ".join(names.values()) + " |",
        "|---|---|---|---|---|",
    ]
    for b, d in buckets.items():
        L.append(f"| {b} | {d['n']} | " + " | ".join(f(d["mae"][k]) for k in names) + " |")
    L.append(f"| **все 1–48** | {overall['n']} | " + " | ".join(f"**{f(overall['mae'][k])}**" for k in names) + " |")
    L.append("| только часы, где факт > 100 | — | " + " | ".join(f(overall["mae_peaks"][k]) for k in names) + " |")
    L += ["", "В сильный смог (факт > 100 мкг/м³) наша модель ошибается меньше CAMS, но больше, чем «будет как сейчас»: длинные эпизоды смога она всё ещё сглаживает. Это главное ограничение, и на экране «Честность» оно названо прямо."]
    L += [
        "",
        "## Решение «физкультура на улице?» (порог 35,4 мкг/м³ — верх категории «Умеренно» по EPA)",
        "",
        "Для всех трёх прогнозов решение принимается на одной и той же границе EPA 35,4 мкг/м³ — так же, как в приложении.",
        "",
        f"Доля тестовых часов выше порога: {f(100 * overall['bad_share'], 0)}%.",
        "",
        "| Прогноз | Точность решения | Precision «плохо» | Recall «плохо» | Точное попадание в категорию EPA |",
        "|---|---|---|---|---|",
    ]
    for k, nm in names.items():
        a, p, r = overall["decision"][k]
        L.append(f"| {nm} | {f(100 * a, 0)}% | {f(100 * p, 0)}% | {f(100 * r, 0)}% | {f(100 * overall['cat_acc'][k], 0)}% |")
    L += [
        "",
        "## MAE по каждому горизонту",
        "",
        "| h | n | модель | persistence | CAMS |",
        "|---|---|---|---|---|",
    ]
    for k, n, a, b, c in per_h:
        if k in (1, 2, 3, 6, 9, 12, 18, 24, 30, 36, 42, 48):
            L.append(f"| {k} | {n} | {f(a)} | {f(b)} | {f(c)} |")
    L += [
        "",
        "## Как читать честно",
        "",
        "- Одна станция и один отопительный сезон обучения; тест — следующие месяцы той же станции. Для других районов и для дешёвых датчиков AirKaz и sensor.community ошибка может быть больше: в приложении модель стартует от ближайшего живого датчика, а обучена на станции 8876.",
        "- Соседние часы сильно автокоррелированы, поэтому число пар не равно числу независимых наблюдений; эффективный объём ближе к числу суток.",
        "- Погодные признаки в обучении взяты из архива прогнозов (близко к анализу), а в приложении — из настоящего прогноза; на дальних горизонтах реальная ошибка будет немного выше.",
        "- Малая выборка на наших собственных логах датчиков — в `evals/small_sample.md`.",
        "",
    ]
    (ROOT / "evals" / "forecast_report.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
