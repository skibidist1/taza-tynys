"""App logic on real snapshots and the winter archive (runs js/*.js with macOS JavaScriptCore).

Run: python3 tests/test_app_logic.py
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"
OUT = None


def jsc(*args):
    r = subprocess.run([JSC, "-m", *args], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip(), r.stderr or r.stdout
    return json.loads(r.stdout)


def out():
    global OUT
    if OUT is None:
        OUT = jsc("tests/app_harness.mjs", "--", "data/snapshot.json", "data/sensors_snapshot.json", "data/forecast_model.json", "data/demo_winter.json")
    return OUT


def test_nearest_sensor_is_healthy():
    o = out()
    assert o["near"] is None or o["near"]["ok"]
    assert o["nearAllOk"]
    assert abs(o["dist"] - 1.112) < 0.01


def test_forecast_48h():
    o = out()
    assert not o["stale"]
    assert o["viewLen"] >= 40, o["viewLen"]
    assert o["fcOk"]


def test_epa_categories():
    assert out()["cats"] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5]


def test_actions_per_profile():
    for p, v in out()["profiles"].items():
        assert len(v["actions"]) == 3, p
        assert v["actions"][2].startswith("cat_") and v["actions"][2].endswith(p)


def test_school_rules():
    for lessons in out()["school"]:
        for l in lessons:
            assert l["v"] in ("yes", "light", "no", None)
            if l["v"] == "no":
                assert l["pm"] > 55.4
            if l["v"] == "yes":
                assert l["pm"] <= 35.4


def test_winter_demo():
    o = out()
    assert o["winterNow"] > 2 * o["winterCams"], (o["winterNow"], o["winterCams"])
    assert o["winterSchool"].count("no") + o["winterSchool"].count("light") >= 4, o["winterSchool"]


def test_i18n():
    k = out()["keys"]
    ru, kk = set(k["ru"]), set(k["kk"])
    assert kk <= ru, kk - ru
    must_kk = {"ann_head", "ann_intro", "ann_item", "ann_none", "ann_bad", "ann_src", "v_yes", "v_light", "v_no",
               "r_ok", "r_usg", "r_unhealthy", "r_nodata", "cat_good", "cat_moderate", "cat_usg", "cat_unhealthy", "cat_very", "cat_hazardous",
               "tab_today", "tab_school", "now_title", "cams_says", "school_title", "lesson"}
    assert must_kk <= kk, must_kk - kk
    assert kk == ru, ru - kk  # all screens are translated
    app = (ROOT / "js" / "app.js").read_text() + (ROOT / "index.html").read_text()
    used = set(re.findall(r"\bt\('([a-z0-9_]+)'", app)) | set(re.findall(r'data-i18n="([a-z0-9_]+)"', app)) \
        | set(re.findall(r"\btl\(\w+, '([a-z0-9_]+)'", app))
    dyn = {f"cat_{c}" for c in ("good", "moderate", "usg", "unhealthy", "very", "hazardous")} \
        | {f"cat_{c}_{p}" for c in ("good", "moderate", "usg", "unhealthy", "very", "hazardous") for p in ("general", "sensitive")} \
        | {f"prof_{p}" for p in ("general", "sensitive")} | {f"v_{v}" for v in ("yes", "light", "no")} \
        | {"r_ok", "r_usg", "r_unhealthy", "r_nodata", "pick_now", "pick_worst", "vent_now", "vent_later", "vent_short",
           "src_live", "src_cache", "src_snapshot", "sn_live", "sn_cache", "sn_snapshot", "inv_yes", "inv_no", "inv_stable",
           "r_past", "hero_pe", "vent_plan", "vent_plan_air", "closed_later", "de_peak_under", "de_peak_ok", "test_period"} \
        | {f"f_{f}" for f in ("log_pm_now", "log_cams", "inversion", "wind", "hour")} \
        | {f"d_{d}" for d in ("almaly", "auezov", "bostandyk", "zhetysu", "medeu", "turksib", "alatau", "nauryzbay")}
    missing = (used | dyn) - ru
    assert not missing, missing


def test_advice_is_consistent():
    """Never 'air the room now' inside the closed-windows episode; the suggested airing hour is outside it."""
    for name, case in out()["consistency"].items():
        for c in case:
            bad = set(c["bad"])
            if c["first"] == "vent_now":
                assert c["now"] not in bad, (name, c)
            if c["vent"] is not None:
                assert c["vent"] not in bad, (name, c)


def test_offline_chain():
    o = jsc("tests/offline_harness.mjs", "--", "data/snapshot.json", "data/sensors_snapshot.json")
    assert o == {"fcOffline": "snapshot", "snOffline": "snapshot", "fcOnline": "live", "snOnline": "live",
                 "fcCached": "cache", "snCached": "cache"}, o


if __name__ == "__main__":
    if not pathlib.Path(JSC).exists():
        print("SKIPPED: JavaScriptCore (jsc) not found - JS logic NOT tested")
        sys.exit(2)
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
