"""سطر الأوامر:
  python -m alhasany                              ← الواجهة (بتتفتح في المتصفح + لينك/QR للموبايل)
  python -m alhasany setup                        ← أول مرة: اختيار مكان فولدر Alhasany + تنزيل الناقص بس
  python -m alhasany check                        ← يعرض الموجود والناقص على الجهاز من غير ما ينزّل حاجة
  python -m alhasany info FILE                    ← البيانات المقترحة (التاريخ، الشيخ، النوع)
  python -m alhasany process FILE [--date 7-6-1448] [--kind night|friday] [--sheikh أحمد] [--khatib "محمد نبيل"]
                                  [--series jibreel|none] [--number 40] [--out DIR]
"""
import argparse
import json
import sys

from .config import load_settings
from .pipeline import default_meta, process


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="alhasany")
    sub = ap.add_subparsers(dest="cmd")
    u = sub.add_parser("ui")
    u.add_argument("--no-browser", action="store_true")
    u.add_argument("--port", type=int, default=8765)
    sub.add_parser("setup")
    sub.add_parser("check")
    i = sub.add_parser("info")
    i.add_argument("file")
    p = sub.add_parser("process")
    p.add_argument("file")
    for k in ("date", "kind", "sheikh", "khatib", "series", "out"):
        p.add_argument(f"--{k}")
    p.add_argument("--number", type=int)
    p.add_argument("--merge-prayer", action="store_true")
    a = ap.parse_args()
    if a.cmd in (None, "ui"):
        from .server import serve
        return serve(open_browser=not getattr(a, "no_browser", False), port=getattr(a, "port", 8765))
    from . import setup
    if a.cmd == "check":
        print(json.dumps({**setup.report(setup.root_dir()), "root": str(setup.root_dir() or "")}, ensure_ascii=False, indent=1))
        return
    if a.cmd in ("setup", "process") and not setup.ensure():
        sys.exit("فيه حاجة متنزلتش — شوف الرسايل فوق وجرّب تاني")
    if a.cmd == "setup":
        print("\n✓ الجهاز جاهز")
        return
    s = load_settings()
    meta = default_meta(a.file, s)
    if a.cmd == "info":
        print(json.dumps(meta, ensure_ascii=False, indent=1))
        return
    for k in ("date", "kind", "sheikh", "khatib"):
        if getattr(a, k):
            meta[k] = getattr(a, k)
    if a.date:
        d, m, y = map(int, a.date.split("-"))
        meta.update(day=d, month=m, year=y)
    if a.series:
        meta["series"] = None if a.series == "none" else a.series
    if a.number:
        meta["number"] = a.number
    if a.merge_prayer:
        meta["merge_prayer"] = True
    job = process(a.file, meta, outdir=a.out)
    for f in job["files"]:
        print(f"\n## {f['name']} [{f['duration']}]  {f['note']}")
        if f.get("surahs"):
            print("   السور:", " ← ".join(f["surahs"]))
        for x in f["issues"]:
            print(f"   ⚠ {x['t']} {x['kind']}: المتوقع «{x['expected']}» — المسموع «{x['heard']}»")
        for w in f["warnings"]:
            print("   ⚠", w)


if __name__ == "__main__":
    main()
