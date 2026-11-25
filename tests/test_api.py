"""api/sensors.py parsing robustness (offline, no network). Run: python3 tests/test_api.py"""
import json
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
import sensors  # noqa: E402

NOW = datetime(2026, 11, 25, 10, 0, tzinfo=sensors.ALMATY)


def page(rows):
    return "<script>var sensors_data = " + json.dumps(rows) + "</script>"


def row(**kw):
    base = {"id": "1", "name": "A", "lat": "43.25", "lng": "76.9", "pm25": "20", "date": "2026-11-25 09:55:00", "hour": "now"}
    base.update(kw)
    return base


def test_bad_hour_and_bad_rows_do_not_break():
    rows = [row(), row(hour="99", pm25="30"), row(hour="-3"), row(lat="x"), {"junk": 1}, row(hour="8", pm25="25"), row(hour="9", pm25="999")]
    out = sensors.parse_airkaz(page(rows), NOW)
    s = [x for x in out if x["id"] == "ak-1"][0]
    assert s["pm25"] == 20.0
    assert s["history"] == [["2026-11-25T08:00", 25.0]], s["history"]


def test_missing_marker_raises():
    try:
        sensors.parse_airkaz("<html>no data</html>", NOW)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_sc_out_of_range_is_suspect():
    data = [{"sensor": {"id": 7, "sensor_type": {"name": "SDS011"}}, "location": {"latitude": "43.2", "longitude": "76.9"},
             "timestamp": "2026-11-25 04:50:00", "sensordatavalues": [{"value_type": "P2", "value": "999.9"}]},
            {"sensor": {"id": 8, "sensor_type": {"name": "SPS30"}}, "location": {"latitude": "43.2", "longitude": "76.9"},
             "timestamp": "2026-11-25 04:50:00", "sensordatavalues": [{"value_type": "P2", "value": "12.5"}]}]
    out = {s["id"]: s for s in sensors.parse_sc(json.dumps(data), NOW)}
    assert out["sc-7"]["suspect"] and out["sc-7"]["pm25"] is None
    assert not out["sc-8"]["suspect"] and out["sc-8"]["pm25"] == 12.5


def test_both_sources_down_gives_errors():
    orig = sensors._get
    sensors._get = lambda url, timeout=6: (_ for _ in ()).throw(OSError("down"))
    try:
        d = sensors.collect()
    finally:
        sensors._get = orig
    assert d["liveCount"] == 0 and len(d["errors"]) == 2


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
