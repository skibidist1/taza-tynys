"""Almaty district boundaries for the map underlay: OSM via Overpass -> simplified rings.

Writes data/almaty_districts.json  (© OpenStreetMap contributors, ODbL).
Usage: python3 pipeline/make_districts.py
"""
import json
import math
import time
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CITY_REL = 2465058  # Алматы (KZ-75)
QUERY = f"""[out:json][timeout:120];
rel({CITY_REL});map_to_area->.city;
rel(area.city)["boundary"="administrative"]["admin_level"="6"];
out geom;"""
EPS = 0.0015  # degrees, ~150 m


MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]


def overpass(q):
    last = None
    for attempt in range(6):  # public Overpass servers are often busy
        url = MIRRORS[attempt % len(MIRRORS)]
        req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                     headers={"User-Agent": "taza-tynys-hackathon/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise last


def stitch(ways):
    """Join outer way segments into closed rings."""
    segs = [w[:] for w in ways if len(w) >= 2]
    rings = []
    while segs:
        ring = segs.pop(0)
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring += s[1:]
                elif s[-1] == ring[-1]:
                    ring += s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                changed = True
                break
        rings.append(ring)
    return rings


def dp(pts, eps):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        num = abs((b[1] - a[1]) * (a[0] - p[0]) - (a[1] - p[1]) * (b[0] - a[0]))
        den = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-12
        d = num / den
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return dp(pts[: idx + 1], eps)[:-1] + dp(pts[idx:], eps)
    return [a, b]


def simplify_ring(r):
    """Douglas-Peucker on a closed ring: split it at the vertex farthest from the start first."""
    if len(r) < 4:
        return r
    k = max(range(len(r)), key=lambda i: (r[i][0] - r[0][0]) ** 2 + (r[i][1] - r[0][1]) ** 2)
    return dp(r[: k + 1], EPS)[:-1] + dp(r[k:], EPS)


def main():
    d = overpass(QUERY)
    out = []
    for e in d["elements"]:
        ways = [[(round(g["lat"], 5), round(g["lon"], 5)) for g in m["geometry"]]
                for m in e.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
        rings = [simplify_ring(r) for r in stitch(ways)]
        rings = [[[round(a, 4), round(b, 4)] for a, b in r] for r in rings if len(r) >= 4]
        if rings:
            out.append({"name": e["tags"].get("name"), "name_kk": e["tags"].get("name:kk"), "rings": rings})
    res = {"source": "© OpenStreetMap contributors (ODbL)", "districts": sorted(out, key=lambda x: x["name"] or "")}
    (ROOT / "data" / "almaty_districts.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    print(len(out), "districts", sum(len(r) for x in out for r in x["rings"]), "points:", [x["name"] for x in out])


if __name__ == "__main__":
    main()
