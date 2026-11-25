"""Download hourly history for two Almaty winters (Nov-Feb) from Open-Meteo.

Air quality: air-quality-api (CAMS global reanalysis/forecast archive).
Weather: historical-forecast-api (archived runs of the same "best match"
models the live forecast uses). The ERA5 archive API has no
boundary_layer_height, and historical forecasts only carry it from about
autumn 2024, so we use winters 2024/25 and 2025/26.

Usage: python3 pipeline/fetch_history.py
Writes pipeline/history/<winter>.json
"""
import json
import pathlib
import urllib.parse
import urllib.request

LAT, LON = 43.24, 76.89
TZ = "Asia/Almaty"
WINTERS = {
    "2024-25": ("2024-11-01", "2025-02-28"),
    "2025-26": ("2025-11-01", "2026-02-28"),
}
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "pipeline" / "history"


def get(url: str, params: dict) -> dict:
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=60) as r:
        return json.load(r)


def fetch(start: str, end: str) -> dict:
    aq = get("https://air-quality-api.open-meteo.com/v1/air-quality", {
        "latitude": LAT, "longitude": LON, "timezone": TZ,
        "hourly": "pm2_5,pm10,us_aqi", "start_date": start, "end_date": end,
    })
    wx = get("https://historical-forecast-api.open-meteo.com/v1/forecast", {
        "latitude": LAT, "longitude": LON, "timezone": TZ,
        "hourly": "temperature_2m,wind_speed_10m,boundary_layer_height",
        "wind_speed_unit": "ms", "start_date": start, "end_date": end,
    })
    assert aq["hourly"]["time"] == wx["hourly"]["time"], "time axes differ"
    h = {"time": aq["hourly"]["time"]}
    h["pm2_5"] = aq["hourly"]["pm2_5"]
    h["pm10"] = aq["hourly"]["pm10"]
    h["us_aqi"] = aq["hourly"]["us_aqi"]
    h["temp"] = wx["hourly"]["temperature_2m"]
    h["wind"] = wx["hourly"]["wind_speed_10m"]
    h["blh"] = wx["hourly"]["boundary_layer_height"]
    return {
        "source": {
            "air": "air-quality-api.open-meteo.com (CAMS)",
            "weather": "historical-forecast-api.open-meteo.com (best_match)",
            "lat": LAT, "lon": LON, "timezone": TZ,
            "aq_grid": [aq["latitude"], aq["longitude"]],
            "wx_grid": [wx["latitude"], wx["longitude"]],
        },
        "start": start, "end": end, "hourly": h,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (s, e) in WINTERS.items():
        d = fetch(s, e)
        n = len(d["hourly"]["time"])
        miss = {k: sum(v is None for v in d["hourly"][k]) for k in d["hourly"] if k != "time"}
        (OUT / f"{name}.json").write_text(json.dumps(d, separators=(",", ":")))
        print(name, n, "hours, missing:", miss)


if __name__ == "__main__":
    main()
