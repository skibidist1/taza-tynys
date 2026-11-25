"""Video-only cards (not in the deck): 'rule' (caught dirty hours at equal indoor share) and 'final' (title + link, light, no black frame).

Numbers come from data/forecast_model.json; team line from team.json (hidden if empty).
Usage: python3 tools/cards.py  -> build/cards/rule.png, final.png
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
    m = json.loads((SUB.parent / "data" / "forecast_model.json").read_text())["metrics"]
    d = m["school_hours"]["decisions"]
    rows = [("Наша модель", d["model"], "#2f9f88", True), ("«Будет как сейчас»", d["persistence"], "#c4cfcc", False),
            ("CAMS", d["cams"], "#db6f60", False)]
    head = '<div class="r"><span></span>' + "".join(f'<span class="v" style="font-size:36px;text-align:center">{k}% уроков в зале</span>' for k in ("30", "40", "50")) + "</div>"
    bars = head + "".join(
        f'<div class="r"><span class="{"hl" if hl else ""}">{html.escape(n)}</span>'
        + "".join(f'<span class="v" style="text-align:center;background:{c};border-radius:18px;padding:8px 0;color:#15302b">{x["recall_at_share"][k]*100:.0f}%</span>' for k in ("30", "40", "50"))
        + '</div>' for n, x, c, hl in rows)
    rule = f'''<div class="c"><h2>Сколько грязных часов поймано <span style="font-size:40px;color:#4d6661;font-weight:500;white-space:nowrap">(факт выше 35,4 мкг/м³)</span></h2>
      <p class="n" style="margin:-20px 0 30px">Честное сравнение: при одинаковой доле уроков в зале</p><div class="bars">{bars}</div>
      <p class="n">Отрыв модели 4–7 пунктов, интервалы перекрываются. Тест строго позже обучения, станция OpenAQ 8876. Датчик «сейчас» учитывается только на ближайшие 3 часа, дальше решает прогноз.</p></div>'''
    f = load()
    team = " · ".join(x for x in [f"команда {html.escape(f['team'])}" if f["team"] else "", html.escape(f["members"]), html.escape(f["contact"])] if x)
    final = f'''<div class="c"><h1>Таза Тыныс</h1><p class="lead">Про физкультуру решает реальный воздух, а не догадка.</p>
      <div class="url">taza-tynys.vercel.app</div>{f'<div class="team">{team}</div>' if team else ''}
      <div class="team">Órleu Hack 2026 · Кейс 1 «Экология Казахстана»</div></div>'''
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in (("rule", rule), ("final", final)):
            pg.set_content(f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>")
            pg.wait_for_timeout(200)
            pg.screenshot(path=str(out / f"{name}.png"))
        b.close()
    print("cards ->", out)


if __name__ == "__main__":
    main()
