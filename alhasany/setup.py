"""تجهيز الجهاز — أول تشغيل وكل تشغيل:
1) فحص المكتبات/ffmpeg/الموديل ← بينزّل **الناقص بس** (اللي موجود على الجهاز بيتستخدم زي ما هو)
2) اختيار مكان فولدر الشغل (Alhasany) وبناء الفولدرات اللي جواه
"""
import importlib.metadata as md
import json
import os
import shutil
import string
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from .config import APP_DIR, load_settings, save_settings

ROOT_NAME = "Alhasany"
# الفولدرات جوه Alhasany (أسامي إنجليزي عشان متتلخبطش مع أسامي الملفات العربي)
FOLDERS = {
    "Raw": "التسجيلات الخام (من المايك أو الموبايل) — حطها هنا",
    "Cut": "الملفات المقصوصة الجاهزة للرفع — فولدر لكل شهر هجري (1448-06)",
    "Work": "شغل البرنامج: التفريغ المحفوظ وملفات المراجعة (متمسحهوش عشان ميعيدش التفريغ)",
    "Backups": "نسخة من الفهارس والأوصاف قبل أي تعديل على القناة",
    "Models": "موديل التفريغ (Whisper)",
    "Tools": "ffmpeg لو مكانش متثبت على الجهاز",
}
MODEL = "large-v3-turbo"
FFMPEG_ZIP = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

# (اسم الباكدج, نسخة/شرط, محتاجها بس لو فيه كارت NVIDIA)
PACKAGES = [
    ("faster-whisper", ">=1.2", False),
    ("numpy", "", False),
    ("hijridate", "==2.3.0", False),
    ("pillow", "", False),
    ("arabic-reshaper", "", False),
    ("python-bidi", "", False),
    ("qrcode", "", False),
    ("nvidia-cublas-cu12", "", True),
    ("nvidia-cudnn-cu12", "==9.*", True),
]


# ---------- الفحص ----------
def has_nvidia():
    smi = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _installed(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def missing_packages(gpu):
    return [n + v for n, v, need_gpu in PACKAGES if (gpu or not need_gpu) and not _installed(n)]


def find_ffmpeg(root=None):
    p = shutil.which("ffmpeg")
    if p and shutil.which("ffprobe"):
        return str(Path(p).parent)
    for d in ([Path(root) / "Tools" / "ffmpeg"] if root else []) + [Path(__file__).resolve().parent.parent / "bin"]:
        hit = next(d.rglob("ffmpeg.exe"), None) if d.is_dir() else None
        if hit and (hit.parent / "ffprobe.exe").exists():
            return str(hit.parent)
    return None


def find_model(root=None):
    """الموديل في Alhasany\\Models، أو في كاش HuggingFace لو اتنزّل قبل كده (مننزّلوش تاني)."""
    if root:
        d = Path(root) / "Models" / MODEL
        if (d / "model.bin").exists():
            return str(d)
    hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    for snap in hf.glob(f"models--*faster-whisper-{MODEL}/snapshots/*"):
        if (snap / "model.bin").exists():
            return str(snap)
    return None


def report(root=None):
    gpu = has_nvidia()
    return {"python": sys.version.split()[0], "gpu": gpu, "missing_packages": missing_packages(bool(gpu)),
            "ffmpeg": find_ffmpeg(root), "model": find_model(root)}


# ---------- التنزيل (الناقص بس) ----------
def install_packages(pkgs, log=print):
    if not pkgs:
        return True
    log("بنزّل المكتبات الناقصة: " + "، ".join(pkgs))
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *pkgs])
    return r.returncode == 0


def _refresh_path():
    """بعد winget: نقرا الـ PATH الجديد من الريجستري من غير ما نقفل البرنامج."""
    import winreg
    parts = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(hive, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join(parts + [os.environ.get("PATH", "")])


def install_ffmpeg(root, log=print):
    if shutil.which("winget"):
        log("بثبّت ffmpeg عن طريق winget…")
        r = subprocess.run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-source-agreements",
                            "--accept-package-agreements", "--disable-interactivity"])
        if r.returncode == 0:
            _refresh_path()
            if find_ffmpeg(root):
                log("✓ ffmpeg اتثبت")
                return find_ffmpeg(root)
    dst = Path(root) / "Tools" / "ffmpeg"
    dst.mkdir(parents=True, exist_ok=True)
    z = dst / "ffmpeg.zip"
    log("بنزّل ffmpeg (حوالي 130 ميجا)…")
    urllib.request.urlretrieve(FFMPEG_ZIP, z)
    with zipfile.ZipFile(z) as f:
        f.extractall(dst)
    z.unlink()
    return find_ffmpeg(root)


