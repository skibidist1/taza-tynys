"""Python model == JS model on fixed inputs.

Runs js/trap.js through macOS JavaScriptCore (jsc) and compares its output
with pipeline/trap_features.py and with the expected values exported by
pipeline/train_trap.py (tests/model_cases.json).
Run: python3 tests/test_model.py   (or python3 -m pytest tests)
"""
import json
import math
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
from trap_features import build_features, predict  # noqa: E402

JSC_CANDIDATES = [
    "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc",
    shutil.which("jsc") or "",
]
TOL = 1e-9


def load(p):
    return json.loads((ROOT / p).read_text())


def close(a, b, tol=TOL):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def find_jsc():
    for c in JSC_CANDIDATES:
        if c and pathlib.Path(c).exists():
            return c
    return None


def run_js():
    jsc = find_jsc()
    if not jsc:
        return None
    r = subprocess.run(
        [jsc, "-m", "tests/js_harness.mjs", "--", "tests/model_cases.json", "data/model.json", "data/factors.json"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_python_matches_exported_cases():
    model, cases = load("data/model.json"), load("tests/model_cases.json")
    s = cases["series"]
    for c in cases["series_cases"]:
        x = build_features(s["time"], s["wind"], s["temp"], s["blh"], c["i"])
        p, _ = predict(model, x)
        assert all(close(a, b) for a, b in zip(x, c["x"])), c["i"]
        assert close(p, c["p"])
    for v in cases["vector_cases"]:
        assert close(predict(model, v["x"])[0], v["p"])


def test_js_matches_python():
    out = run_js()
    if out is None:
        print("SKIP: jsc not found, JS side not executed")
        return
    cases = load("tests/model_cases.json")
    for js, py in zip(out["series"], cases["series_cases"]):
        assert js["i"] == py["i"]
        assert all(close(a, b) for a, b in zip(js["x"], py["x"])), (js["x"], py["x"])
        assert close(js["p"], py["p"]), (js["p"], py["p"])
        assert all(close(a, b) for a, b in zip(js["contrib"], py["contrib"]))
    for js, py in zip(out["vectors"], cases["vector_cases"]):
        assert close(js["p"], py["p"])


def test_model_contract():
    m = load("data/model.json")
    n = len(m["features"])
    for k in ("mean", "std", "coef"):
        assert len(m[k]) == n
    assert all(s > 0 for s in m["std"])
    assert 0 < m["threshold"] < 1 and math.isfinite(m["intercept"])
    # Physically sensible signs for weather features: calmer, colder, lower layer -> higher risk.
    assert m["coef"][0] < 0 and m["coef"][1] < 0 and m["coef"][2] < 0


def test_calc_js_matches_python():
    out = run_js()
    if out is None:
        return
    sys.path.insert(0, str(ROOT / "tests"))
    from calc_ref import compute_house
    py = compute_house(load("data/factors.json"), "coal_stove", 4, False)
    js = out["calc"]
    for opt_js in js["options"]:
        opt_py = py[opt_js["key"]]
        for k in ("pm_kg", "pm_kg_low", "pm_kg_high", "cost_kzt", "amount"):
            assert close(opt_js[k], opt_py[k], 1e-9), (opt_js["key"], k, opt_js[k], opt_py[k])


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
