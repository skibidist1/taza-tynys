"""Build data/demo_winter.json: a real winter smog episode replayed from archives.

"Now" = 6 Feb 2025, 09:00 (Thursday). The "sensor now" is the real OpenAQ station 8876 value,
CAMS and weather are the archived values for the next 48 h, and `actual` keeps what the
station really measured afterwards, so the app can show forecast vs reality.
Usage: python3 pipeline/make_demo_winter.py  (after fetch_ground.py)
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
START, END, NOW = "2025-02-05T00:00", "2025-02-08T23:00", "2025-02-06T09:00"


def main():
    h = json.loads((ROOT / "pipeline" / "history" / "ground_8876.json").read_text())["hourly"]
    idx = [i for i, t in enumerate(h["time"]) if START <= t <= END]
    pick = lambda k: [h[k][i] for i in idx]  # noqa: E731
    times = pick("time")
    now_i = times.index(NOW)
    pm = pick("pm25")
    hist = [[t, v] for t, v in zip(times[now_i - 23:now_i + 1], pm[now_i - 23:now_i + 1]) if v is not None]
    station = {"id": "oaq-8876", "src": "openaq", "name": "Станция OpenAQ 8876 (архив)", "lat": 43.2529, "lon": 76.9312,
               "pm25": pm[now_i], "updated": NOW + "+05:00", "history": hist, "live": True, "suspect": False, "ok": True}
    demo = {
        "fetchedAt": NOW + "+05:00",
        "note": "Архив: станция OpenAQ 8876, CAMS и архив прогнозов погоды Open-Meteo, 5–8 февраля 2025",
        "air": {"utc_offset_seconds": 18000, "hourly": {"time": times, "pm2_5": pick("cams"), "pm10": [None] * len(times), "us_aqi": [None] * len(times)}},
        "weather": {"utc_offset_seconds": 18000, "hourly": {"time": times, "temperature_2m": pick("temp"), "temperature_850hPa": pick("t850"),
                                                             "wind_speed_10m": pick("wind"), "boundary_layer_height": pick("blh")}},
        "sensors": {"fetchedAt": NOW + "+05:00", "attribution": "архив OpenAQ (станция 8876)", "liveCount": 1, "median": pm[now_i], "sensors": [station], "errors": []},
        "actual": {"time": times, "pm25": pm},
    }
    (ROOT / "data" / "demo_winter.json").write_text(json.dumps(demo, ensure_ascii=False, separators=(",", ":")))
    print("demo", NOW, "station", pm[now_i], "cams", h["cams"][idx[now_i]])


if __name__ == "__main__":
    main()
