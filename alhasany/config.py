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


def work_dir():
    s = load_settings()
    p = Path(s.get("work_dir") or (APP_DIR / "work"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_dir():
    s = load_settings()
    p = Path(s.get("output_dir") or (APP_DIR / "output"))
    p.mkdir(parents=True, exist_ok=True)
    return p