def install_model(root, log=print):
    from faster_whisper import download_model
    out = Path(root) / "Models" / MODEL
    log("بنزّل موديل التفريغ (حوالي 1.6 جيجا) — مرة واحدة بس…")
    return download_model(MODEL, output_dir=str(out))


# ---------- فولدر الشغل ----------
def drives():
    """البارتيشنات المتاحة ومساحتها الفاضية (بالجيجا)."""
    out = []
    for L in string.ascii_uppercase:
        p = f"{L}:\\"
        if os.path.exists(p):
            try:
                u = shutil.disk_usage(p)
                out.append({"path": p, "free_gb": round(u.free / 2**30), "total_gb": round(u.total / 2**30)})
            except OSError:
                pass
    return out


def suggest_drive():
    """أكبر بارتيشن فاضي غير C (عشان C بيتملي وبيتمسح لو الويندوز اتسطّب تاني)."""
    ds = drives()
    other = [d for d in ds if not d["path"].upper().startswith("C")]
    return max(other or ds, key=lambda d: d["free_gb"])["path"] if ds else str(Path.home())


def make_root(parent):
    root = Path(parent) / ROOT_NAME if Path(parent).name != ROOT_NAME else Path(parent)
    for name, desc in FOLDERS.items():
        (root / name).mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text("فولدرات أداة الحسني:\n\n" + "\n".join(f"{k}\t{v}" for k, v in FOLDERS.items()) + "\n",
                          encoding="utf-8-sig")
    s = load_settings()
    s["root"] = str(root)
    save_settings({k: v for k, v in s.items() if k in _user_keys(s)})
    return root


def _user_keys(s):
    # بنحفظ في settings.json اللي المستخدم غيّره بس + الفولدر — الباقي بيفضل من defaults
    from .config import DEFAULTS, _load
    d = _load(DEFAULTS, {})
    return {k for k in s if k == "root" or s.get(k) != d.get(k)}


def root_dir():
    r = load_settings().get("root")
    return Path(r) if r and Path(r).is_dir() else None


def ensure(log=print, ask=input):
    """كل اللي البرنامج محتاجه قبل ما يشتغل. بيرجع True لو كله جاهز."""
    root = root_dir()
    if root is None:
        ds = drives()
        sug = suggest_drive()
        log("\nاختار البارتيشن اللي هعمل فيه فولدر Alhasany:")
        for i, d in enumerate(ds, 1):
            log(f"  {i}) {d['path']}  فاضي {d['free_gb']} من {d['total_gb']} جيجا" + ("   ← مقترح" if d["path"] == sug else ""))
        a = (ask(f"رقم البارتيشن أو مسار فولدر [Enter = {sug}]: ") or "").replace("\ufeff", "").strip().strip('"')
        parent = ds[int(a) - 1]["path"] if a.isdigit() and 0 < int(a) <= len(ds) else (a or sug)
        root = make_root(parent)
        log(f"✓ اتعمل {root}")
    else:
        make_root(root)  # لو فولدر منهم اتمسح يتعمل تاني

    r = report(root)
    log(f"Python {r['python']} | كارت الشاشة: {r['gpu'] or 'مفيش NVIDIA ← التفريغ على المعالج (أبطأ)'}")
    ok = True
    if r["missing_packages"]:
        ok &= install_packages(r["missing_packages"], log)
    else:
        log("✓ المكتبات موجودة")
    if r["ffmpeg"]:
        log(f"✓ ffmpeg موجود ({r['ffmpeg']})")
    else:
        ok &= bool(install_ffmpeg(root, log))
    if r["model"]:
        log(f"✓ موديل التفريغ موجود ({r['model']})")
    elif ok:
        install_model(root, log)
    return ok
