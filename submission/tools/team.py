"""team.json loader and a tiny template engine used by slides, video and docs.

Template syntax (one level, no nesting):
  {field}             value of the field (dotted paths allowed: quote.text)
  [[?field: text]]    text is kept only if field is non-empty
  [[!field: text]]    text is kept only if field is empty
Fields: team, members (joined with ", "), code_url, contact, quote.text, quote.author, interviews.
"""
import json
import pathlib
import re

SUB = pathlib.Path(__file__).resolve().parent.parent


def load():
    d = json.loads((SUB / "team.json").read_text(encoding="utf-8"))
    flat = {
        "team": (d.get("team") or "").strip(),
        "members": ", ".join(m.strip() for m in d.get("members") or [] if m and m.strip()),
        "code_url": (d.get("code_url") or "").strip(),
        "contact": (d.get("contact") or "").strip(),
        "quote.text": ((d.get("quote") or {}).get("text") or "").strip(),
        "quote.author": ((d.get("quote") or {}).get("author") or "").strip(),
        "interviews": (d.get("interviews") or "").strip(),
    }
    return flat


def render(text, f):
    def cond(m):
        neg, key, body = m.group(1) == "!", m.group(2), m.group(3)
        has = bool(f.get(key))
        return body if has != neg else ""
    text = re.sub(r"\[\[([?!])([\w.]+):(.*?)\]\]", cond, text, flags=re.S)
    text = re.sub(r"\{([a-z_]+(?:\.[a-z_]+)?)\}", lambda m: f.get(m.group(1), m.group(0)) if m.group(1) in f else m.group(0), text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text)  # a removed block must not leave a hole


def leftovers(text):
    """Visible placeholders that must never ship: {…} in Cyrillic/upper case or [[…]]."""
    return re.findall(r"\{[А-ЯЁA-Z][^}]*\}|\[\[[^\]]*\]\]", text)
