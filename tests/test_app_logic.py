"""App logic on the offline snapshot: normalisation, windows, actions, school mode, i18n keys.

Runs the real browser modules (js/*.js) with macOS JavaScriptCore.
Run: python3 tests/test_app_logic.py
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSC = "/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc"


def run():
    if not pathlib.Path(JSC).exists():
        print("SKIP: jsc not found")
        sys.exit(0)
    r = subprocess.run([JSC, "-m", "tests/app_harness.mjs", "--", "data/snapshot.json", "data/model.json"],
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
    for d in out()["school"]:
        assert len(d["verdicts"]) == 8
        assert all(x in ("yes", "light", "no", None) for x in d["verdicts"])


def test_i18n_keys_complete_and_used():
    k = out()["keys"]
    assert set(k["ru"]) == set(k["kk"]), set(k["ru"]) ^ set(k["kk"])
    app = (ROOT / "js" / "app.js").read_text() + (ROOT / "index.html").read_text()
    used = set(re.findall(r"\bt\('([a-z0-9_]+)'", app)) | set(re.findall(r'data-i18n="([a-z0-9_]+)"', app))
    missing = used - set(k["ru"])
    assert not missing, missing


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
