"""Save a real /api/sensors response as data/sensors_snapshot.json (offline / local-dev fallback)."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from sensors import collect  # noqa: E402

d = collect()
d["snapshot"] = True
(ROOT / "data" / "sensors_snapshot.json").write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))
print(d["fetchedAt"], "live", d["liveCount"], "median", d["median"], "errors", d["errors"])
for s in d["sensors"]:
    if s["live"]:
        print("  ", s["id"], s["name"], s["pm25"], s["updated"], len(s["history"]))
