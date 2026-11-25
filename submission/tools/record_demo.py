"""Product demo scenes from production (?demo=winter), timed to the narration.

Usage: python3 tools/record_demo.py  -> build/rec/<key>.mp4 for s3_now, s4_strip, s5_why, s6_school
"""
import time

from playwright.sync_api import sync_playwright

from recorder import PROD, Rec, durations

CSS = "nav.tabs,.tabs{position:static!important} html{scroll-behavior:auto!important}"


def scene_now(r, D):
    r.hold(D * 0.30)
    r.scroll(r.top("#place"), 1.4)
    r.hold(D * 0.25)
    r.scroll(0, 1.4)
    r.until(D)


def scene_strip(r, D):
    r.scroll(r.top(".scale-card"), 1.0)
    r.hold(2.0)
    step = (D - 3.5) / 5
    for i in [35, 38, 42, 50, 58]:
        t = time.monotonic()
        r.click(f'#strip button[data-i="{i}"]', 0.4)
        r.hold(max(0.1, step - (time.monotonic() - t)))
    r.until(D)


def scene_why(r, D):
    r.hold(0.6)
    r.click("[data-tab=why]", 0.8)
    r.hold(0.8)
    r.click("text=Худший час прогноза", 0.6)
    r.hold(D * 0.42)
    r.scroll(r.top("#view-why .card:nth-of-type(2)", 70), 1.4)
    r.until(D)


def scene_school(r, D):
    r.hold(0.6)
    r.click("[data-tab=school]", 0.6)
    r.hold(0.8)
    r.scroll(r.top("#view-school .card", 0) + 300, 1.0)
    cb = "#view-school input[type=checkbox] >> nth=2"
    r.click(cb, 0.8)
    r.hold(0.6)
    r.click(cb, 0.8)
    r.hold(2.0)
    r.scroll(r.top("#view-school .card:nth-of-type(2)", 10), 1.4)
    r.hold(1.6)
    r.click("text=Скопировать на русском", 0.6)
    r.hold(1.4)
    r.scroll(r.pg.evaluate("window.scrollY") + 330, 1.2)
    r.until(D)


SCENES = [("s3_now", scene_now), ("s4_strip", scene_strip), ("s5_why", scene_why), ("s6_school", scene_school)]


def main():
    dur = durations()
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, fn in SCENES:
            D = dur[name] + 0.6
            ctx = b.new_context(viewport={"width": 1024, "height": 576}, device_scale_factor=1.25, color_scheme="light",
                                permissions=["clipboard-read", "clipboard-write"])
            pg = ctx.new_page()
            pg.goto(PROD + "?demo=winter", wait_until="networkidle")
            pg.add_style_tag(content=CSS)
            pg.wait_for_timeout(2500)
            r = Rec(pg, name)
            fn(r, D)
            ctx.close()
            r.encode()
        b.close()


if __name__ == "__main__":
    main()
