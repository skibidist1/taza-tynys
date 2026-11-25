"""Forecast model: Python == JS on fixed inputs; model contract.

Run: python3 tests/test_forecast.py  (JS side needs macOS JavaScriptCore `jsc`)
"""
import json
import math
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from forecast_features import FEATURES, HORIZON, features, predict  # noqa: E402

JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
RAW = [(80, 40, -2, -6, 0.8, 20), (15, 25, 1, -3, 1.5, 13), (150, 60, 4, -10, 0.3, 21), (5, 10, -8, 2, 3.5, 14)]


def load(p):
    return json.loads((ROOT / p).read_text())


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def test_contract():
    m = load("data/forecast_model.json")
    assert m["features"] == FEATURES
    assert len(m["horizons"]) == HORIZON
    for k, hz in enumerate(m["horizons"], 1):
        assert hz["h"] == k and len(hz["coef"]) == len(FEATURES) and math.isfinite(hz["intercept"])
    assert all(s > 0 for s in m["std"])
    for k in ("model", "persistence", "cams", "max_pers_cams"):
        assert m["metrics"]["mae"][k] > 0
    assert 0.6 < m["metrics"]["interval80_coverage"] < 0.98
    assert all(hz["q10"] < 0 < hz["q90"] for hz in m["horizons"])


def test_python_cases():
    m, cases = load("data/forecast_model.json"), load("tests/forecast_cases.json")
    for c, raw in zip(cases, RAW):
        x = features(*raw)
        assert all(close(a, b) for a, b in zip(x, c["x"]))
        assert close(predict(m, c["h"], x)[0], c["p"])


def test_js_matches_python():
    if not pathlib.Path(JSC).exists():
        raise AssertionError("SKIPPED: JavaScriptCore (jsc) not found - JS twin NOT tested")
    r = subprocess.run([JSC, "-m", "tests/forecast_harness.mjs", "--", "tests/forecast_cases.json", "data/forecast_model.json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)
    for a, c in zip(js, load("tests/forecast_cases.json")):
        assert all(close(u, v) for u, v in zip(a["x"], c["x"])), (a["x"], c["x"])
        assert close(a["pm"], c["p"]), (a["pm"], c["p"])
        for k in ("median", "lo", "hi"):
            assert close(a[k], c[k]), (k, a[k], c[k])
        assert a["lo"] <= a["median"] <= a["hi"]
        assert all(close(u, v) for u, v in zip(a["contrib"], c["contrib"]))


def test_inversion_raises_forecast():
    """Physics sanity: stronger inversion and calmer wind -> higher forecast (same other inputs)."""
    m = load("data/forecast_model.json")
    for h in (6, 12, 24):
        calm = predict(m, h, features(40, 30, 8, -5, 0.5, 20))[0]
        mixed = predict(m, h, features(40, 30, -6, -5, 3.0, 20))[0]
        assert calm > mixed, (h, calm, mixed)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
