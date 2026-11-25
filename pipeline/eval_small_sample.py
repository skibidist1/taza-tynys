"""Small-sample check of the forecast on today's real low-cost sensors (AirKaz) and our own log.

Sample A: the last ~24 hourly PM2.5 rows of each healthy AirKaz sensor (from data/sensors_snapshot.json).
          Every hour is used as an origin, every later hour as a target (h <= 23).
Sample B: the team's own log ../../data-logs/airkaz/*.jsonl (every 10 min: all AirKaz sensors + CAMS).
          Used when it spans at least 2 hours.
CAMS and weather for the same hours come from Open-Meteo (past_days=2) at each sensor's point.
Writes evals/small_sample.md and data/small_sample.json. This is a SMALL sample: one day, few sensors.
Usage: python3 pipeline/make_sensors_snapshot.py && python3 pipeline/eval_small_sample.py
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG_DIR = ROOT.parent.parent / "data-logs" / "airkaz"
sys.path.insert(0, str(ROOT / "pipeline"))
from forecast_features import features, predict  # noqa: E402


def om(lat, lon):
    common = {"latitude": lat, "longitude": lon, "timezone": "Asia/Almaty", "past_days": 2, "forecast_days": 1}
    aq = json.load(urllib.request.urlopen("https://air-quality-api.open-meteo.com/v1/air-quality?" + urllib.parse.urlencode({**common, "hourly": "pm2_5"}), timeout=60))
    wx = json.load(urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
        {**common, "hourly": "temperature_2m,temperature_850hPa,wind_speed_10m", "wind_speed_unit": "ms"}), timeout=60))
    a = dict(zip(aq["hourly"]["time"], aq["hourly"]["pm2_5"]))
    w = {t: (wx["hourly"]["temperature_2m"][i], wx["hourly"]["temperature_850hPa"][i], wx["hourly"]["wind_speed_10m"][i]) for i, t in enumerate(wx["hourly"]["time"])}
    return a, w


def series_from_log():
    """Per-sensor hourly means from the 10-minute log (first row per sensor id = its current value)."""
    out = {}
    n_lines = 0
    for p in sorted(LOG_DIR.glob("*.jsonl")) if LOG_DIR.exists() else []:
        for line in p.read_text().splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_lines += 1
            seen = set()
            hour = d["ts"][:13] + ":00"
            for s in d.get("sensors", []):
                if s["id"] in seen or s.get("pm25") in (None, ""):
                    continue
                seen.add(s["id"])
                if datetime.fromisoformat(d["ts"]) - datetime.strptime(s["date"], "%Y-%m-%d %H:%M:%S") > timedelta(hours=3):
                    continue
                key = (s["id"], s["name"], float(s["lat"]), float(s["lng"]))
                out.setdefault(key, {}).setdefault(hour, []).append(float(s["pm25"]))
    series = {k: {h: sum(v) / len(v) for h, v in hs.items()} for k, hs in out.items()}
    return series, n_lines


def evaluate(name, lat, lon, hist, model):
    a, w = om(lat, lon)
    times = sorted(hist)
    errs = {"model": [], "persistence": [], "cams": []}
    for i, t0 in enumerate(times):
        for t in times[i + 1:]:
            h = int((datetime.fromisoformat(t) - datetime.fromisoformat(t0)).total_seconds() // 3600)
            if not 1 <= h <= 48 or t not in a or t not in w or a[t] is None or None in w[t]:
                continue
            temp, t850, wind = w[t]
            p, _ = predict(model, h, features(hist[t0], a[t], t850, temp, wind, int(t[11:13])))
            y = hist[t]
            errs["model"].append(abs(p - y))
            errs["persistence"].append(abs(hist[t0] - y))
            errs["cams"].append(abs(a[t] - y))
    n = len(errs["model"])
    mae = {k: (sum(v) / n if n else None) for k, v in errs.items()}
    cams_now = [a[t] for t in times if a.get(t) is not None]
    return {"sensor": name, "lat": lat, "lon": lon, "hours": len(times), "pairs": n, "mae": mae,
            "sensor_median": sorted(hist.values())[len(hist) // 2], "cams_median": sorted(cams_now)[len(cams_now) // 2] if cams_now else None}


def main():
    model = json.loads((ROOT / "data" / "forecast_model.json").read_text())
    snap = json.loads((ROOT / "data" / "sensors_snapshot.json").read_text())
    results = []
    for s in snap["sensors"]:
        if s.get("ok") and len(s.get("history", [])) >= 6:
            results.append({"sample": "A: AirKaz, последние сутки", **evaluate(s["name"], s["lat"], s["lon"], dict(s["history"]), model)})
    log_series, n_lines = series_from_log()
    for (sid, name, lat, lon), hist in log_series.items():
        if len(hist) >= 2:
            results.append({"sample": "B: наш лог", **evaluate(name, lat, lon, hist, model)})
    out = {"generated": datetime.now().isoformat(timespec="minutes"), "snapshot": snap["fetchedAt"], "log_lines": n_lines, "results": results}
    (ROOT / "data" / "small_sample.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    def f(v):
        return "—" if v is None else f"{v:.1f}".replace(".", ",")
    L = [
        "# Малая выборка: прогноз на реальных датчиках за последние сутки",
        "",
        f"Сгенерировано `pipeline/eval_small_sample.py` {out['generated']}. Снимок датчиков: {snap['fetchedAt']}. Строк в логе команды (`data-logs/airkaz/*.jsonl`, раз в 10 минут): {n_lines}.",
        "",
        "Это **малая выборка**: одни сутки, несколько дешёвых датчиков, поздняя осень без сильного смога. Она показывает, что модель не ломается на датчиках другого типа, но не доказывает точность. Основная оценка — `evals/forecast_report.md`.",
        "",
        "| Выборка | Датчик | Часов | Пар | Медиана датчика | Медиана CAMS | MAE модель | MAE persistence | MAE CAMS |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        L.append(f"| {r['sample']} | {r['sensor']} | {r['hours']} | {r['pairs']} | {f(r['sensor_median'])} | {f(r['cams_median'])} | {f(r['mae']['model'])} | {f(r['mae']['persistence'])} | {f(r['mae']['cams'])} |")
    if not any(r["sample"].startswith("B") for r in results):
        L += ["", f"Лог команды пока слишком короткий для оценки ({n_lines} строк, нужно хотя бы 2 часа). Скрипт подхватит его автоматически при следующем запуске."]
    L += ["", "Датчики, застрявшие около нуля (например, «Ерменсай»), исключены как неисправные.", ""]
    (ROOT / "evals" / "small_sample.md").write_text("\n".join(L))
    print("\n".join(L[6:]))


if __name__ == "__main__":
    main()
