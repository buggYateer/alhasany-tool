"""أدوات مشتركة: ffmpeg، تنسيق الوقت، قراءة الصوت."""
import shutil
import subprocess
from pathlib import Path


def ffmpeg_bin(name="ffmpeg"):
    """ffmpeg من PATH، أو جنب البرنامج (لما يتغلّف)."""
    p = shutil.which(name)
    if p:
        return p
    local = Path(__file__).resolve().parent.parent / "bin" / f"{name}.exe"
    if local.exists():
        return str(local)
    raise RuntimeError(f"مش لاقي {name} — ثبّته (winget install Gyan.FFmpeg)")


def fmt(t):
    t = int(max(0, t))
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def duration(path):
    out = subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def read_audio(path, start=0.0, length=None, sr=16000):
    """الصوت كـ numpy float32 mono (من غير PyAV)."""
    import numpy as np
    cmd = [ffmpeg_bin(), "-v", "error", "-ss", f"{start:.2f}", "-i", str(path)]
    if length:
        cmd += ["-t", f"{length:.2f}"]
    cmd += ["-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
