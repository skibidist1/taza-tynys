"""Video hook (first ~12 s): the live product on a big phone — winter example, station 125 vs CAMS 41 -> PE indoors.

Records a stage page with the production app in a phone-sized iframe and captions that appear in sync.
Usage: python3 tools/hook.py  -> build/rec/s1_hook.mp4
"""
from playwright.sync_api import sync_playwright

from recorder import PROD, Rec, durations

STAGE = """<html><head><meta charset="utf-8"><style>
body{margin:0;width:1280px;height:720px;overflow:hidden;font-family:ui-rounded,"SF Pro Rounded",system-ui,-apple-system,Arial,sans-serif;color:#15302b;
background:radial-gradient(900px 500px at 100% 0%,rgba(159,216,200,.6),transparent 60%),linear-gradient(180deg,#f7faf9,#eef4f2)}
.phone{position:absolute;left:150px;top:14px;width:410px;height:692px;box-sizing:border-box;border-radius:46px;background:#15302b;padding:10px;box-shadow:0 30px 60px -30px rgba(21,48,43,.6)}
.phone iframe{width:390px;height:672px;border:0;border-radius:36px;background:#fff;display:block}
.cap{position:absolute;left:640px;width:560px;opacity:0;transform:translateY(14px);transition:all .45s ease}
.cap.on{opacity:1;transform:none}
.k{font-size:30px;color:#4d6661}.v{font-size:120px;font-weight:800;line-height:1;letter-spacing:-3px}
.pill{display:inline-block;font-size:44px;font-weight:800;padding:12px 28px;border-radius:999px;background:#f6d6d1;color:#7a2418}
.small{font-size:26px;color:#4d6661}
</style></head><body>
<div class="phone"><iframe id="app" src="URL"></iframe></div>
<div class="cap" id="c1" style="top:70px"><div class="k">Станция у школы, PM2.5</div><div class="v" style="color:#b04a3c">125</div></div>
<div class="cap" id="c2" style="top:250px"><div class="k">Модель Copernicus CAMS</div><div class="v">41</div></div>
<div class="cap" id="c3" style="top:440px"><span class="pill">→ физкультура в зале</span></div>
<div class="cap" id="c4" style="top:560px"><div class="small">6 февраля 2025, 09:00 · реальный архив</div></div>
</body></html>"""


def main():
    D = durations()["s1_hook"] + 0.6
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, color_scheme="light")
        pg = ctx.new_page()
        pg.set_content(STAGE.replace("URL", PROD + "?demo=winter#today"))
        pg.wait_for_timeout(500)
        app = next(f for f in pg.frames if "taza-tynys" in f.url)
        app.wait_for_selector("#hero .value", timeout=30000)
        pg.wait_for_timeout(2500)
        # close-up crop: hide the page header so the number and the decision fill the phone
        app.evaluate("""() => { const st = document.createElement('style');
          st.textContent = '.top,.status,.tabs{display:none!important} .demo-eval{display:none!important} main{padding-top:6px}';
          document.head.appendChild(st); window.scrollTo(0, 0); }""")
        pg.wait_for_timeout(400)
        r = Rec(pg, "s1_hook", scroller=app)
        show = lambda i: pg.evaluate(f"document.getElementById('c{i}').classList.add('on')")  # noqa: E731
        r.hold(0.6); show(1); r.at(2.6)
        show(2); r.at(4.8)
        show(3); r.at(7.0)
        show(4)
        r.scroll(r.top(".scale-card", 8), 1.6)
        r.until(D)
        r.encode()
        b.close()


if __name__ == "__main__":
    main()
