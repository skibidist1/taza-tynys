"""Static checks for the Taza Tynys PWA. Run: python3 scripts/check.py

- data/forecast_model.json matches the contract and pipeline/forecast_features.FEATURES
- data/sensors_snapshot.json: sensors with coordinates, liveCount consistent
- api/*.py talks only to airkaz.org and data.sensor.community
- data/snapshot.json, data/demo_winter.json: valid raw Open-Meteo shape
- every file listed in the sw.js cache exists; local links in index.html exist
- app files reach out only to api.open-meteo.com and air-quality-api.open-meteo.com
"""
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from forecast_features import FEATURES, HORIZON  # noqa: E402

ALLOWED_HOSTS = {"api.open-meteo.com", "air-quality-api.open-meteo.com"}
APP_FILES = ["index.html", "styles.css", "sw.js", "manifest.webmanifest", "vercel.json"] + \
    [str(p.relative_to(ROOT)) for p in (ROOT / "js").glob("*.js")] + \
    [str(p.relative_to(ROOT)) for p in (ROOT / "data").glob("*.json")]
# XML namespace identifiers are not network requests
IGNORED_URLS = {"http://www.w3.org/2000/svg"}

errors = []


def err(msg):
    errors.append(msg)


def load(rel):
    try:
        return json.loads((ROOT / rel).read_text())
    except Exception as e:  # noqa: BLE001
        err(f"{rel}: cannot parse JSON ({e})")
        return None


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def check_model():
    m = load("data/forecast_model.json")
    if not m:
        return
    if m.get("features") != FEATURES:
        err(f"forecast_model.json: features {m.get('features')} != pipeline FEATURES {FEATURES}")
    n = len(FEATURES)
    for k in ("mean", "std"):
        v = m.get(k, [])
        if len(v) != n or not all(finite(x) for x in v):
            err(f"forecast_model.json: '{k}' must be {n} finite numbers")
    if any(s <= 0 for s in m.get("std", [1])):
        err("forecast_model.json: std must be > 0")
    hz = m.get("horizons", [])
    if len(hz) != HORIZON:
        err(f"forecast_model.json: need {HORIZON} horizons, got {len(hz)}")
    for k, h in enumerate(hz, 1):
        if h.get("h") != k or len(h.get("coef", [])) != n or not finite(h.get("intercept")) or not (0.5 < h.get("smear", 0) < 3):
            err(f"forecast_model.json: bad horizon {k}")
    for k in ("mae_model", "mae_persistence", "mae_cams"):
        if not (finite(m.get("metrics", {}).get(k)) and m["metrics"][k] > 0):
            err(f"forecast_model.json: metrics.{k} missing")


def check_sensors(rel):
    d = load(rel)
    if not d:
        return
    if not isinstance(d.get("sensors"), list) or not d["sensors"]:
        err(f"{rel}: no sensors")
        return
    for s in d["sensors"]:
        if not (finite(s.get("lat")) and finite(s.get("lon"))) or "ok" not in s:
            err(f"{rel}: sensor {s.get('id')} lacks lat/lon/ok")
            break
    ok = [s for s in d["sensors"] if s["ok"]]
    if d.get("liveCount") != len(ok):
        err(f"{rel}: liveCount {d.get('liveCount')} != {len(ok)} ok sensors")
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", d.get("fetchedAt", "")):
        err(f"{rel}: fetchedAt missing")


def check_raw(rel, min_hours=96):
    d = load(rel)
    if not d:
        return
    try:
        a, w = d["air"]["hourly"], d["weather"]["hourly"]
        n = len(a["time"])
        if n < min_hours:
            err(f"{rel}: only {n} hours")
        for k in ("pm2_5", "pm10", "us_aqi"):
            if len(a[k]) != n:
                err(f"{rel}: air.{k} length mismatch")
        for k in ("temperature_2m", "temperature_850hPa", "wind_speed_10m", "boundary_layer_height"):
            if len(w[k]) != len(w["time"]):
                err(f"{rel}: weather.{k} length mismatch")
        if a["time"] != w["time"]:
            err(f"{rel}: air and weather time axes differ")
        nulls = sum(v is None for v in a["pm2_5"])
        if nulls > 0.05 * n:
            err(f"{rel}: too many missing pm2_5 ({nulls})")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", d.get("fetchedAt", "")):
            err(f"{rel}: fetchedAt missing or malformed")
        if not (a["time"][0][:13] <= d["fetchedAt"][:13] <= a["time"][-1][:13]):
            err(f"{rel}: fetchedAt outside of data range")
    except (KeyError, TypeError) as e:
        err(f"{rel}: bad shape ({e})")


def check_sw():
    sw = (ROOT / "sw.js").read_text()
    m = re.search(r"const ASSETS = \[(.*?)\];", sw, re.S)
    if not m:
        err("sw.js: ASSETS list not found")
        return
    assets = re.findall(r"'([^']+)'", m.group(1))
    for a in assets:
        if a == "./":
            continue
        if not (ROOT / a).is_file():
            err(f"sw.js: cached file missing: {a}")
    # every runtime module and data file the app loads must be cached for offline use
    must = [str(p.relative_to(ROOT)) for p in (ROOT / "js").glob("*.js")] + \
        ["data/forecast_model.json", "data/snapshot.json", "data/sensors_snapshot.json", "data/demo_winter.json", "index.html", "styles.css"]
    for f in must:
        if f not in assets:
            err(f"sw.js: {f} is not in the offline cache")


def check_links():
    html = (ROOT / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="([^"#]+)"', html):
        if re.match(r"^[a-z]+:", ref):
            continue
        if not (ROOT / ref).is_file():
            err(f"index.html: missing local file {ref}")
    man = load("manifest.webmanifest") or {}
    for icon in man.get("icons", []):
        if not (ROOT / icon["src"]).is_file():
            err(f"manifest: missing icon {icon['src']}")


def check_external_urls():
    for rel in APP_FILES:
        text = (ROOT / rel).read_text(errors="replace")
        for url in re.findall(r"https?://[^\s'\"`)<>]+", text):
            if url in IGNORED_URLS:
                continue
            host = re.sub(r"^https?://", "", url).split("/")[0].split("?")[0]
            if host not in ALLOWED_HOSTS:
                err(f"{rel}: external URL not allowed: {url}")
        if re.search(r"@import|fonts\.googleapis|cdn\.", text):
            err(f"{rel}: external font/CDN reference")


API_HOSTS = {"airkaz.org", "data.sensor.community"}


def check_api():
    """The serverless function may only talk to the two sensor sources."""
    for p in (ROOT / "api").glob("*.py"):
        for url in re.findall(r"https?://[^\s'\"]+", p.read_text()):
            host = re.sub(r"^https?://", "", url).split("/")[0]
            if host not in API_HOSTS:
                err(f"{p.relative_to(ROOT)}: external URL not allowed: {url}")


def main():
    check_model()
    check_raw("data/snapshot.json")
    check_raw("data/demo_winter.json", min_hours=72)
    check_sensors("data/sensors_snapshot.json")
    check_api()
    check_sw()
    check_links()
    check_external_urls()
    if errors:
        print("check.py: FAIL")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"check.py: OK ({len(APP_FILES)} app files scanned)")


if __name__ == "__main__":
    main()
