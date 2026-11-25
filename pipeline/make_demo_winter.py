"""Build data/demo_winter.json: a real winter smog episode replayed from the archive.

Same shape as data/snapshot.json, so the app runs it through the same code.
Values: CAMS PM2.5/PM10 (air-quality-api archive) and archived weather forecasts
(historical-forecast-api), 16-20 Dec 2025; "now" = 17 Dec 2025, 09:00.
Usage: python3 pipeline/make_demo_winter.py  (after fetch_history.py)
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
START, END, NOW = "2025-12-16T00:00", "2025-12-20T23:00", "2025-12-17T09:00+05:00"


def main():
    h = json.loads((ROOT / "pipeline" / "history" / "2025-26.json").read_text())["hourly"]
    idx = [i for i, t in enumerate(h["time"]) if START <= t <= END]
    pick = lambda k: [h[k][i] for i in idx]  # noqa: E731
    demo = {
        "fetchedAt": NOW,
        "note": "Архив Open-Meteo: CAMS и архив прогнозов погоды, эпизод смога 16–20 декабря 2025",
        "air": {"utc_offset_seconds": 18000, "hourly": {"time": pick("time"), "pm2_5": pick("pm2_5"), "pm10": pick("pm10"), "us_aqi": pick("us_aqi")}},
        "weather": {"utc_offset_seconds": 18000, "hourly": {"time": pick("time"), "temperature_2m": pick("temp"), "wind_speed_10m": pick("wind"), "boundary_layer_height": pick("blh")}},
    }
    (ROOT / "data" / "demo_winter.json").write_text(json.dumps(demo, ensure_ascii=False, separators=(",", ":")))
    print("demo hours", len(idx))


if __name__ == "__main__":
    main()
