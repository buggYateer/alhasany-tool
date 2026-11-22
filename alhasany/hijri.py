"""التاريخ: من اسم ملف المسجل (YYMMDD_HHMM) أو تاريخ الملف ← هجري (أم القرى) + يوم الأسبوع."""
import datetime as dt
import re
from pathlib import Path

from hijridate import Gregorian

DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def file_datetime(path):
    p = Path(path)
    m = re.match(r"(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})", p.stem)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return dt.datetime(2000 + y, mo, d, h, mi)
    m = re.search(r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", re.sub(r"[٠-٩]", lambda c: str("٠١٢٣٤٥٦٧٨٩".index(c.group())), p.stem))
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return dt.datetime(y, mo, d, h, mi)
    return dt.datetime.fromtimestamp(p.stat().st_mtime)


def to_hijri(d, offset_days=0):
    d = d + dt.timedelta(days=offset_days)
    h = Gregorian(d.year, d.month, d.day).to_hijri()
    return h.day, h.month, h.year


def describe(path, offset_days=0):
    """{'date': '7-6-1448', 'weekday': 'الثلاثاء', 'kind': 'night'|'friday', 'month': 6, 'year': 1448}"""
    t = file_datetime(path)
    d, m, y = to_hijri(t, offset_days)
    wd = DAYS[t.weekday()]
    kind = "friday" if wd == "الجمعة" and 10 <= t.hour < 15 else "night"
    return {"date": f"{d}-{m}-{y}", "weekday": wd, "kind": kind, "day": d, "month": m, "year": y,
            "gregorian": t.strftime("%Y-%m-%d %H:%M")}
