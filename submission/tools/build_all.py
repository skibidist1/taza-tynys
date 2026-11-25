"""One command to rebuild the whole package from production and team.json.

  python3 tools/build_all.py          # docs + screenshots + slides + audio + recordings + cards + video
  python3 tools/build_all.py --docs   # only DEFENSE.md, DESCRIPTION.md and the README note
  python3 tools/build_all.py --video  # reuse screenshots, rebuild slides, audio (voice/ first), recordings and video

Needs: Python Playwright + Chromium, ffmpeg/ffprobe, macOS `say` (only for segments without a live voice file).
"""
import pathlib
import subprocess
import sys

T = pathlib.Path(__file__).resolve().parent


def run(script, *args):
    print(f"\n== {script} {' '.join(args)}")
    subprocess.run([sys.executable, str(T / script), *args], check=True, cwd=T)


def main():
    run("docs.py")
    if "--docs" in sys.argv:
        return
    if "--video" not in sys.argv:
        run("shots.py")
    run("render.py")
    run("make_audio.py")
    run("hook.py")
    run("record_demo.py")
    run("cards.py")
    run("build_video.py")


if __name__ == "__main__":
    main()
