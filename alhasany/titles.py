"""اقتراح العنوان من Gemini (مجاني بمفتاح كل جهاز). لو مفيش مفتاح: الواجهة بتنسخ البرومبت لأي شات."""
import json
import urllib.error
import urllib.request

from .config import load_secrets, load_settings


class TitleError(Exception):
    pass


def suggest(prompt):
    key = (load_secrets().get("gemini_key") or "").strip()
    if not key:
        raise TitleError("مفتاح Gemini مش متسجل — حطه من الإعدادات، أو استخدم «انسخ البرومبت»")
    model = load_settings().get("gemini_model") or "gemini-2.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.3}}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=90))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:300]
        raise TitleError(f"Gemini رفض الطلب ({e.code}): {msg}") from e
    except OSError as e:
        raise TitleError(f"مفيش اتصال بـ Gemini ({e})") from e
    try:
        text = r["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise TitleError("Gemini مرجّعش عنوان") from e
    lines = [l.strip(" *#-«»\"") for l in text.splitlines() if l.strip()]
    title = lines[0].replace("العنوان:", "").strip() if lines else ""
    return {"title": title, "summary": " ".join(lines[1:])[:300], "raw": text}
