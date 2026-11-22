"""خط الشغل الكامل لتسجيل خام: تفريغ ← قص ← ملفات ← فحص التلاوة ← مسودة الوصف."""
import json
from pathlib import Path

from . import asr, captions, cutter, hijri
from .config import load_settings, output_dir, work_dir
from .quran import Quran, check_recitation
from .util import fmt


def sheikh_info(settings, short):
    for s in settings["sheikhs"]:
        if s["short"] == short or s["full"] == short or s["tag"] == short.replace(" ", "_"):
            return s
    return {"short": short, "full": short, "tag": short.replace(" ", "_")}


def default_meta(path, settings=None):
    """البيانات المقترحة من اسم الملف وجدول المشايخ — الواجهة بتعرضها وصاحب القناة بيأكد."""
    settings = settings or load_settings()
    h = hijri.describe(path, settings.get("hijri_offset_days", 0))
    # خطبة الجمعة: الخطيب بيتغير كل أسبوع ← منخمنش، الواجهة تسأل
    sh = None if h["kind"] == "friday" else next((s for s in settings["sheikhs"] if s.get("day") == h["weekday"]), None)
    meta = {**h, "sheikh": sh["short"] if sh else "", "khatib": "", "merge_prayer": False, "series": None, "number": None}
    if sh:
        ser = next((x for x in settings["series"] if x["sheikh"] == sh["short"]), None)
        if ser:
            meta["series"] = ser["key"]
            if ser.get("numbered"):
                meta["number"] = ser.get("last_number", 0) + 1
    return meta


def transcript_for(path, log=print):
    """التفريغ بيتحفظ — لو اتعمل قبل كده منعيدوش."""
    p = Path(path)
    cache = work_dir() / f"{p.stem}.{int(p.stat().st_size)}.json"
    if cache.exists():
        log("التفريغ موجود من قبل")
        return json.loads(cache.read_text(encoding="utf-8"))
    t = asr.transcribe(p, log=log)
    cache.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    return t


def process(path, meta, log=print, outdir=None):
    settings = load_settings()
    outdir = Path(outdir or output_dir())
    t = transcript_for(path, log)
    cut_meta = {"kind": meta["kind"], "date": meta["date"]}
    if meta["kind"] == "night":
        cut_meta["sheikh"] = meta["sheikh"]
    else:
        info = sheikh_info(settings, meta["khatib"] or meta["sheikh"])
        cut_meta["khatib"] = info["short"] if info in settings["sheikhs"] else info["full"]
        cut_meta["merge_prayer"] = meta.get("merge_prayer", info.get("khutba_with_prayer", False))
    log("بحسب نقاط القص…")
    files = cutter.plan(t, cut_meta)
    q = Quran()
    series = next((s for s in settings["series"] if s["key"] == meta.get("series")), None)
    results = []
    for f in files:
        if not f["ranges"]:
            log(f"⚠ {f['note']}")
            continue
        log(f"بقص {f['name']}…")
        dst = cutter.render(path, f, outdir, log)
        item = {"file": str(dst), "name": f["name"], "role": f["role"], "duration": fmt(f["duration"]),
                "note": f["note"], "preview": f["preview"], "warnings": [], "issues": []}
        who = sheikh_info(settings, cut_meta.get("sheikh") or cut_meta.get("khatib"))
        mo, yr = meta["month"], meta["year"]
        if f["role"] in ("isha", "jumua") or (f["role"] == "khutba" and cut_meta.get("merge_prayer")):
            pr = f["ranges"][f.get("n_khutba", 0):] if f["role"] == "khutba" else f["ranges"]
            words = cutter.words_in(t, pr)
            texts = [" ".join(w for _, w in words[i:i + 14]) for i in range(0, len(words), 10)]
            runs = q.runs(texts)
            item["surahs"] = [f"{n} ({a}-{b})" for n, _, a, b in runs]
            off = cutter.section_starts(f["ranges"])[f.get("n_khutba", 0)] if f["role"] == "khutba" else 0
            # الفحص لكل ركعة لوحدها (كل ركعة بسورتها) — لو اتعمل على الكل مرة واحدة بيطلع تنبيهات غلط كتير
            issues, o = [], off
            for a, b in pr:
                w1 = [(o + ws - a, w) for s in t["segments"] for ws, _, w in s["words"] if a <= ws <= b]
                issues += check_recitation(w1, q)
                o += b - a
            item["issues"] = [{**x, "t": fmt(x["t"])} for x in issues]
            if f["role"] != "khutba":
                item["caption"] = captions.recitation(settings, who["tag"], "العشاء" if f["role"] == "isha" else "الجمعة", runs, mo, yr)
        if f["role"] == "khutba":
            starts = cutter.section_starts(f["ranges"])
            item["caption"] = captions.khutba(settings, who["tag"], "", starts, cut_meta.get("merge_prayer"), mo, yr)
            item["prompt"] = captions.title_prompt("khutba", who["full"], captions.sample_text(t, f["ranges"][:f["n_khutba"]]))
            if len(starts) < 2:
                item["warnings"].append("مش لاقي بداية الخطبة الثانية — التوقيتات متشالة")
        if f["role"] == "lesson":
            item["caption"] = captions.lesson(settings, who["tag"], meta["weekday"], "", mo, yr, series, meta.get("number"))
            ctx = f"السلسلة: {series['name']}" if series else ""
            item["prompt"] = captions.title_prompt("lesson", who["full"], captions.sample_text(t, f["ranges"]), ctx)
        results.append(item)
    job = {"source": str(path), "meta": meta, "files": results}
    jp = work_dir() / f"job_{Path(path).stem}.json"
    jp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"خلص ✓ — {len(results)} ملف في {outdir}")
    return job
