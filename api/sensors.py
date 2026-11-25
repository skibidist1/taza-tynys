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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler

ALMATY = timezone(timedelta(hours=5))
LIVE_HOURS = 3
UA = {"User-Agent": "taza-tynys/1.0 (school air-quality prototype)"}
AIRKAZ_URL = "https://airkaz.org/almaty.php"
SC_URL = "https://data.sensor.community/airrohr/v1/filter/area=43.25,76.92,25"


# AirKaz answers in ~5-6 s; sensor.community is fast. Vercel's default function limit is 10 s+.
TIMEOUTS = {"airkaz": 11, "sensor.community": 6}


def _get(url, timeout=6):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


VALID = (0.0, 500.0)  # PM2.5 outside [0, 500) is a sensor error (e.g. SDS011 in fog reports 999.9, -1 = no data)


def _valid(v):
    return VALID[0] <= v < VALID[1]


def parse_airkaz(html, now):
    i = html.find("sensors_data")
    if i < 0:
        raise ValueError("sensors_data marker not found (page layout changed?)")
    start = html.find("[", i)
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    by = {}
    for x in data:
        try:  # one broken row must not kill the whole source
            if x.get("city") not in (None, "", "Алматы"):
                continue  # the page also lists sensors of other cities
            lat, lon = float(x["lat"]), float(x["lng"])
            stamp = datetime.strptime(x["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ALMATY)
            s = by.setdefault(x["id"], {"id": f"ak-{x['id']}", "src": "airkaz", "name": x.get("name") or "",
                                        "lat": lat, "lon": lon, "updated": stamp.isoformat(timespec="minutes"),
                                        "history": {}, "pm25": None})
            if x.get("pm25") in (None, ""):
                continue
            v = float(x["pm25"])
            hour = x.get("hour")
            if not _valid(v):
                if hour == "now":
                    s["bad_now"] = True  # current reading is an error code: do not fall back to an old hour as "live"
                continue
            if hour == "now":
                s["pm25"] = v
                continue
            h = int(hour)
            if not 0 <= h <= 23:
                continue
            t = stamp.replace(minute=0, second=0, microsecond=0)
            t -= timedelta(hours=(t.hour - h) % 24)  # most recent clock hour h not later than the update
            s["history"][t.strftime("%Y-%m-%dT%H:00")] = v
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    out = []
    for s in by.values():
        hist = sorted(s["history"].items())
        if s["pm25"] is None and hist:
            s["pm25"] = hist[-1][1]
        s["history"] = [[t, v] for t, v in hist]
        s["live"] = s["pm25"] is not None and now - datetime.fromisoformat(s["updated"]) <= timedelta(hours=LIVE_HOURS)
        # a sensor whose daily median is below 1 ug/m3 is most likely broken (city air is never that clean for a day)
        vals = sorted([v for _, v in hist] + ([s["pm25"]] if s["pm25"] is not None else []))
        s["suspect"] = (len(vals) >= 6 and vals[len(vals) // 2] < 1.0) or s.pop("bad_now", False)
        out.append(s)
    return out


def parse_sc(text, now):
    by = {}
    for x in json.loads(text):
        try:
            for v in x.get("sensordatavalues", []):
                if v.get("value_type") != "P2":
                    continue
                sid = x["sensor"]["id"]
                s = by.setdefault(sid, {"id": f"sc-{sid}", "src": "sensor.community",
                                        "name": f"sensor.community {x['sensor']['sensor_type']['name']} #{sid}",
                                        "lat": float(x["location"]["latitude"]), "lon": float(x["location"]["longitude"]),
                                        "vals": [], "bad": 0, "updated": None})
                val = float(v["value"])
                if _valid(val):
                    s["vals"].append(val)
                else:
                    s["bad"] += 1
                ts = datetime.strptime(x["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(ALMATY)
                if s["updated"] is None or ts.isoformat() > s["updated"]:
                    s["updated"] = ts.isoformat(timespec="minutes")
        except (KeyError, TypeError, ValueError):
            continue
    out = []
    for s in by.values():
        vals = s.pop("vals")
        bad = s.pop("bad")
        s["pm25"] = round(statistics.mean(vals), 1) if vals else None
        s["history"] = []
        s["live"] = s["pm25"] is not None and now - datetime.fromisoformat(s["updated"]) <= timedelta(hours=LIVE_HOURS)
        s["suspect"] = bad > 0 or s["pm25"] is None
        out.append(s)
    return out


def collect():
    now = datetime.now(ALMATY)
    sensors, errors = [], []
    jobs = {"airkaz": (AIRKAZ_URL, parse_airkaz), "sensor.community": (SC_URL, parse_sc)}
    with ThreadPoolExecutor(max_workers=2) as ex:  # fetch both sources in parallel
        futs = {name: ex.submit(_get, url, TIMEOUTS[name]) for name, (url, _) in jobs.items()}
        for name, (_, parse) in jobs.items():
            try:
                sensors += parse(futs[name].result(), now)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")
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
        data = collect()
        failed = data["liveCount"] == 0 and data["errors"]
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        # never let a CDN keep an empty answer: both sources down -> 502, no-store
        self.send_response(502 if failed else 200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # partial answer (one source failed) is cached only briefly, without stale-while-revalidate
        cache = "no-store" if failed else ("public, s-maxage=60" if data["errors"] else "public, s-maxage=600, stale-while-revalidate=1200")
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)
