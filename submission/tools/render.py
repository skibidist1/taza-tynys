"""Slides: fill team.json blocks, check for placeholders and overflow, export PNGs and slides.pdf.

Usage: python3 tools/render.py   -> build/slides/slide_NN.png, slides.pdf
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from team import SUB, leftovers, load  # noqa: E402

FILL = """(f) => {
  document.querySelectorAll('[data-field]').forEach((e) => { e.textContent = f[e.dataset.field] || ''; });
  document.querySelectorAll('[data-if]').forEach((e) => e.classList.toggle('on', !!f[e.dataset.if]));
  document.querySelectorAll('[data-unless]').forEach((e) => e.classList.toggle('off', !!f[e.dataset.unless]));
}"""


def main():
    out = SUB / "build" / "slides"
    out.mkdir(parents=True, exist_ok=True)
    f = load()
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto((SUB / "slides.html").as_uri())
        pg.wait_for_timeout(800)
        pg.evaluate(FILL, f)
        text = pg.inner_text("body")
        bad = leftovers(text)
        if bad:
            sys.exit(f"placeholders visible on slides: {bad}")
        over = pg.evaluate("""[...document.querySelectorAll('.slide')].map((s,i)=>{const r=s.getBoundingClientRect();
          const bad=[...s.querySelectorAll('*')].filter(e=>{const q=e.getBoundingClientRect();return q.width&&(q.bottom>r.bottom-20||q.right>r.right+1)});
          return bad.length?i+1:0}).filter(Boolean)""")
        if over:
            print("WARNING: content near/over the edge on slides", over)
        n = pg.locator(".slide").count()
        for i in range(n):
            pg.locator(".slide").nth(i).screenshot(path=str(out / f"slide_{i + 1:02d}.png"))
        pg.pdf(path=str(SUB / "slides.pdf"), width="1920px", height="1080px", print_background=True, prefer_css_page_size=True)
        b.close()
    print("slides", n, "->", out, "+ slides.pdf")


if __name__ == "__main__":
    main()
