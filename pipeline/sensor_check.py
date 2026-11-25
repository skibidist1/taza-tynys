"""Spot check: CAMS (Open-Meteo) vs public ground sensors in Almaty, last ~24 h.

Sources without registration:
- AirKaz.org public page almaty.php embeds `sensors_data` with the last 24 hourly PM2.5
  values per sensor (low-cost sensors, community project).
- sensor.community live API (last 5 minutes per sensor) for the Almaty area.
No public archive of real sensors for past winters without registration was found
(OpenAQ v3 needs an API key; archive.sensor.community was not reachable from our network),
so this is a one-day sanity check, not a validation of the model.

Usage: python3 pipeline/sensor_check.py  -> evals/sensor_check.md, evals/sensor_check_data.json
"""
import json
import pathlib
import statistics
import urllib.request
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
UA = {"User-Agent": "taza-tynys-hackathon-check/1.0"}


def get(url, as_json=True):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", errors="replace")
    return json.loads(body) if as_json else body


def airkaz():
    html = get("https://airkaz.org/almaty.php", as_json=False)
    marker = "var sensors_data = "
    i = html.find(marker)
    if i < 0:
        return []
    data, _ = json.JSONDecoder().raw_decode(html[i + len(marker):])
    out = {}
    for x in data:
        if x.get("pm25") in (None, "") or x.get("hour") in (None, "now"):
            continue
        stamp = datetime.strptime(x["date"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - stamp > timedelta(hours=6):
            continue  # stale sensor
        h = int(x["hour"])
        # hour h = most recent clock hour h not later than the last update
        t = stamp.replace(minute=0, second=0)
        while t.hour != h:
            t -= timedelta(hours=1)
        key = (x["id"], x["name"], float(x["lat"]), float(x["lng"]))
        out.setdefault(key, {})[t.strftime("%Y-%m-%dT%H:00")] = float(x["pm25"])
    return [{"id": k[0], "name": k[1], "lat": k[2], "lon": k[3], "hourly": v} for k, v in out.items()]


def sensor_community():
    d = get("https://data.sensor.community/airrohr/v1/filter/area=43.25,76.92,25")
    by = {}
    for x in d:
        for v in x["sensordatavalues"]:
            if v["value_type"] == "P2":
                s = x["sensor"]["id"]
                by.setdefault(s, {"lat": float(x["location"]["latitude"]), "lon": float(x["location"]["longitude"]),
                                  "type": x["sensor"]["sensor_type"]["name"], "vals": []})["vals"].append(float(v["value"]))
    return [{"id": s, **{k: v for k, v in r.items() if k != "vals"}, "pm25_now": statistics.mean(r["vals"])} for s, r in by.items()]


def cams(lat, lon):
    d = get("https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={lat}&longitude={lon}&hourly=pm2_5&timezone=Asia%2FAlmaty&past_days=1&forecast_days=1")
    return dict(zip(d["hourly"]["time"], d["hourly"]["pm2_5"])), (d["latitude"], d["longitude"])


def main():
    ak = airkaz()
    sc = sensor_community()
    city, grid = cams(43.24, 76.89)
    rows = []
    for s in ak:
        c, g = cams(s["lat"], s["lon"])
        pairs = [(t, v, c.get(t)) for t, v in sorted(s["hourly"].items()) if c.get(t) is not None]
        s["pairs"] = pairs
        s["cams_grid"] = g
        if pairs:
            rows.append((s, statistics.median(p[1] for p in pairs), statistics.median(p[2] for p in pairs)))
    now_key = datetime.now().strftime("%Y-%m-%dT%H:00")
    for s in sc:
        c, _ = cams(s["lat"], s["lon"])
        s["cams_now"] = c.get(now_key)

    (ROOT / "evals" / "sensor_check_data.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="minutes"), "airkaz": ak, "sensor_community": sc,
         "cams_city": city, "cams_city_grid": grid}, ensure_ascii=False, indent=1, default=str))

    L = [
        "# Сверка CAMS с реальными датчиками Алматы (последние сутки)",
        "",
        f"Сгенерировано `pipeline/sensor_check.py` {datetime.now():%d.%m.%Y %H:%M} (время Алматы). Сырые данные: `evals/sensor_check_data.json`.",
        "",
        "## Что удалось найти без регистрации",
        "",
        "- **AirKaz.org** — на публичной странице `almaty.php` встроены почасовые PM2.5 за последние 24 часа по каждому датчику. Архива за прошлые зимы в открытом виде нет.",
        "- **sensor.community** — живой API без ключа (последние 5 минут). Архив `archive.sensor.community` из нашей сети не открылся.",
        "- **OpenAQ v3** требует API-ключ (регистрация) — не использовали.",
        "",
        "Поэтому полноценной проверки модели на реальных датчиках за зиму **нет**. Ниже — только сверка уровня CAMS с датчиками за последние сутки.",
        "",
        "## AirKaz: медианы за последние сутки",
        "",
        "| Датчик | Координаты | Часов | Медиана датчика, мкг/м³ | Медиана CAMS в той же точке | Датчик / CAMS |",
        "|---|---|---|---|---|---|",
    ]
    for s, m_s, m_c in rows:
        ratio = f"{m_s / m_c:.2f}".replace(".", ",") if m_c else "—"
        L.append(f"| {s['name']} | {s['lat']:.3f}, {s['lon']:.3f} | {len(s['pairs'])} | {m_s:.1f} | {m_c:.1f} | {ratio} |".replace(".", ","))
    if not rows:
        L.append("| нет активных датчиков | | | | | |")
    L += ["", "## sensor.community: текущие значения", "", "| Датчик | Тип | Координаты | PM2.5 сейчас (5 мин) | CAMS этот час |", "|---|---|---|---|---|"]
    for s in sc:
        cn = "—" if s["cams_now"] is None else f"{s['cams_now']:.1f}"
        L.append(f"| {s['id']} | {s['type']} | {s['lat']:.3f}, {s['lon']:.3f} | {s['pm25_now']:.1f} | {cn} |".replace(".", ","))
    L += [
        "",
        "## Выводы и ограничения",
        "",
        "- Активных публичных датчиков мало (на AirKaz сейчас единицы), часть стоит в предгорьях, где воздух чище, чем в центре котловины.",
        "- Это недорогие оптические датчики без поверки; при высокой влажности они завышают PM2.5.",
        "- Одни сутки в конце ноября — не зимний смог. Главная известная проблема CAMS — занижение зимних пиков (максимум CAMS за две зимы около 110 мкг/м³, а городские датчики в морозные вечера, по сообщениям мониторинговых проектов, показывают кратно больше; архивом это проверить не удалось) — на таких сутках не проявляется.",
        f"- За эти сутки точек, где датчик выше CAMS: {sum(1 for _, a, b in rows if a > b) + sum(1 for x in sc if x['cams_now'] is not None and x['pm25_now'] > x['cams_now'])}, ниже CAMS: {sum(1 for _, a, b in rows if a <= b) + sum(1 for x in sc if x['cams_now'] is not None and x['pm25_now'] <= x['cams_now'])}. Сетка CAMS около 40 км не видит разницу между районами (частный сектор на севере против предгорий на юге), ошибка бывает в обе стороны.",
        "- Вывод для продукта: абсолютным цифрам CAMS для конкретного района доверять нельзя, поэтому приложение строит окна и рекомендации по **относительной** шкале внутри дня и подписывает модель и её ограничения.",
        "",
    ]
    (ROOT / "evals" / "sensor_check.md").write_text("\n".join(L))
    print("\n".join(L[13:13 + len(rows) + 8 + len(sc)]))


if __name__ == "__main__":
    main()
