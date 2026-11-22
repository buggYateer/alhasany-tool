"""التفريغ بـ faster-whisper (كارت الشاشة لو موجود، وإلا المعالج) + إصلاح تلقائي لمشاكل Whisper المعروفة:
- «التعليق»: نفس الجملة تتكرر (السلام عليكم / اشتركوا في القناة) ← نعيد تفريغ الجزء ده
- «الفجوة»: صوت واضح مفيش له تفريغ (زي فاتحة الركعة الأولى) ← نعيد تفريغه من غير VAD"""
import os
import site
from pathlib import Path

from .util import duration, fmt, read_audio

MODEL = "large-v3-turbo"
PROMPT = "بسم الله الرحمن الرحيم. الحمد لله والصلاة والسلام على رسول الله."
_model = None


def _cuda_dirs():
    if os.name != "nt":
        return
    for sp in site.getsitepackages():
        nv = Path(sp) / "nvidia"
        if nv.is_dir():
            for b in nv.glob("*/bin"):
                try:
                    os.add_dll_directory(str(b))
                except OSError:
                    pass
                os.environ["PATH"] = str(b) + os.pathsep + os.environ["PATH"]


def load_model(log=print):
    global _model
    if _model is not None:
        return _model
    _cuda_dirs()
    from faster_whisper import WhisperModel
    for device, ctype in (("cuda", "int8_float16"), ("cuda", "int8"), ("cpu", "int8")):
        try:
            _model = WhisperModel(MODEL, device=device, compute_type=ctype)
            log("التفريغ شغال على " + ("كارت الشاشة" if device == "cuda" else "المعالج (أبطأ)"))
            return _model
        except Exception as e:  # noqa: BLE001
            log(f"({device}/{ctype} مش متاح: {str(e)[:80]})")
    raise RuntimeError("مش قادر أشغّل Whisper")


def _run(audio, offset, vad, words=True):
    m = load_model()
    segs, _ = m.transcribe(audio, language="ar", beam_size=5, vad_filter=vad, word_timestamps=words,
                           condition_on_previous_text=False, initial_prompt=PROMPT)
    out = []
    for s in segs:
        out.append({"start": round(s.start + offset, 2), "end": round(s.end + offset, 2), "text": s.text.strip(),
                    "words": [[round(w.start + offset, 2), round(w.end + offset, 2), w.word.strip()] for w in (s.words or [])]})
    return out


HALLU = ("اشتركوا في القناة", "شكرا للمشاهدة", "ترجمة نانسي", "المترجم للقناة")


def _loops(segs):
    """فترات فيها نفس الجملة اتكررت ≥3 مرات ورا بعض، أو هلوسة معروفة."""
    bad = []
    for i in range(len(segs) - 2):
        t = segs[i]["text"]
        if t and t == segs[i + 1]["text"] == segs[i + 2]["text"] and len(t) < 60:
            bad.append((segs[i]["start"] - 5, segs[i + 2]["end"] + 5))
    return bad


def _gaps(path, segs, dur, log):
    """فجوات ≥ 25 ث مفيهاش تفريغ لكن فيها صوت عالي (كلام/تلاوة)."""
    import numpy as np
    out = []
    edges = [0.0] + [x for s in segs for x in (s["start"], s["end"])] + [dur]
    for a, b in zip(edges[0::2], edges[1::2]):
        if b - a < 25:
            continue
        x = read_audio(path, a, min(b - a, 600))
        if len(x) < 16000:
            continue
        fr = x[: len(x) // 1600 * 1600].reshape(-1, 1600)
        db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
        if (db > np.percentile(db, 50) + 15).mean() > 0.15:
            out.append((a, b))
    return out


def transcribe(path, log=print, progress=None):
    """{'file', 'duration', 'segments': [{start,end,text,words:[[s,e,w]]}]}"""
    path = str(path)
    dur = duration(path)
    log(f"بفرّغ {Path(path).name} ({fmt(dur)})…")
    segs = _run(read_audio(path), 0, vad=True)
    # إصلاح التعليق والفجوات
    for kind, wins in (("تكرار", _loops(segs)), ("فجوة", _gaps(path, segs, dur, log))):
        for a, b in wins:
            a, b = max(0, a), min(dur, b)
            log(f"إصلاح {kind} عند {fmt(a)}–{fmt(b)}")
            new = _run(read_audio(path, a, b - a), a, vad=False)
            new = [s for s in new if not any(h in s["text"] for h in HALLU)]
            segs = sorted([s for s in segs if s["end"] <= a or s["start"] >= b] + new, key=lambda s: s["start"])
        if progress:
            progress()
    segs = [s for s in segs if not any(h in s["text"] for h in HALLU)]
    return {"file": path, "duration": round(dur, 1), "segments": segs}
