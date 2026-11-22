"""سجل القناة: كل اللي اتنشر على القناة (من الأداة أو بالإيد) — عشان:
- صفحة «آخر المنشور» تبيّن كل رسالة: من الأداة ولا بالإيد، في الفهرس ولا لأ، على الموقع ولا لأ
- رقم الدرس و«الدرس السابق» يتاخدوا من الفهرس نفسه (مش من ذاكرة الأداة)
السجل في Work\\channel_posts.json (على الجهاز بس)."""
import json
import re
import time
from pathlib import Path

from . import tg
from .config import load_settings, update_settings, work_dir

REG = "channel_posts.json"


def _path():
    return work_dir() / REG


def load():
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"posts": {}, "max_id": 0, "index_ids": {}, "scanned_at": 0}


def save(reg):
    _path().write_text(json.dumps(reg, ensure_ascii=False, indent=0), encoding="utf-8")


def _plain(h):
    return re.sub(r"<[^>]+>", "", h or "")


def guess_series(caption_html):
    c = caption_html or ""
    if "حديث جبريل" in c:
        return "jibreel"
    if "#وقفة_مع_آية" in c:
        return "yahya"
    if "#سلسلة_الفقه" in c:
        return "fiqh"
    if "#سيد_عبدالعال" in c and "#درس_" in c:
        return "sayed"
    return None


def guess_line(caption_html, series):
    """سطر الفهرس المقترح من الوصف (المسؤول بيعدّله قبل ما يتضاف)."""
    bolds = [_plain(b).strip() for b in re.findall(r"<b>(.*?)</b>", caption_html or "", re.S)]
    if series == "yahya":
        verses = next((b for b in bolds if re.search(r"\(\d", b)), "")
        nums = re.search(r"\([\d\s\-–،,]+\)", verses)
        sub = re.search(r"🔹\s*<b>(.*?)</b>", caption_html or "", re.S)
        sub = _plain(sub.group(1)).strip() if sub else ""
        return f"{nums.group(0) if nums else ''} {sub}".strip()
    t = bolds[0] if bolds else ""
    if series in ("jibreel", "fiqh") and ": " in t:  # «علامات الساعة: رفع الأمانة» ← القسم موجود في الفهرس أصلًا
        t = t.split(": ", 1)[1]
    return t


def _record(m):
    doc = m.get("audio") or m.get("document") or m.get("voice")
    if doc:
        kind = "audio"
    elif m.get("photo"):
        kind = "photo"
    elif m.get("text"):
        kind = "text"
    else:
        kind = "other"
    cap = tg.to_html(m.get("caption"), m.get("caption_entities"))
    r = {"id": m["id"], "date": (m.get("forward_origin") or {}).get("date") or m.get("forward_date") or m.get("date"), "kind": kind,
         "file_name": (doc or {}).get("file_name"), "duration": (doc or {}).get("duration"), "caption": cap}
    if kind == "text":
        r["text"] = _plain(tg.to_html(m.get("text"), m.get("entities")))[:300]
    if kind == "audio":
        r["series"] = guess_series(cap)
        r["line"] = guess_line(cap, r["series"])
    return r


def refresh_indexes(reg, log=print):
    """يقرا رسايل الفهارس: مين فيها، وآخر رقم وآخر رسالة لكل سلسلة ← يحدّث الإعدادات."""
    s = load_settings()
    url = s["channel_url"]
    changed = False
    for ser in s["series"]:
        if not ser.get("index_msg"):
            continue
        try:
            h = tg.read_index(ser["index_msg"])
        except tg.TgError as e:
            log(f"⚠ مش قادر أقرا فهرس {ser['name']}: {e}")
            continue
        ids = [int(x) for x in re.findall(re.escape(url) + r"(\d+)", h)]
        reg["index_ids"][ser["key"]] = ids
        if ids and max(ids) != ser.get("last_msg"):
            ser["last_msg"] = max(ids)
            changed = True
        if ser.get("numbered"):
            n = len(re.findall(r"^\d+\. <a href=", h, re.M))
            if n and n != ser.get("last_number"):
                ser["last_number"] = n
                changed = True
    if changed:
        update_settings({"series": s["series"]})
        log("✓ أرقام السلاسل اتحدّثت من الفهارس")
    return changed


def scan(start=None, log=print, give_up=6, limit=150):
    """يقرا الرسايل الجديدة في القناة (من آخر رسالة اتقرت) ويسجّلها."""
    reg = load()
    s = load_settings()
    if start is None:
        start = reg["max_id"] + 1 if reg["max_id"] else max([x.get("last_msg") or 0 for x in s["series"]] + [0]) - 20
    i, miss, n = max(1, start), 0, 0
    while miss < give_up and n < limit:
        m = tg.peek(i)
        if m is None:
            miss += 1
        else:
            miss = 0
            reg["posts"][str(i)] = _record(m)
            reg["max_id"] = max(reg["max_id"], i)
            n += 1
        i += 1
        time.sleep(0.35)
    log(f"قريت {n} رسالة جديدة (لحد رسالة {reg['max_id']})")
    refresh_indexes(reg, log)
    reg["scanned_at"] = time.time()
    save(reg)
    return reg


def site_ids():
    p = Path(load_settings().get("site_channel_json") or "")
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("messages", [])
        return {r.get("id") for r in rows}
    except (OSError, ValueError):
        return None


def tool_ids():
    ids = {}
    for f in work_dir().glob("job_*.json"):
        try:
            for x in json.loads(f.read_text(encoding="utf-8"))["files"]:
                if x.get("msg_id"):
                    ids[x["msg_id"]] = {"job": f.stem[4:], "published": bool(x.get("published"))}
        except (OSError, ValueError, KeyError):
            pass
    return ids


def listing(limit=60):
    reg = load()
    s = load_settings()
    in_index = {i: k for k, ids in reg.get("index_ids", {}).items() for i in ids}
    index_msgs = {x["index_msg"] for x in s["series"] if x.get("index_msg")}
    site = site_ids()
    tools = tool_ids()
    out = []
    for k in sorted(reg["posts"], key=int, reverse=True)[:limit]:
        p = dict(reg["posts"][k])
        pid = p["id"]
        p["is_index"] = pid in index_msgs
        p["in_index"] = in_index.get(pid)
        p["on_site"] = None if site is None else (pid in site)
        p["via_tool"] = tools.get(pid)
        out.append(p)
    return {"posts": out, "max_id": reg["max_id"], "scanned_at": reg.get("scanned_at", 0),
            "series": [{"key": x["key"], "name": x["name"], "index_msg": x.get("index_msg"), "numbered": x.get("numbered", False)}
                       for x in s["series"]], "site_sync": bool(s.get("site_sync"))}


def find_names(names, log=print):
    """للنشر: يقرا الجديد ويدوّر على الملفات بالاسم في السجل."""
    reg = scan(log=log)
    want = {tg.nkey(n): n for n in names}
    found = {}
    for k in sorted(reg["posts"], key=int, reverse=True):
        p = reg["posts"][k]
        key = tg.nkey(p.get("file_name"))
        if key in want and want[key] not in found:
            found[want[key]] = {"id": p["id"], "caption": p.get("caption", "")}
            log(f"لقيت «{want[key]}» في الرسالة {p['id']}")
    return found
