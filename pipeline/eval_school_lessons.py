"""One child-facing metric: school lessons that would go outdoors in dirty air (CAMS vs Taza Tynys).

Same data, split, CAMS noise and model as pipeline/train_forecast.py (same seed and RNG order).
Lesson = weekday target hour 8:00-14:59 in the test period; decision made 24 h before (forecast horizon 24).
'Outdoors' = rule says the value is at or below the threshold 35.4; 'dirty' = measured PM2.5 > 35.4.
Appends/replaces the section in evals/forecast_report.md (rerun this after train_forecast.py, which rewrites the report).
Usage: python3 pipeline/eval_school_lessons.py
"""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import train_forecast as T  # noqa: E402

ROOT = T.ROOT
MARK = "## Метрика для детей: грязные уроки, которые ушли бы на улицу"
LEAD = 24


def main():
    rng = np.random.default_rng(T.SEED)
    h = T.load()
    tr = T.build(h, lambda t: t < T.TRAIN_END, lambda t: t < T.TRAIN_END, rng)
    te = T.build(h, lambda t: t >= T.TEST_START and T.test_month(t), T.test_month, rng)
    model = T.fit(tr)
    model["school_rule_hours"] = json.loads((ROOT / "data" / "forecast_model.json").read_text())["school_rule_hours"]
    F = T.flat(model, te)
    R = T.rules(F, model["school_rule_hours"])
    sch = np.array([T.school_hour(t) for t in F["t"]]) & (F["h"] == LEAD)
    y = F["y"][sch]
    dirty = y > T.LIMIT
    K = int(dirty.sum())
    out = {}
    for k in ("cams", "model", "persistence"):
        out[k] = int((dirty & (R[k][sch] <= T.LIMIT)).sum())
    n = int(sch.sum())
    indoor = {k: float((R[k][sch] > T.LIMIT).mean()) for k in out}
    # equal indoor share (model's share) for honesty
    share = indoor["model"]
    thr = np.quantile(R["cams"][sch], 1 - share)
    out["cams_equal_share"] = int((dirty & (R["cams"][sch] <= thr)).sum())
    print(json.dumps({"lessons": n, "K": K, "outdoors_dirty": out, "indoor_share": indoor}, ensure_ascii=False))
    (ROOT / "evals" / "school_lessons.json").write_text(json.dumps(
        {"lead_hours": LEAD, "lessons": n, "dirty": K, "outdoors_dirty": out, "indoor_share": {k: round(v, 3) for k, v in indoor.items()}},
        ensure_ascii=False, indent=1) + "\n")
    p = lambda v: f"{100 * v:.0f}%"  # noqa: E731
    sec = [MARK, "",
           f"Те же данные, тот же тест и тот же шум CAMS, что выше; считает `pipeline/eval_school_lessons.py`. Урок = будний час 8:00–14:59 тестового периода ({n} уроков), решение принято за {LEAD} ч до урока. "
           f"Грязный урок — факт PM2.5 > 35,4 мкг/м³ (таких K = **{K}**). «Вышел бы на улицу» — правило показывает значение не выше порога.", "",
           "| Правило | Грязных уроков ушло бы на улицу (из " + str(K) + ") | Доля уроков в зале |", "|---|---|---|",
           f"| CAMS | **{out['cams']}** | {p(indoor['cams'])} |",
           f"| «Будет как сейчас» | {out['persistence']} | {p(indoor['persistence'])} |",
           f"| Таза Тыныс (модель, как в приложении) | **{out['model']}** | {p(indoor['model'])} |",
           f"| CAMS, порог сдвинут до той же доли в зале ({p(share)}) | {out['cams_equal_share']} | {p(share)} |", "",
           "Оговорка: Таза Тыныс отправляет в зал заметно больше уроков, чем CAMS при том же пороге (последняя строка показывает CAMS при равной доле — разрыв там меньше). "
           "Одна станция, один сезон обучения, шум CAMS — допущение.", ""]
    rp = ROOT / "evals" / "forecast_report.md"
    txt = rp.read_text()
    if MARK in txt:
        txt = txt[:txt.index(MARK)].rstrip() + "\n"
    rp.write_text(txt.rstrip() + "\n\n" + "\n".join(sec))


if __name__ == "__main__":
    main()
