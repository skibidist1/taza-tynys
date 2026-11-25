"""Real ground sensors in Almaty, one JSON (Vercel Python serverless: GET /api/sensors).

Sources, no registration:
- AirKaz.org: the public page almaty.php embeds `sensors_data = [...]` with up to the last
  24 hourly PM2.5 rows per sensor (the same sensor repeats once per hour). AirKaz sends no
  CORS headers, so the browser cannot read it directly; this function does it server-side.
- sensor.community: public live API, last ~5 minutes per sensor.
A sensor counts as live if its last update is within LIVE_HOURS; "ok" = live and not stuck near zero.
Attribution required in the UI: "данные AirKaz.org, sensor.community".
"""
import json
import statistics
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

ALMATY = timezone(timedelta(hours=5))
LIVE_HOURS = 3
UA = {"User-Agent": "taza-tynys/1.0 (school air-quality prototype)"}
AIRKAZ_URL = "https://airkaz.org/almaty.php"
SC_URL = "https://data.sensor.community/airrohr/v1/filter/area=43.25,76.92,25"


def _get(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_airkaz(html, now):
    i = html.find("sensors_data")
    if i < 0:
        return []
    start = html.find("[", i)
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    by = {}
    for x in data:
        try:
            lat, lon = float(x["lat"]), float(x["lng"])
            stamp = datetime.strptime(x["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ALMATY)
        except (KeyError, TypeError, ValueError):
            continue
        s = by.setdefault(x["id"], {"id": f"ak-{x['id']}", "src": "airkaz", "name": x.get("name") or "",
                                    "lat": lat, "lon": lon, "updated": stamp.isoformat(timespec="minutes"),
                                    "history": {}, "pm25": None})
        if x.get("pm25") in (None, ""):
            continue
        v = float(x["pm25"])
        hour = x.get("hour")
        if hour == "now":
            s["pm25"] = v
            continue
        try:
            h = int(hour)
        except (TypeError, ValueError):
            continue
        t = stamp.replace(minute=0, second=0, microsecond=0)
        while t.hour != h:
            t -= timedelta(hours=1)
        s["history"][t.strftime("%Y-%m-%dT%H:00")] = v
    out = []
    for s in by.values():
        hist = sorted(s["history"].items())
        if s["pm25"] is None and hist:
            s["pm25"] = hist[-1][1]
        s["history"] = [[t, v] for t, v in hist]
        s["live"] = s["pm25"] is not None and now - datetime.fromisoformat(s["updated"]) <= timedelta(hours=LIVE_HOURS)
        # a sensor whose daily median is below 1 ug/m3 is most likely broken (city air is never that clean for a day)
        vals = sorted([v for _, v in hist] + ([s["pm25"]] if s["pm25"] is not None else []))
        s["suspect"] = len(vals) >= 6 and vals[len(vals) // 2] < 1.0
        out.append(s)
    return out


def parse_sc(text, now):
    by = {}
    for x in json.loads(text):
        for v in x.get("sensordatavalues", []):
            if v.get("value_type") != "P2":
                continue
            sid = x["sensor"]["id"]
            s = by.setdefault(sid, {"id": f"sc-{sid}", "src": "sensor.community",
                                    "name": f"sensor.community {x['sensor']['sensor_type']['name']} #{sid}",
                                    "lat": float(x["location"]["latitude"]), "lon": float(x["location"]["longitude"]),
                                    "vals": [], "updated": None})
            s["vals"].append(float(v["value"]))
            ts = datetime.strptime(x["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(ALMATY)
            if s["updated"] is None or ts.isoformat() > s["updated"]:
                s["updated"] = ts.isoformat(timespec="minutes")
    out = []
    for s in by.values():
        vals = s.pop("vals")
        s["pm25"] = round(statistics.mean(vals), 1)
        s["history"] = []
        s["live"] = now - datetime.fromisoformat(s["updated"]) <= timedelta(hours=LIVE_HOURS)
        s["suspect"] = False
        out.append(s)
    return out


def collect():
    now = datetime.now(ALMATY)
    sensors, errors = [], []
    try:
        sensors += parse_airkaz(_get(AIRKAZ_URL), now)
    except Exception as e:  # noqa: BLE001
        errors.append(f"airkaz: {e}")
    try:
        sensors += parse_sc(_get(SC_URL), now)
    except Exception as e:  # noqa: BLE001
        errors.append(f"sensor.community: {e}")
    for s in sensors:
        s["ok"] = bool(s["live"] and not s["suspect"])
    live = [s["pm25"] for s in sensors if s["ok"]]
    return {
        "fetchedAt": now.isoformat(timespec="minutes"),
        "attribution": "данные AirKaz.org и sensor.community",
        "liveCount": len(live),
        "median": round(statistics.median(live), 1) if live else None,
        "sensors": sensors,
        "errors": errors,
    }


class handler(BaseHTTPRequestHandler):  # noqa: N801 (Vercel expects this name)
    def do_GET(self):  # noqa: N802
        body = json.dumps(collect(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, s-maxage=600, stale-while-revalidate=1200")
        self.end_headers()
        self.wfile.write(body)
