"""Train the "weather trap" model: P(CAMS PM2.5 > 45 ug/m3 in this hour).

Logistic regression on numpy (no sklearn). Train on one winter, test on the
other (both directions), compare with baselines, write data/model.json and
evals/trap_report.md.

Usage: python3 pipeline/fetch_history.py && python3 pipeline/train_trap.py
"""
import json
import math
import pathlib
import sys
from datetime import date

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trap_features import FEATURES, build_features, predict  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
HIST = ROOT / "pipeline" / "history"
TARGET = 45.0          # ug/m3, CAMS PM2.5, roughly the top 20% of winter hours
L2 = 1e-3
SEED = 7
WEATHER_IDX = [0, 1, 2]
HOUR_IDX = [3, 4, 5, 6]


def load(winter):
    d = json.loads((HIST / f"{winter}.json").read_text())
    h = d["hourly"]
    n = len(h["time"])
    X = np.array([build_features(h["time"], h["wind"], h["temp"], h["blh"], i) for i in range(n)])
    pm = np.array(h["pm2_5"], dtype=float)
    hours = np.array([int(t[11:13]) for t in h["time"]])
    days = np.array([t[:10] for t in h["time"]])
    return {"X": X, "pm": pm, "y": (pm > TARGET).astype(float), "hour": hours, "day": days, "raw": h}


def fit(X, y, l2=L2, iters=4000, lr=0.5):
    """Standardize, then full-batch gradient descent on L2-regularised log loss."""
    mean, std = X.mean(0), X.std(0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    w = np.zeros(Z.shape[1])
    b = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return {"mean": mean, "std": std, "coef": w, "intercept": b}


def score(m, X):
    Z = (X - m["mean"]) / m["std"]
    return 1 / (1 + np.exp(-(Z @ m["coef"] + m["intercept"])))


def auc(y, s):
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, weights=ranks)
    ranks = (sums / cnt)[inv]
    n1 = y.sum()
    n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def within_hour_auc(y, s, hours):
    vals = []
    for h in range(24):
        k = hours == h
        if 0 < y[k].sum() < k.sum():
            vals.append(auc(y[k], s[k]))
    return float(np.mean(vals))


def best_threshold(y, s):
    """Threshold maximising F1 on the TRAIN winter."""
    best = (0.0, 0.5)
    for t in np.linspace(0.05, 0.95, 91):
        pred = s >= t
        tp = (pred & (y == 1)).sum()
        if tp == 0:
            continue
        p = tp / pred.sum()
        r = tp / (y == 1).sum()
        f1 = 2 * p * r / (p + r)
        if f1 > best[0]:
            best = (f1, float(t))
    return best[1]


def pr(y, s, t):
    pred = s >= t
    tp = float((pred & (y == 1)).sum())
    return {
        "precision": tp / max(pred.sum(), 1),
        "recall": tp / max((y == 1).sum(), 1),
        "flagged_share": float(pred.mean()),
    }


