"""Frame recorder: a stream of real screenshots with timestamps -> mp4 (Playwright screencast tears on scroll)."""
import json
import os
import pathlib
import shutil
import subprocess
import time

SUB = pathlib.Path(__file__).resolve().parent.parent
FF = "/Users/zhumat/.local/bin/ffmpeg"
PROD = "https://taza-tynys.vercel.app/"
BUILD = SUB / "build"


def durations():
    return json.loads((BUILD / "audio" / "durations.json").read_text())


class Rec:
    def __init__(self, pg, name, scroller=None):
        self.pg, self.name = pg, name
        self.scroller = scroller or pg  # page or frame whose window scrolls
        self.dir = BUILD / "rec" / f"frames_{name}"
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True)
        self.fr = []
        self.t0 = time.monotonic()

    def snap(self):
        p = self.dir / f"f{len(self.fr):04d}.png"
        self.pg.screenshot(path=str(p))
        self.fr.append((p, time.monotonic() - self.t0))

    def hold(self, sec, live=True):
        """Keep capturing (so CSS transitions and late renders are not lost)."""
        end = time.monotonic() + sec
        self.snap()
        while time.monotonic() < end:
            if live:
                self.snap()
            else:
                time.sleep(0.02)

    def scroll(self, y, sec=1.2):
        y0 = self.scroller.evaluate("window.scrollY")
        n = max(1, int(sec / 0.09))
        for i in range(1, n + 1):
            k = i / n
            e = k * k * (3 - 2 * k)
            self.scroller.evaluate(f"window.scrollTo(0,{y0 + (y - y0) * e})")
            self.snap()

    def click(self, sel, after=0.6):
        self.scroller.click(sel) if hasattr(self.scroller, "click") else self.pg.click(sel)
        end = time.monotonic() + after
        while time.monotonic() < end:
            self.snap()

    def top(self, sel, off=16):
        return self.scroller.evaluate(
            f'(()=>{{const e=document.querySelector("{sel}");return Math.max(0,e.getBoundingClientRect().top+window.scrollY-{off})}})()')

    def at(self, t):
        """Hold until t seconds since start."""
        rem = t - (time.monotonic() - self.t0)
        if rem > 0:
            self.hold(rem)

    def until(self, t):
        self.at(t)
        self.snap()

    def encode(self):
        lines = []
        for i, (f, t) in enumerate(self.fr):
            nt = self.fr[i + 1][1] if i + 1 < len(self.fr) else t + 0.04
            lines.append(f"file '{os.path.abspath(f)}'\nduration {max(0.001, nt - t):.4f}\n")
        lines.append(f"file '{os.path.abspath(self.fr[-1][0])}'\n")
        lst = BUILD / "rec" / f"frames_{self.name}.txt"
        lst.write_text("".join(lines))
        out = BUILD / "rec" / f"{self.name}.mp4"
        subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-vf", "scale=1280:720:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18", str(out)], check=True)
        shutil.rmtree(self.dir, ignore_errors=True)
        lst.unlink()
        print(self.name, "frames", len(self.fr), "span", round(self.fr[-1][1], 2))
        return out
