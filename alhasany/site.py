"""تحديث موقع المسجد بعد كل نشر — مقفول افتراضيًا (site_sync)، صاحب القناة بيفتحه من الإعدادات.
لو أي خطوة فشلت، النشر على القناة مبيتأثرش، والمرة الجاية الموقع بيكمّل اللي فاته."""
import json
import re
import subprocess
from pathlib import Path

from .config import load_settings


def _channel_json(s, job, f):
    p = Path(s.get("site_channel_json") or "")
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("messages", [])
    if any(r.get("id") == f["msg_id"] for r in rows):
        return "موجود قبل كده"
    rows.append({"id": f["msg_id"], "t": f["name"], "d": f["duration"], "c": f["caption"], "l": [], "file": f["file"]})
    rows.sort(key=lambda r: r.get("id", 0))
    p.write_text(json.dumps(data, ensure_ascii=False, indent=0 if isinstance(data, list) else 1), encoding="utf-8")
    return "اتضاف"


def _series_py(s, ser, f):
    """يضيف (رقم الرسالة, العنوان) في SERIES جوه gen_series.py — الموقع بياخد ترتيب السلاسل منه."""
    p = Path(s.get("site_series_py") or "")
    if not p.is_file() or not ser:
        return None
    src = p.read_text(encoding="utf-8")
    if re.search(rf"\({f['msg_id']},\s*\"", src):
        return "موجود قبل كده"
    k = src.find(f'{{"key": "{ser["key"]}"')
    if k < 0:
        return f"السلسلة {ser['key']} مش موجودة في الملف"
    nxt = src.find('{"key":', k + 5)
    block_end = nxt if nxt > 0 else len(src)
    sec = f.get("index_section")
    pos = -1
    if sec:
        h = src.find(f'("{sec}", [', k, block_end)
        if h > 0:
            pos = src.find(")])", h, block_end)
    if pos < 0:
        pos = src.rfind(")])", k, block_end)
    if pos < 0:
        return "مش لاقي مكان أضيف فيه"
    title = (f.get("index_line") or f.get("title") or "").replace('"', "'")
    src = src[:pos + 1] + f', ({f["msg_id"]}, "{title}")' + src[pos + 1:]
    p.write_text(src, encoding="utf-8")
    return "اتضاف"


def sync(job, f, ser):
    s = load_settings()
    if not s.get("site_sync"):
        return []
    steps = []
    r = _channel_json(s, job, f)
    if r:
        steps.append(f"✓ الموقع: سطر المقطع {r}")
    r = _series_py(s, ser, f)
    if r:
        steps.append(f"✓ الموقع: ترتيب السلسلة {r}")
    cmd = s.get("site_update_cmd")
    if cmd:
        # رفع الصوت ممكن ياخد دقايق ← في الخلفية، والنتيجة في Work\site_update.log
        from .config import work_dir
        logf = open(work_dir() / "site_update.log", "w", encoding="utf-8")
        subprocess.Popen(cmd, shell=True, stdout=logf, stderr=subprocess.STDOUT)
        steps.append("⏳ الموقع بيتحدّث في الخلفية (لو فشل بيكمّل المرة الجاية)")
    return steps
