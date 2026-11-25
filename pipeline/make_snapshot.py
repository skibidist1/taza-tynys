"""Save a real Open-Meteo response as the offline fallback data/snapshot.json.

The app loads exactly these two URLs (see js/data.js); the snapshot keeps the
raw responses so the same normalisation code runs on it.
Usage: python3 pipeline/make_snapshot.py
"""
import json
import pathlib
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMON = "latitude=43.24&longitude=76.89&timezone=Asia%2FAlmaty&past_days=1&forecast_days=3"
AIR = f"https://air-quality-api.open-meteo.com/v1/air-quality?{COMMON}&hourly=pm2_5,pm10,us_aqi"
WX = (f"https://api.open-meteo.com/v1/forecast?{COMMON}"
      "&hourly=temperature_2m,temperature_850hPa,wind_speed_10m,boundary_layer_height&wind_speed_unit=ms")


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main():
    air, wx = get(AIR), get(WX)
    now = datetime.now(timezone(timedelta(hours=5)))
    snap = {
        "fetchedAt": now.isoformat(timespec="minutes"),
        "note": "Снимок реального ответа Open-Meteo для офлайн-демо",
        "air": air,
        "weather": wx,
    }
    out = ROOT / "data" / "snapshot.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    print("saved", out, snap["fetchedAt"], len(air["hourly"]["time"]), "hours")


if __name__ == "__main__":
    main()
