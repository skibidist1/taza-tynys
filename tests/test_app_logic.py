"""App logic on the offline snapshot: normalisation, windows, actions, school mode, i18n keys.

Runs the real browser modules (js/*.js) with macOS JavaScriptCore.
Run: python3 tests/test_app_logic.py
"""
import json
import pathlib
import re
import subprocess
import sys

PROFILES = ("general", "child", "sensitive", "sport", "pregnancy")

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"


def run():
    if not pathlib.Path(JSC).exists():
        print("SKIP: jsc not found")
        sys.exit(0)
    r = subprocess.run([JSC, "-m", "tests/app_harness.mjs", "--", "data/snapshot.json", "data/model.json", "data/demo_winter.json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip(), r.stderr or r.stdout
    return json.loads(r.stdout)


OUT = None


def out():
    global OUT
    if OUT is None:
        OUT = run()
    return OUT


def test_normalize():
    o = out()
    assert o["n"] >= 96, o["n"]
    assert not o["stale"]
    assert o["n"] - o["nowIndex"] >= 72
    assert o["trapAll"]


def test_stale_replay():
    o = out()
    assert o["lateStale"] and o["lateNow"] == o["nowTime"]


def test_levels_match_who_steps():
    assert out()["levels"] == [0, 0, 1, 1, 2, 3, 3, 4, 5]


def test_actions_and_windows_per_profile():
    for p, v in out()["profiles"].items():
        assert len(v["actions"]) == 3, p
        assert v["actions"][2] == f"protect_{p}"
        assert v["windows"], p


def test_school():
    sch = out()["school"]
    assert sch, "no school days"
    for d in sch:
        for l in d["lessons"]:
            assert l["verdict"] in ("yes", "light", "no", None)
            if d["group"] == "junior":
                assert l["verdict"] != "light"  # juniors: outdoor or indoor only
            if l["verdict"] == "yes":
                assert l["pm"] <= 25 and not l["trap"]
            if l["trap"]:
                assert l["verdict"] == "no"
    # junior is never less strict than senior for the same lesson
    rank = {"yes": 0, "light": 1, "no": 2, None: -1}
    by = {(d["shift"], d["day"], d["group"]): d["lessons"] for d in sch}
    for (shift, day, g), ls in by.items():
        if g == "junior":
            for lj, ls_ in zip(ls, by[(shift, day, "senior")]):
                assert rank[lj["verdict"]] >= rank[ls_["verdict"]]


def test_school_winter_smog_day_goes_indoors():
    for verdicts in out()["winterSchool"]:
        assert verdicts.count("no") >= 4, verdicts


def test_i18n_keys_complete_and_used():
    k = out()["keys"]
    assert set(k["ru"]) == set(k["kk"]), set(k["ru"]) ^ set(k["kk"])
    app = (ROOT / "js" / "app.js").read_text() + (ROOT / "index.html").read_text()
    used = set(re.findall(r"\bt\('([a-z0-9_]+)'", app)) | set(re.findall(r'data-i18n="([a-z0-9_]+)"', app)) \
        | set(re.findall(r"\btl\(\w+, '([a-z0-9_]+)'", app)) | {"r_ok", "r_light", "r_pm", "r_trap", "r_rel", "r_nodata", "pick_now", "pick_worst"} \
        | {f"story_{a}_{b}" for a in ("wind", "temp", "blh") for b in ("up", "down", "n")} | {"story_hour_up", "story_hour_down"} \
        | {f"lvl_{k}" for k in ("aqg", "it4", "it3", "it2", "it1", "over")} | {f"rel_{k}" for k in ("best", "mid", "worst")} \
        | {f"prof_{k}" for k in PROFILES} | {f"protect_{k}" for k in PROFILES} | {f"act_{k}" for k in ("walk", "walk_child", "run")} \
        | {f"f_{k}" for k in ("wind", "temp", "blh", "hour", "weekend")} | {"f_val_weekend_0", "f_val_weekend_1"} \
        | {f"v_{k}" for k in ("yes", "light", "no")} | {"g_junior", "g_senior", "vent_now", "vent_later", "vent_short", "src_live", "src_cache", "src_snapshot", "src_archive", "copied", "copy_fail"}
    missing = used - set(k["ru"])
    assert not missing, missing


def test_offline_fallback_chain():
    r = subprocess.run([JSC, "-m", "tests/offline_harness.mjs", "--", "data/snapshot.json"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr or r.stdout
    o = json.loads(r.stdout)
    assert o["offlineNoCache"] == "snapshot", o
    assert o["online"] == "live" and o["cached"], o
    assert o["offlineWithCache"] == "cache", o


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
    print(json.dumps({k: v for k, v in out().items() if k != "keys"}, ensure_ascii=False)[:1500])
    sys.exit(1 if fails else 0)
