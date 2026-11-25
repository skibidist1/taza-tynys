"""Static checks for the Taza Tynys PWA. Run: python3 scripts/check.py

- data/model.json matches the model contract and pipeline/trap_features.FEATURES
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
from trap_features import FEATURES  # noqa: E402

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
    m = load("data/model.json")
    if not m:
        return
    for k in ("features", "mean", "std", "coef", "intercept", "threshold", "trained_on", "metrics"):
        if k not in m:
            err(f"model.json: missing '{k}'")
    if m.get("features") != FEATURES:
        err(f"model.json: features {m.get('features')} != pipeline FEATURES {FEATURES}")
    n = len(FEATURES)
    for k in ("mean", "std", "coef"):
        v = m.get(k, [])
        if len(v) != n or not all(finite(x) for x in v):
            err(f"model.json: '{k}' must be {n} finite numbers")
    if any(s <= 0 for s in m.get("std", [1])):
        err("model.json: std must be > 0")
    if not finite(m.get("intercept")) or not (0 < m.get("threshold", -1) < 1):
        err("model.json: bad intercept/threshold")
    for k in ("auc", "precision", "recall", "baseline_temp_only_auc", "baseline_hour_only_auc"):
        if not (0 <= m.get("metrics", {}).get(k, -1) <= 1):
            err(f"model.json: metrics.{k} missing or out of [0,1]")


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
        for k in ("temperature_2m", "wind_speed_10m", "boundary_layer_height"):
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
        ["data/model.json", "data/snapshot.json", "data/demo_winter.json", "index.html", "styles.css"]
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


def main():
    check_model()
    check_raw("data/snapshot.json")
    check_raw("data/demo_winter.json")
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
