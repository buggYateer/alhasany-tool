"""الربط بقناة تليجرام عن طريق البوت (توكن كل جهاز في secrets.json — مش على GitHub).

البوت مبيقدرش يقرا رسايل القناة القديمة مباشرة، فبنعمل الحيلة دي:
forward للرسالة لشات المسؤول مع البوت ← نقرا النص والتنسيق والملف ← نمسح النسخة على طول.
"""
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import load_secrets, load_settings, save_secrets


class TgError(Exception):
    pass


def _token():
    t = (load_secrets().get("bot_token") or "").strip()
    if not t:
        raise TgError("توكن البوت مش متسجل — حطه من الإعدادات")
    return t


def api(method, **params):
    data = urllib.parse.urlencode({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                                   for k, v in params.items() if v is not None}).encode()
    url = f"https://api.telegram.org/bot{_token()}/{method}"
    try:
        r = json.load(urllib.request.urlopen(url, data, timeout=60))
    except urllib.error.HTTPError as e:
        r = json.load(e)
    except OSError as e:
        raise TgError(f"مفيش اتصال بتليجرام ({e})") from e
    if not r.get("ok"):
        raise TgError(r.get("description", "خطأ من تليجرام"))
    return r["result"]


def channel():
    return load_settings()["channel"]


def admin_chat():
    """شات المسؤول مع البوت (لازم يكون داس Start). بنحفظه أول مرة."""
    sec = load_secrets()
    if sec.get("admin_chat_id"):
        return sec["admin_chat_id"]
    ups = api("getUpdates", allowed_updates=["message"])
    ids = [u["message"]["chat"]["id"] for u in ups if "message" in u and u["message"]["chat"]["type"] == "private"]
    if not ids:
        raise TgError("افتح البوت في تليجرام ودوس Start، وبعدين جرّب تاني")
    sec["admin_chat_id"] = ids[-1]
    save_secrets(sec)
    return ids[-1]


def bot_info():
    me = api("getMe")
    return {"username": me.get("username"), "name": me.get("first_name")}


def peek(msg_id):
    """رسالة القناة رقم msg_id (أو None لو مش موجودة) — من غير ما يفضل أثر في الشات."""
    chat = admin_chat()
    try:
        m = api("forwardMessage", chat_id=chat, from_chat_id=channel(), message_id=msg_id, disable_notification=True)
    except TgError as e:
        if "not found" in str(e) or "MESSAGE_ID_INVALID" in str(e):
            return None
        raise
    try:
        api("deleteMessage", chat_id=chat, message_id=m["message_id"])
    except TgError:
        pass
    m["id"] = msg_id
    return m


# ---------- تنسيق تليجرام (entities) ← HTML ----------
_TAGS = {"bold": "b", "italic": "i", "underline": "u", "strikethrough": "s", "spoiler": "tg-spoiler",
         "code": "code", "pre": "pre", "blockquote": "blockquote", "expandable_blockquote": "blockquote expandable"}


def to_html(text, entities):
    """الرسالة بتنسيقها كـ HTML (عشان نعدّلها من غير ما يضيع التنسيق اللي اتعمل بالإيد)."""
    if not text:
        return ""
    u = text.encode("utf-16-le")
    n = len(u) // 2
    opens, closes = {}, {}
    for e in entities or []:
        t = e["type"]
        if t == "text_link":
            o, c = f'<a href="{html.escape(e["url"])}">', "</a>"
        elif t in _TAGS:
            tag = _TAGS[t]
            o, c = f"<{tag}>", f"</{tag.split()[0]}>"
        else:
            continue
        s, end = e["offset"], e["offset"] + e["length"]
        opens.setdefault(s, []).append((end, o))
        closes.setdefault(end, []).insert(0, c)
    out = []
    for i in range(n + 1):
        out += closes.get(i, [])
        out += [o for _, o in sorted(opens.get(i, []), key=lambda x: -x[0])]
        if i < n:
            ch = u[2 * i:2 * i + 2]
            # حرف خارج BMP (إيموجي) = وحدتين UTF-16
            if 0xD800 <= int.from_bytes(ch, "little") <= 0xDBFF:
                continue
            if i > 0 and 0xD800 <= int.from_bytes(u[2 * i - 2:2 * i], "little") <= 0xDBFF:
                ch = u[2 * i - 2:2 * i + 2]
            out.append(html.escape(ch.decode("utf-16-le"), quote=False))
    return "".join(out)


