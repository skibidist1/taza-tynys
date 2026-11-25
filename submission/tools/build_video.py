"""Assemble pitch.mp4 from narration (build/audio), recordings (build/rec), slides (build/slides) and cards (build/cards).

Rules: hook is live product footage; metric tables stay <= 10 s; the last frame is the light title card (no black tail).
Usage: python3 tools/build_video.py  -> pitch.mp4 (checks duration <= 175 s with ffprobe)
"""
import json
import pathlib
import subprocess
import sys

SUB = pathlib.Path(__file__).resolve().parent.parent
B = SUB / "build"
FF, FP = "/Users/zhumat/.local/bin/ffmpeg", "/Users/zhumat/.local/bin/ffprobe"
LIMIT = 175.0


def dur(p):
    return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    segs = json.loads((SUB / "tools" / "narration.json").read_text(encoding="utf-8"))
    durs = json.loads((B / "audio" / "durations.json").read_text())
    parts, total = [], 0.0
    (B / "parts").mkdir(exist_ok=True)
    vf = "scale=1280:720:flags=lanczos,format=yuv420p,fps=30"
    for s in segs:
        k, vis = s["key"], s["visual"]
        a = durs[k]
        D = a + 0.6
        if vis.startswith("slide:7"):
            D = min(a + 0.35, 10.0)  # metric table: keep it short
        if vis == "card:final":
            D = a + 2.2  # hold the title card, no fade to black
        af = f"adelay=300|300,apad,atrim=0:{D:.3f},aformat=sample_rates=48000:channel_layouts=stereo"
        aud = ["-i", str(B / "audio" / f"{k}.wav")]
        o = B / "parts" / f"{k}.mp4"
        if vis in ("hook", "rec"):
            src = B / "rec" / f"{k}.mp4"
            cmd = [FF, "-y", "-v", "error", "-i", str(src)] + aud + [
                "-filter_complex", f"[0:v]{vf},tpad=stop_mode=clone:stop_duration=5[v];[1:a]{af}[a]"]
        else:
            if vis.startswith("slide:"):
                img = B / "slides" / f"slide_{int(vis.split(':')[1]):02d}.png"
            else:
                img = B / "cards" / f"{vis.split(':')[1]}.png"
            # slow push-in so still images do not look frozen
            zoom = f"zoompan=z='min(1+0.0004*on,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(D*30)+30}:s=1920x1080:fps=30"
            cmd = [FF, "-y", "-v", "error", "-loop", "1", "-t", f"{D:.3f}", "-i", str(img)] + aud + [
                "-filter_complex", f"[0:v]{zoom},{vf}[v];[1:a]{af}[a]"]
        cmd += ["-map", "[v]", "-map", "[a]", "-t", f"{D:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(o)]
        subprocess.run(cmd, check=True)
        parts.append(o)
        total += D
        print(f"{k:12s} {vis:12s} {D:6.2f}s")
    lst = B / "parts" / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    out = SUB / "pitch.mp4"
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-crf", "21",
                    "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)], check=True)
    d = dur(out)
    print(f"pitch.mp4: planned {total:.1f}s, ffprobe {d:.2f}s ({int(d // 60)}:{d % 60:05.2f})")
    if d > LIMIT:
        sys.exit(f"too long: {d:.1f}s > {LIMIT}s")


if __name__ == "__main__":
    main()
