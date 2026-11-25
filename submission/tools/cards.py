"""Video-only cards (not in the deck): 'lessons' (dirty lessons that would go outdoors, CAMS vs model) and 'final' (title + link, light, no black frame).

Numbers come from data/forecast_model.json; team line from team.json (hidden if empty).
Usage: python3 tools/cards.py  -> build/cards/lessons.png, final.png
"""
import html
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from team import SUB, load  # noqa: E402

CSS = """
body{margin:0;font-family:ui-rounded,"SF Pro Rounded",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;color:#15302b}
.c{width:1920px;height:1080px;box-sizing:border-box;padding:110px 130px;display:flex;flex-direction:column;justify-content:center;
background:radial-gradient(1200px 700px at 100% 0%,rgba(159,216,200,.55),transparent 60%),linear-gradient(180deg,#f7faf9,#eef4f2)}
h2{font-size:64px;margin:0 0 50px;letter-spacing:-1px}
.bars{display:grid;gap:26px}
.r2{display:grid;grid-template-columns:360px 1fr 160px;align-items:center;gap:28px;font-size:46px}
.r{display:grid;grid-template-columns:560px 1fr 1fr 1fr;align-items:center;gap:28px;font-size:38px}
.t{height:64px;border-radius:18px;background:rgba(21,48,43,.08);overflow:hidden}.t i{display:block;height:100%;border-radius:18px}
.v{font-weight:800;font-size:56px;text-align:right}
.n{font-size:30px;color:#4d6661;margin-top:44px;max-width:1500px;line-height:1.35}
.hl{font-weight:800}
h1{font-size:150px;margin:0 0 26px;letter-spacing:-3px}
.lead{font-size:50px;margin:0 0 60px;max-width:1500px;line-height:1.25}
.url{font-size:72px;font-weight:800;color:#2f7d6d}
.team{font-size:36px;color:#4d6661;margin-top:34px}
"""


def main():
    out = SUB / "build" / "cards"
    out.mkdir(parents=True, exist_ok=True)
    L = json.loads((SUB.parent / "evals" / "school_lessons.json").read_text())
    K, o, ind = L["dirty"], L["outdoors_dirty"], L["indoor_share"]
    rows = [("CAMS", o["cams"], "#db6f60"), ("Таза Тыныс", o["model"], "#2f9f88")]
    bars = "".join(
        f'<div class="r2"><span class="{"hl" if i else ""}">{html.escape(n)}</span><span class="t"><i style="width:{100 * v / K:.1f}%;background:{c}"></i></span><span class="v">{v}</span></div>'
        for i, (n, v, c) in enumerate(rows))
    rule = f'''<div class="c"><h2>Грязные уроки физкультуры, которые вышли бы на улицу</h2>
      <p class="n" style="margin:-20px 0 40px">Тестовый период, будни 8–15 ч: из {K} уроков с воздухом выше порога 35,4 мкг/м³ (решение за сутки)</p><div class="bars">{bars}</div>
      <p class="n">Честно: Таза Тыныс чаще отправляет в зал, {ind["model"] * 100:.0f}% уроков против {ind["cams"] * 100:.0f}% у CAMS. Если сдвинуть порог CAMS до той же доли, он пропустит {o["cams_equal_share"]}. Одна станция, шум CAMS — допущение.</p></div>'''
    f = load()
    team = " · ".join(x for x in [f"команда {html.escape(f['team'])}" if f["team"] else "", html.escape(f["members"]), html.escape(f["contact"])] if x)
    final = f'''<div class="c"><h1>Таза Тыныс</h1><p class="lead">Про физкультуру решает реальный воздух, а не догадка.</p>
      <div class="url">taza-tynys.vercel.app</div>{f'<div class="team">{team}</div>' if team else ''}
      <div class="team">Órleu Hack 2026 · Кейс 1 «Экология Казахстана»</div></div>'''
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in (("lessons", rule), ("final", final)):
            pg.set_content(f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>")
            pg.wait_for_timeout(200)
            pg.screenshot(path=str(out / f"{name}.png"))
        b.close()
    print("cards ->", out)


if __name__ == "__main__":
    main()