# ---------- التعرف على المرفوع ----------
def nkey(name):
    n = re.sub(r"\.(mp3|m4a|ogg|wav)$", "", (name or "").strip(), flags=re.I)
    n = re.sub(r"\s*\(\d+\)$", "", n).replace("_", " ")
    return re.sub(r"\s+", " ", n).strip()


def find_uploads(names, log=print, start=None, give_up=6):
    """بيدوّر على الرسايل الجديدة في القناة اللي فيها ملفات بنفس الأسامي.
    بيبدأ من آخر رسالة معروفة ويقف بعد كام رقم ورا بعض مفيش فيهم رسايل."""
    want = {nkey(n): n for n in names}
    s = load_settings()
    sec = load_secrets()
    i = start or (sec.get("last_seen_msg") or max([x.get("last_msg") or 0 for x in s["series"]] + [0])) + 1
    found, miss, last_ok = {}, 0, None
    while miss < give_up and len(found) < len(want):
        m = peek(i)
        if m is None:
            miss += 1
        else:
            miss, last_ok = 0, i
            doc = m.get("audio") or m.get("document") or {}
            k = nkey(doc.get("file_name"))
            if k in want:
                found[want[k]] = {"id": i, "caption": to_html(m.get("caption"), m.get("caption_entities"))}
                log(f"لقيت «{want[k]}» في الرسالة {i}")
        i += 1
        time.sleep(0.4)  # منتقلش على تليجرام
    if last_ok:
        sec = load_secrets()
        sec["last_seen_msg"] = max(sec.get("last_seen_msg") or 0, last_ok - len(want) - 3)
        save_secrets(sec)
    return found


# ---------- الكتابة على القناة ----------
def set_caption(msg_id, caption_html):
    try:
        api("editMessageCaption", chat_id=channel(), message_id=msg_id, caption=caption_html, parse_mode="HTML")
    except TgError as e:
        if "not modified" not in str(e):
            raise


def backup(root, name, content):
    if not root:
        return
    d = Path(root) / "Backups"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{datetime.now():%Y%m%d_%H%M%S}_{name}.html").write_text(content, encoding="utf-8")


def read_index(msg_id):
    m = peek(msg_id)
    if m is None:
        raise TgError(f"رسالة الفهرس {msg_id} مش موجودة")
    return to_html(m.get("text"), m.get("entities"))


def index_sections(index_html):
    return [re.sub(r"<[^>]+>", "", l).replace("🔸", "").strip() for l in index_html.split("\n") if l.startswith("🔸")]


def section_of(index_html, msg_id):
    """القسم اللي فيه آخر درس اتنشر (عشان يبقى الاختيار الافتراضي)."""
    url = load_settings()["channel_url"]
    cur = None
    for l in index_html.split("\n"):
        if l.startswith("🔸"):
            cur = re.sub(r"<[^>]+>", "", l).replace("🔸", "").strip()
        if msg_id and f'href="{url}{msg_id}"' in l:
            return cur
    return None


def index_add(index_html, msg_id, title, section=None, numbered=False):
    """يضيف سطر الدرس في آخر القسم (أو آخر قسم) — من غير ما يغيّر أي حاجة تانية في الرسالة."""
    url = load_settings()["channel_url"]
    lines = index_html.split("\n")
    if f'href="{url}{msg_id}"' in index_html:
        return index_html  # متضاف قبل كده
    items = [k for k, l in enumerate(lines) if re.match(r'^(\d+\. |• )<a href=', l)]
    if not items:
        raise TgError("مش لاقي سطور الدروس في الفهرس")
    target = items[-1]
    if section:
        heads = [k for k, l in enumerate(lines) if l.startswith("🔸") and section in l]
        if heads:
            nxt = [k for k, l in enumerate(lines) if k > heads[-1] and l.startswith("🔸")]
            inside = [k for k in items if heads[-1] < k < (nxt[0] if nxt else len(lines))]
            if inside:
                target = inside[-1]
    n = len(items) + 1
    label = f"{n}. " if numbered else "• "
    new = f'{label}<a href="{url}{msg_id}">{html.escape(title, quote=False)}</a>'
    lines.insert(target + 1, new)
    if numbered:  # إعادة الترقيم لو اتضاف في النص
        c = 0
        for k, l in enumerate(lines):
            if re.match(r"^\d+\. <a href=", l):
                c += 1
                lines[k] = re.sub(r"^\d+\. ", f"{c}. ", l)
    return "\n".join(lines)


def set_index(msg_id, new_html):
    try:
        api("editMessageText", chat_id=channel(), message_id=msg_id, text=new_html, parse_mode="HTML",
            link_preview_options={"is_disabled": True})
    except TgError as e:
        if "not modified" not in str(e):
            raise