def day_block_ci(y, s, days, rng, n=500):
    """95% CI of AUC with a bootstrap over whole days (keeps hour-to-hour autocorrelation)."""
    uniq = np.unique(days)
    idx_by_day = {d: np.where(days == d)[0] for d in uniq}
    vals = []
    for _ in range(n):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([idx_by_day[d] for d in pick])
        vals.append(auc(y[idx], s[idx]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def lag1(y):
    return float(np.corrcoef(y[:-1], y[1:])[0, 1])


def evaluate(train, test, cols, rng):
    m = fit(train["X"][:, cols], train["y"])
    s_tr = score(m, train["X"][:, cols])
    s_te = score(m, test["X"][:, cols])
    t = best_threshold(train["y"], s_tr)
    out = {
        "auc": auc(test["y"], s_te),
        "auc_ci95_by_day": day_block_ci(test["y"], s_te, test["day"], rng),
        "within_hour_auc": within_hour_auc(test["y"], s_te, test["hour"]),
        "threshold": t,
    }
    out.update(pr(test["y"], s_te, t))
    return out, m


def main():
    rng = np.random.default_rng(SEED)
    w1, w2 = "2024-25", "2025-26"
    A, B = load(w1), load(w2)
    all_cols = list(range(len(FEATURES)))
    variants = {
        "model": all_cols,
        "temp_only": [1],
        "hour_only": HOUR_IDX,
        "weather_only": WEATHER_IDX,
    }
    results = {}
    for split, (tr, te) in {f"train {w1} -> test {w2}": (A, B), f"train {w2} -> test {w1}": (B, A)}.items():
        results[split] = {}
        for name, cols in variants.items():
            results[split][name] = evaluate(tr, te, cols, rng)[0]

    # Final model: both winters together; out-of-sample metrics come from the splits above.
    X = np.vstack([A["X"], B["X"]])
    y = np.concatenate([A["y"], B["y"]])
    m = fit(X, y)
    thr = best_threshold(y, score(m, X))
    primary = results[f"train {w1} -> test {w2}"]["model"]

    model = {
        "version": 1,
        "kind": "logistic_regression",
        "features": FEATURES,
        "mean": [round(float(v), 6) for v in m["mean"]],
        "std": [round(float(v), 6) for v in m["std"]],
        "coef": [round(float(v), 6) for v in m["coef"]],
        "intercept": round(float(m["intercept"]), 6),
        "threshold": round(thr, 3),
        "target": {"variable": "pm2_5", "source": "CAMS via Open-Meteo", "gt": TARGET, "unit": "ug/m3"},
        "trained_on": f"Almaty 43.24N 76.89E, Nov-Feb {w1} and {w2}, {len(y)} hours",
        "generated": date.today().isoformat(),
        "base_rate": round(float(y.mean()), 4),
        "metrics": {
            "split": f"train {w1}, test {w2}",
            "auc": round(primary["auc"], 3),
            "auc_ci95_by_day": [round(v, 3) for v in primary["auc_ci95_by_day"]],
            "within_hour_auc": round(primary["within_hour_auc"], 3),
            "precision": round(primary["precision"], 3),
            "recall": round(primary["recall"], 3),
            "baseline_temp_only_auc": round(results[f"train {w1} -> test {w2}"]["temp_only"]["auc"], 3),
            "baseline_hour_only_auc": round(results[f"train {w1} -> test {w2}"]["hour_only"]["auc"], 3),
        },
        "note": "Target is CAMS reanalysis/forecast PM2.5 on a ~40 km grid, not ground measurements.",
    }
    (ROOT / "data" / "model.json").write_text(json.dumps(model, ensure_ascii=False, indent=1) + "\n")

    write_cases(model, B)
    write_report(model, results, A, B, w1, w2)
    print(json.dumps(model["metrics"], indent=1))


def write_cases(model, W):
    """Fixed inputs + expected outputs for the JS twin (tests/test_model.py)."""
    h = W["raw"]
    start = 24 * 40  # a mid-December stretch
    n = 48
    series = {k: h[k][start:start + n] for k in ("time", "wind", "temp", "blh")}
    idx = [0, 5, 11, 23, 30, 47]
    cases = []
    for i in idx:
        x = build_features(series["time"], series["wind"], series["temp"], series["blh"], i)
        p, contrib = predict(model, x)
        cases.append({"i": i, "x": x, "p": p, "contrib": contrib})
    vectors = []
    for x in ([1.0, -10.0, math.log(60), 0, 1, 0, 1, 0], [4.0, 2.0, math.log(900), 1, 0, 0, -1, 1],
              [0.3, -15.0, math.log(20), -1, 0, 0, -1, 0]):
        p, contrib = predict(model, x)
        vectors.append({"x": x, "p": p, "contrib": contrib})
    out = {"series": series, "series_cases": cases, "vector_cases": vectors}
    (ROOT / "tests" / "model_cases.json").write_text(json.dumps(out, indent=1) + "\n")


def f3(v):
    return f"{v:.3f}".replace(".", ",")


def write_report(model, results, A, B, w1, w2):
    lines = [
        "# Модель «погодной ловушки»: отчёт об оценке",
        "",
        f"Сгенерировано `pipeline/train_trap.py` ({model['generated']}). Все цифры ниже воспроизводятся командой `python3 pipeline/train_trap.py`.",
        "",
        "## Что предсказываем",
        "",
        f"Вероятность того, что в данный час PM2.5 по модели CAMS в точке Алматы (43,24 с. ш., 76,89 в. д.) будет выше **{int(TARGET)} мкг/м³**.",
        "",
        "**Почему 45, а не 55.** CAMS (сетка около 40 км) сильно сглаживает смог в котловине: зимой медиана PM2.5 по CAMS около 30 мкг/м³, 90-й перцентиль около 52, максимум около 100–110, тогда как реальные городские датчики в морозные вечера показывают 100–300. "
        f"Порог 55 даёт только {100*float((A['pm']>55).mean()):.0f}% и {100*float((B['pm']>55).mean()):.0f}% часов (слишком редкий и почти целиком вечерний класс). "
        f"Порог 45 — это верхние {100*float((A['pm']>45).mean()):.0f}% / {100*float((B['pm']>45).mean()):.0f}% зимних часов CAMS, то есть «худшая пятая часть» по шкале самой модели. "
        "Он выше промежуточной цели ВОЗ IT-3 для суток (37,5) и близок к IT-2 (50). Это относительный таргет: модель учится узнавать погоду, при которой CAMS даёт свои худшие часы, а не абсолютный уровень, который вдохнёт человек.",
        "",
        "**Честно:** таргет — реанализ и прогноз CAMS, а не измерения. Модель воспроизводит логику CAMS, ошибки CAMS она наследует.",
        "",
        "## Данные",
        "",
        "| Зима | Часов | Медиана PM2.5 | p90 | Доля часов > 45 | Доля > 55 |",
        "|---|---|---|---|---|---|",
    ]
    for w, D in ((w1, A), (w2, B)):
        lines.append(f"| {w} (1 ноя – 28 фев) | {len(D['pm'])} | {np.median(D['pm']):.1f} | {np.percentile(D['pm'],90):.1f} | {100*D['y'].mean():.1f}% | {100*(D['pm']>55).mean():.1f}% |")
    lines += [
        "",
        "- PM2.5: `air-quality-api.open-meteo.com` (CAMS).",
        "- Погода: `historical-forecast-api.open-meteo.com` — архив тех же моделей, что отдаёт живой прогноз (`api.open-meteo.com`), поэтому признаки на обучении и в приложении одного происхождения.",
        "- **Отклонение от плана:** планировали зимы 2023/24 и 2024/25, но `boundary_layer_height` в архиве Open-Meteo есть только примерно с осени 2024 года (в ERA5-архиве его нет совсем, в архиве прогнозов за январь 2024 — пустые значения). Поэтому взяты зимы **2024/25 и 2025/26**.",
        "",
        "## Признаки",
        "",
        "| Признак | Смысл |",
        "|---|---|",
        "| `wind_12h` | средний ветер на 10 м за последние 12 ч, м/с |",
        "| `temp_24h` | средняя температура за последние 24 ч, °C (холодные сутки — больше топят) |",
        "| `blh_12h` | среднее ln(высота слоя перемешивания + 10 м) за 12 ч («крышка» над городом) |",
        "| `hour_sin`, `hour_cos`, `hour_sin2`, `hour_cos2` | суточный цикл (две гармоники: утренний и вечерний пик) |",
        "| `weekend` | суббота или воскресенье |",
        "",
        "Скользящие средние вместо мгновенных значений выбраны на эксперименте: они дают большую точность и все погодные коэффициенты получают физически осмысленный знак (меньше ветра, холоднее, ниже слой → выше риск). Логистическая регрессия на numpy (градиентный спуск, L2 = 0,001), признаки стандартизованы.",
        "",
        "## Результаты (обучение на одной зиме, тест на другой)",
        "",
    ]
    names = {"model": "**Модель (все признаки)**", "temp_only": "Бейзлайн: только температура", "hour_only": "Бейзлайн: только час суток", "weather_only": "Только погода (без часа)"}
    for split, res in results.items():
        lines += [f"### {split}", "", "| Вариант | ROC-AUC | 95% ДИ (бутстрэп по дням) | AUC внутри часа | Precision | Recall | Порог | Доля часов с тревогой |", "|---|---|---|---|---|---|---|---|"]
        for k, r in res.items():
            lines.append(f"| {names[k]} | {f3(r['auc'])} | {f3(r['auc_ci95_by_day'][0])}–{f3(r['auc_ci95_by_day'][1])} | {f3(r['within_hour_auc'])} | {f3(r['precision'])} | {f3(r['recall'])} | {f3(r['threshold'])} | {100*r['flagged_share']:.0f}% |")
        lines.append("")
    feat_lines = [f"| `{f}` | {c:+.2f} |".replace(".", ",") for f, c in zip(model["features"], model["coef"])]
    lines += [
        "Порог вероятности подбирается по F1 **на обучающей** зиме и без изменений применяется к тестовой.",
        "",
        "**AUC внутри часа** — среднее ROC-AUC, посчитанное отдельно для каждого часа суток. У бейзлайна «только час» он равен 0,5 по построению. Эта метрика показывает, насколько погода различает «плохой вечер» и «обычный вечер» в одно и то же время.",
        "",
        "## Как читать честно",
        "",
        "- Бо́льшая часть общего AUC приходится на **суточный цикл**: бейзлайн «только час» уже сильный (вечером CAMS почти всегда грязнее). Погода добавляет немного: прирост общего AUC +0,02–0,03, AUC внутри часа 0,58–0,65. Модель помогает отличить «ловушку» от обычного вечера ; в прямом разбиении она точнее бейзлайна «только час» (precision 0,51 против 0,37 при вдвое меньшей доле тревог), в обратном — на уровне бейзлайна по precision при более высоком recall. Это не прогноз концентраций.",
        "- Бейзлайн «только температура» слабый (общий AUC 0,59–0,63): одного мороза мало, важны время суток, штиль и низкий слой. Внутри часа температура различает почти так же, как вся погода вместе — честно: основная погодная информация в CAMS-таргете идёт от холода и «крышки».",
        f"- **Автокорреляция.** Соседние часы почти одинаковы (автокорреляция таргета с лагом 1 ч: {lag1(A['y']):.2f} и {lag1(B['y']):.2f}), поэтому 2880 часов — это не 2880 независимых наблюдений. Доверительные интервалы считаем бутстрэпом **целыми сутками**, а не часами; эффективный объём выборки ближе к числу суток (120 на зиму), чем к числу часов. Обучение и тест разнесены на разные зимы, утечки соседних часов между ними нет.",
        "- Обе зимы короткие, а погодные режимы между годами отличаются; метрики на одной паре зим нельзя считать окончательными.",
        "",
        "## Модель в приложении",
        "",
        f"В `data/model.json` лежит модель, обученная на **обеих** зимах ({model['trained_on']}); метрики в файле — из прямого разбиения «обучение {w1} → тест {w2}». Порог тревоги {model['threshold']:.2f}, базовая частота класса {100*model['base_rate']:.1f}%.".replace(".", ",", 1),
        "",
        "| Признак | Коэффициент (на 1 стандартное отклонение) |",
        "|---|---|",
        *feat_lines,
        "",
        "Предсказание считается на устройстве в `js/trap.js`; формула продублирована в `pipeline/trap_features.py`, совпадение проверяет `tests/test_model.py`.",
        "",
        "## Проверка по реальным датчикам",
        "",
        "См. `evals/sensor_check.md`: архива реальных датчиков без регистрации за прошлые зимы найти не удалось, поэтому там только сверка CAMS с публичными датчиками AirKaz и sensor.community за последние сутки.",
        "",
    ]
    (ROOT / "evals" / "trap_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
