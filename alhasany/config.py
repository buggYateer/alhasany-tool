"""الإعدادات: settings.json (مشايخ، جدول، سلاسل، فولدرات) + secrets.json (توكن البوت، مفتاح Gemini).
الملفين في %APPDATA%\\AlhasanyTool — مش جوه المستودع."""
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "AlhasanyTool"
SETTINGS = APP_DIR / "settings.json"
SECRETS = APP_DIR / "secrets.json"
DEFAULTS = Path(__file__).parent / "data" / "defaults.json"


def _load(p, fallback):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def load_settings():
    d = _load(DEFAULTS, {})
    s = _load(SETTINGS, {})
    d.update(s)
    return d


def save_settings(s):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def load_secrets():
    return _load(SECRETS, {})


def save_secrets(sec):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")


def _root_sub(name, fallback):
    s = load_settings()
    r = s.get("root")
    p = Path(r) / name if r else Path(s.get(fallback) or (APP_DIR / name.lower()))
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir():
    return _root_sub("Work", "work_dir")


def output_dir(year=None, month=None):
    """Alhasany\\Cut\\1448-06 — فولدر لكل شهر هجري."""
    p = _root_sub("Cut", "output_dir")
    if year and month:
        p = p / f"{year}-{int(month):02d}"
        p.mkdir(parents=True, exist_ok=True)
    return p
