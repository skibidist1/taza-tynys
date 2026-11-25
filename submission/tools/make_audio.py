"""Narration audio: live voice from voice/<key>.m4a|.wav|.mp3 if present, otherwise macOS `say` (Milena).

Writes build/audio/<key>.wav and build/audio/durations.json.
Usage: python3 tools/make_audio.py
"""
import json
import pathlib
import subprocess

SUB = pathlib.Path(__file__).resolve().parent.parent
FF, FP = "/Users/zhumat/.local/bin/ffmpeg", "/Users/zhumat/.local/bin/ffprobe"
OUT = SUB / "build" / "audio"


def dur(p):
    return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    segs = json.loads((SUB / "tools" / "narration.json").read_text(encoding="utf-8"))
    durs, src = {}, {}
    for s in segs:
        k = s["key"]
        live = next((SUB / "voice" / f"{k}.{ext}" for ext in ("m4a", "wav", "mp3") if (SUB / "voice" / f"{k}.{ext}").exists()), None)
        wav = OUT / f"{k}.wav"
        if live:
            # trim silence at both ends, normalise loudness
            af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
                  "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,loudnorm=I=-16:TP=-1.5")
            subprocess.run([FF, "-y", "-v", "error", "-i", str(live), "-af", af, "-ar", "48000", "-ac", "2", str(wav)], check=True)
            src[k] = f"voice/{live.name}"
        else:
            aiff = OUT / f"{k}.aiff"
            subprocess.run(["say", "-v", "Milena", "-r", "178", "-o", str(aiff), s["text"]], check=True)
            subprocess.run([FF, "-y", "-v", "error", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(wav)], check=True)
            aiff.unlink()
            src[k] = "say Milena"
        durs[k] = round(dur(wav), 3)
        print(f"{k:12s} {durs[k]:6.2f}s  {src[k]}")
    (OUT / "durations.json").write_text(json.dumps(durs, indent=1))
    print("total", round(sum(durs.values()), 1), "s")


if __name__ == "__main__":
    main()
