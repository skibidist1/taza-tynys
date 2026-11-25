"""Real hourly PM2.5 history: OpenAQ public S3 archive, location 8876 (Almaty, 43.2529 N 76.9312 E).

No API key: files are public at openaq-data-archive.s3.amazonaws.com
records/csv.gz/locationid=8876/year=YYYY/month=MM/location-8876-YYYYMMDD.csv.gz
Also fetches CAMS PM2.5 and weather (incl. temperature_850hPa) for the same point and hours.
Usage: python3 pipeline/fetch_ground.py   -> pipeline/history/ground_8876.json
"""
import csv
import gzip
import io
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOC = 8876
LAT, LON = 43.2529, 76.9312
START, END = date(2024, 10, 1), date(2025, 11, 30)  # BLH archive starts ~autumn 2024; OpenAQ archive ends Nov 2025
BASE = "https://openaq-data-archive.s3.amazonaws.com/records/csv.gz"


def day_file(d):
    url = f"{BASE}/locationid={LOC}/year={d:%Y}/month={d:%m}/location-{LOC}-{d:%Y%m%d}.csv.gz"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = gzip.decompress(r.read()).decode("utf-8")
    except urllib.error.HTTPError:
        return []
    rows = []
    for rec in csv.DictReader(io.StringIO(raw)):
        if rec["parameter"] == "pm25":
            # "2025-01-15T01:00:00+05:00" is the END of the averaging hour; store hour start, local time
            t = rec["datetime"][:19]
            rows.append((t, float(rec["value"])))
    return rows


def om(url, params):
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=120) as r:
        return json.load(r)


def main():
    from datetime import datetime
    pm = {}
    d = START
    while d <= END:
        for t, v in day_file(d):
            start = (datetime.fromisoformat(t) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:00")
            pm[start] = v
        d += timedelta(days=1)
    common = {"latitude": LAT, "longitude": LON, "timezone": "Asia/Almaty",
              "start_date": START.isoformat(), "end_date": END.isoformat()}
    aq = om("https://air-quality-api.open-meteo.com/v1/air-quality", {**common, "hourly": "pm2_5"})
    wx = om("https://historical-forecast-api.open-meteo.com/v1/forecast", {
        **common, "wind_speed_unit": "ms",
        "hourly": "temperature_2m,temperature_850hPa,wind_speed_10m,boundary_layer_height"})
    assert aq["hourly"]["time"] == wx["hourly"]["time"]
    times = aq["hourly"]["time"]
    out = {
        "source": {
            "ground": f"OpenAQ archive, location {LOC} ({LAT}, {LON}); provider not stated in the archive",
            "cams": "air-quality-api.open-meteo.com (CAMS)",
            "weather": "historical-forecast-api.open-meteo.com (best_match)",
        },
        "hourly": {
            "time": times,
            "pm25": [pm.get(t) for t in times],
            "cams": aq["hourly"]["pm2_5"],
            "temp": wx["hourly"]["temperature_2m"],
            "t850": wx["hourly"]["temperature_850hPa"],
            "wind": wx["hourly"]["wind_speed_10m"],
            "blh": wx["hourly"]["boundary_layer_height"],
        },
    }
    p = ROOT / "pipeline" / "history" / f"ground_{LOC}.json"
    p.write_text(json.dumps(out, separators=(",", ":")))
    h = out["hourly"]
    print("hours", len(times), "with pm25", sum(v is not None for v in h["pm25"]),
          "missing t850", sum(v is None for v in h["t850"]), "missing blh", sum(v is None for v in h["blh"]))


if __name__ == "__main__":
    main()
