"""Build DEFENSE.md and DESCRIPTION.md from tools/templates/ + team.json; update the README interview note.

Usage: python3 tools/docs.py   (run from anywhere)
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from team import SUB, leftovers, load, render  # noqa: E402

README = SUB.parent / "README.md"
NOTE = ("- Интервью с завучами и учителями физкультуры пока не проводились: пороги и решения опираются на документы US EPA и ВОЗ, "
        "а не на опрос пользователей. Это первый шаг пилота.")


VIS = {"hook": "Живой кадр продукта: телефон крупно, зимний пример — «125», «CAMS 41», «Физкультура в этот час: в зале»",
       "rec": "Запись прода (?demo=winter)", "card:rule": "Карточка: сколько грязных часов поймано (87 / 72 / 60 / 40%)",
       "card:final": "Финальная карточка: название и ссылка (светлый кадр, без затемнения)"}
SCENE = {"s3_now": "вкладка «Сейчас»: цифра, карта датчиков", "s4_strip": "лента 48 часов, нажатия на часы, серые точки факта",
         "s5_why": "вкладка «Почему» → «Худший час прогноза»", "s6_school": "вкладка «Школа»: урок → «в зале», объявление ru/kk, «Скопировать»"}


def pitch_script():
    segs = json.loads((SUB / "tools" / "narration.json").read_text(encoding="utf-8"))
    dp = SUB / "build" / "audio" / "durations.json"
    durs = json.loads(dp.read_text()) if dp.exists() else {}
    rows, t = [], 0.0
    for sgm in segs:
        k, v = sgm["key"], sgm["visual"]
        d = durs.get(k)
        when = f"{int(t // 60)}:{int(t % 60):02d}" if d else "—"
        if d:
            t += d + 0.6
        what = VIS.get(v) or (f"Слайд {v.split(':')[1]}" if v.startswith("slide:") else v)
        if v == "rec":
            what += f": {SCENE.get(k, '')}"
        rows.append(f"| {when} | `{k}` | {what} | {sgm['text']} |")
    vid = SUB / "pitch.mp4"
    if vid.exists():
        import subprocess
        t = float(subprocess.run(["/Users/zhumat/.local/bin/ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vid)],
                                 capture_output=True, text=True).stdout or 0)
    total = f"{int(t // 60)}:{int(t % 60):02d}" if t else "—"
    return f"""# Таза Тыныс — сценарий питч-видео (≤ 2:55)

Этот файл собирается из `tools/narration.json` командой `python3 tools/build_all.py --docs`. Текст озвучки правьте в `narration.json`.

Сейчас `pitch.mp4` озвучено системным голосом macOS (Milena), длительность около {total}. Живой голос команды звучит лучше — запишите его по блокам ниже.

## Как переозвучить своим голосом (15 минут)

1. Запишите каждый блок отдельным файлом на телефон (диктофон), в тихой комнате, телефон в 20–30 см ото рта. Читайте текст из таблицы как есть; паузы в начале и конце обрежутся сами.
2. Назовите файл ключом блока и положите в `submission/voice/`: например `voice/s1_hook.m4a`, `voice/s2_problem.m4a` (подходят `.m4a`, `.wav`, `.mp3`). Можно записать не все блоки — для остальных останется синтез.
3. Пересоберите одной командой из папки `submission/`: `python3 tools/build_all.py --video`. Скрипт подхватит ваши файлы, выровняет громкость, перезапишет демо под длину вашего голоса и проверит, что видео не длиннее 2:55.
4. Совет: хук (`s1_hook`) лучше всего звучит голосом учителя или завуча, если команда с ним говорила; не обещайте того, чего нет (рассылки в WhatsApp и пилота пока нет — это «следующий шаг»).

## Блоки

| Начало | Ключ (имя файла) | Что в кадре | Текст для голоса |
|---|---|---|---|
""" + "\n".join(rows) + """

## Откуда цифры

- 34% / 18% / 16% / 32% — кейс (Bizmedia), `docs/CASE.md`.
- «в 3,2 раза» (CAMS медиана 40 при станции > 100, медиана 127, 201 час) — `evals/forecast_report.md`.
- 125 / 41, пик 151 при факте 223, инверсия +6,7 °C, ветер 1,3 м/с, 13 из 13 уроков — зимний пример на проде (`?demo=winter`).
- MAE 17,9 / 23,7 / 22,7; пойманные грязные часы 87% / 72% / 60% / 40% — `evals/forecast_report.md`, `data/forecast_model.json`.

## Пересборка всего пакета

`python3 tools/build_all.py` — тексты (`DEFENSE.md`, `DESCRIPTION.md` из `team.json`), скриншоты с прода, слайды и `slides.pdf`, озвучка, живой хук, запись демо, карточки, склейка `pitch.mp4`. Нужны Playwright с Chromium и ffmpeg. Временные файлы — в `submission/build/` (не коммитится).
"""


def main():
    f = load()
    (SUB / "pitch_script.md").write_text(pitch_script(), encoding="utf-8")
    bad = []
    for name in ("DEFENSE.md", "DESCRIPTION.md"):
        out = render((SUB / "tools" / "templates" / name).read_text(encoding="utf-8"), f)
        bad += [(name, x) for x in leftovers(out)]
        (SUB / name).write_text(out, encoding="utf-8")
    # honest note about interviews lives only in README "Ограничения" (and DEFENSE.md)
    r = README.read_text(encoding="utf-8")
    block = f"<!-- team:interviews -->\n{NOTE if not f['interviews'] else ''}\n<!-- /team:interviews -->"
    r2 = re.sub(r"<!-- team:interviews -->.*?<!-- /team:interviews -->", block, r, flags=re.S)
    if r2 == r and "<!-- team:interviews -->" not in r:
        r2 = r.replace("## Ограничения\n\n", "## Ограничения\n\n" + block + "\n", 1)
    README.write_text(r2, encoding="utf-8")
    if bad:
        print("PLACEHOLDERS LEFT:", bad)
        sys.exit(1)
    print("docs: DEFENSE.md, DESCRIPTION.md, README interview note", "(interviews given)" if f["interviews"] else "(no interviews)")


if __name__ == "__main__":
    main()
