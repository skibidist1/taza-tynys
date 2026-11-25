"""Logs AirKaz Almaty sensor readings + CAMS (Open-Meteo) every 10 min to JSONL. Source: airkaz.org (public page).

Usage: python3 pipeline/airkaz_logger.py [OUT_DIR]
OUT_DIR defaults to $TAZA_LOG_DIR or ../../data-logs/airkaz (the team log used by pipeline/eval_small_sample.py).
One file per day: OUT_DIR/YYYY-MM-DD.jsonl. Runs until stopped (Ctrl+C).
"""
import json, os, sys, time, urllib.request, datetime, pathlib, statistics
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TAZA_LOG_DIR", pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data-logs" / "airkaz"))
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (school hackathon research logger, 1 req/10min)"}
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8")
while True:
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        s = get("https://airkaz.org/almaty.php"); i = s.index("sensors_data"); j = s.index("[", i)
        d, _ = json.JSONDecoder().raw_decode(s[j:])
        alm = [{k: x.get(k) for k in ("id","name","lat","lng","pm25","pm10","temp","date")} for x in d if x.get("city") == "Алматы"]
        cams = json.loads(get("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=43.24&longitude=76.89&current=pm2_5,pm10&timezone=Asia%2FAlmaty"))
        latest = {}
        for x in alm:
            if x["pm25"] in (None, ""): continue
            if x["id"] not in latest or (x["date"] or "") > (latest[x["id"]]["date"] or ""): latest[x["id"]] = x
        live = [float(v["pm25"]) for v in latest.values()]
        rec = {"ts": ts, "n": len(live), "median_pm25": statistics.median(live) if live else None, "cams": cams.get("current"), "sensors": alm}
        with open(OUT / f"{ts[:10]}.jsonl", "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(ts, rec["n"], rec["median_pm25"], (cams.get("current") or {}).get("pm2_5"), flush=True)
    except Exception as e:
        print(ts, "ERR", e, flush=True)
    time.sleep(600)
