"""
قص التسجيلات الخام تلقائيًا بناءً على التفريغ بتوقيت الكلمات.
plan(transcript, meta) ← نقاط القص · render(src, files, outdir) ← ملفات mp3 مضغوطة

القواعد (من صاحب القناة):
- الصلاة: تبدأ من الفاتحة (أو القراءة لو مفيش فاتحة)، بدون أي تكبيرات.
  الركعة الثانية: لو تكملة لنفس الموضع → تُحذف فاتحتها؛ لو سورة/موضع مختلف → تُترك.
- الدرس: من "السلام عليكم..." لحد آخر "والسلام عليكم ورحمة الله وبركاته".
- الجمعة: خطبة (الأولى + الثانية، والجلسة بينهم تتقصر لـ 3-4 ثواني) بدون أذان،
  والصلاة ملف لوحده — إلا الشيخ يحيى: الصلاة في آخر ملف الخطبة.
"""
import json
import re
import subprocess
from pathlib import Path

from .quran import Quran, norm
from .util import ffmpeg_bin, fmt

PAD_IN, PAD_OUT = 0.25, 0.6
SIT_KEEP = 3.5  # طول السكتة بين الخطبتين


class Rec:
    def __init__(self, d):
        self.file, self.duration, self.segs = d["file"], d["duration"], d["segments"]
        self.words = []  # (start, end, norm_word, seg_index)
        for i, s in enumerate(self.segs):
            for a, b, w in s["words"]:
                nw = norm(w)
                if nw:
                    self.words.append((a, b, nw, i))

    def find_seq(self, seq, start_t=0, end_t=None):
        """أول ظهور لسلسلة كلمات (مُطبعة) بعد start_t. يرجع index أول كلمة."""
        seq = [norm(x) for x in seq.split()]
        W = self.words
        for i in range(len(W) - len(seq) + 1):
            if W[i][0] < start_t or (end_t and W[i][0] > end_t):
                continue
            if all(W[i + k][2] == seq[k] for k in range(len(seq))):
                return i
        return None

    def text_around(self, t, before=6, after=8):
        W = self.words
        idx = min(range(len(W)), key=lambda i: abs(W[i][0] - t)) if W else 0
        b = " ".join(w[2] for w in W[max(0, idx - before):idx])
        a = " ".join(w[2] for w in W[idx:idx + after])
        return f"…{b} ‖ {a}…"


def takbir_after(r, t):
    i = r.find_seq("الله اكبر", t)
    return r.words[i][0] if i is not None else None


def fatiha_start(r, t, end_t=None):
    # لازم "الرحمن الرحيم" بعدها علشان منخلطش مع "الحمد لله رب العالمين" في أول الخطبة الثانية،
    # والكلمات متصلة (≤ 15 ث) — "ربنا ولك الحمد" وقت الرفع من الركوع ممكن تتسمع "الحمد لله رب العالمين"
    i = r.find_seq("الحمد لله رب العالمين الرحمن الرحيم", t, end_t)
    return i


def fatiha_onset(r, i):
    """وقت بداية الفاتحة. لو كلماتها متفرقة (Whisper حط «الحمد لله رب العالمين» بدري)، نحددها من الصوت:
    آخر سكتة ≥ 1.2 ث قبل «الرحمن الرحيم» بـ 3 ث = بعد تكبيرة القيام."""
    t0, t_rahman = r.words[i][0], r.words[i + 4][0]
    if t_rahman - t0 <= 15:
        return t0
    gaps = [e for s, e in silences(r) if e - s >= 1.2 and e <= t_rahman - 3 and e >= t_rahman - 20]
    return max(gaps) if gaps else t_rahman - 5


def fatiha_end_idx(r, i):
    """index آخر كلمة في الفاتحة (الضالين/آمين) بعد i."""
    for k in range(i, min(i + 60, len(r.words))):
        w = r.words[k][2]
        # Whisper ساعات بيكتبها غلط («الضامفد») ← أي كلمة تبدأ بـ«الض» بعد «المغضوب»
        if w.startswith("الضال") or (w.startswith("الض") and any("المغضوب" in x[2] for x in r.words[max(i, k - 4):k])):
            if k + 1 < len(r.words) and (r.words[k + 1][2] in ("امين", "آمين", "امنا") or (r.words[k + 1][2].startswith("ام") and len(r.words[k + 1][2]) <= 5 and r.words[k + 1][0] - r.words[k][1] < 4)):
                return k + 1
            return k
    return None


def rakah(r, q, t):
    """قراءة ركعة تبدأ من الفاتحة بعد t: يرجع dict فيه حدود الفاتحة والسورة وأرقام الآيات."""
    i = fatiha_start(r, t)
    if i is None:
        return None
    fe = fatiha_end_idx(r, i)
    t_f = r.words[fe][1] if fe else r.words[i][1]
    # نهاية القراءة: أول تكبيرة أو "سمع الله لمن حمده" (Whisper أحيانًا مبيسمعش تكبيرة الركوع)
    stops = [x for x in (takbir_after(r, t_f), (lambda k: r.words[k][0] if k is not None else None)(r.find_seq("سمع الله", t_f)),
                         (lambda k: r.words[k][0] if k is not None else None)(r.find_seq("الله لمن حمده", t_f))) if x]
    # احتياطي: سكتة الركوع (أكتر من 7 ثواني من غير كلام) أو مقطع مش من القرآن
    # نبدأ الفحص من أول السورة (السكتة بعد الفاتحة/آمين ممكن تبقى طويلة)
    seg_i = r.words[fe + 1][3] if fe is not None and fe + 1 < len(r.words) else r.words[i][3]
    for a_, b_ in zip(r.segs[seg_i:], r.segs[seg_i + 1:]):
        if b_["start"] - a_["end"] > 7 or re.search(r"أكبر|اكبر|لمن حمده|السلام عليكم", b_["text"]):
            stops.append(b_["start"])
            break
    tk = min(stops) if stops else None
    # آخر كلمة قبل تكبيرة الركوع
    last = None
    for k in range(i, len(r.words)):
        if tk and r.words[k][0] >= tk - 0.05:
            break
        last = k
    surah_txt = " ".join(w[2] for w in r.words[(fe or i) + 1:(last or i) + 1])
    first_ay = q.best(" ".join(surah_txt.split()[:14])) if surah_txt else None
    last_ay = q.best(" ".join(surah_txt.split()[-14:])) if surah_txt else None
    return {
        "fatiha_i": i, "fatiha_end_i": fe, "last_i": last, "takbir": tk,
        "start": fatiha_onset(r, i), "surah_start": r.words[fe + 1][0] if fe is not None and fe + 1 < len(r.words) else None,
        "end": r.words[last][1] if last is not None else None,
        "first": first_ay[:2] if first_ay else None, "last": last_ay[:2] if last_ay else None,
    }


BREATH = 1.0      # ثانية قبل وبعد الكلام علشان المقطع يبان طبيعي
FATIHA_GAP = 2.0  # أقصى سكتة بين الفاتحة والسورة


def silences(r):
    """خريطة السكتات في الملف (بالطاقة) — أدق من توقيت كلمات Whisper في نهايات المدود."""
    if not hasattr(r, "_sil"):
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-nostats", "-i", r.file, "-af",
                              "aresample=16000,pan=mono|c0=0.5*c0+0.5*c1,silencedetect=noise=-38dB:d=0.35", "-f", "null", "-"],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
        st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
        en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
        r._sil = list(zip(st, en + [r.duration] * (len(st) - len(en))))
    return r._sil


def sound_end(r, t, limit=1e9):
    """أول سكتة بعد آخر كلمة = نهاية الصوت الحقيقية (بعد المد)."""
    for s, e in silences(r):
        if s >= t - 0.2:
            return min(s, limit)
        if s < t < e:
            return min(s, limit)
    return min(t + 0.8, limit)


def sound_start(r, t, floor=0.0):
    best = None
    for s, e in silences(r):
        if e <= t + 0.2:
            best = e
        else:
            break
    return max(best if best is not None else t, floor)


def envelope(r, a, b):
    """مستوى الصوت (dB) كل 20ms في الفترة a→b."""
    import numpy as np
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", r.file,
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    n = 320
    fr = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    k = np.ones(5) / 5
    return np.convolve(db, k, mode="same")


def recitation_end(r, last_word_start, last_word_end):
    """نهاية الآية الحقيقية: أول هبوط واضح في الصوت بعد آخر كلمة (بعد المد)، وقبل التكبيرة."""
    a = max(0, last_word_start - 1.0)
    db = envelope(r, a, a + 20)
    if len(db) < 20:
        return last_word_end + BREATH
    import numpy as np
    ref = np.percentile(db[: int((last_word_end - a) / 0.02) + 25], 90)
    i = int(max(0, last_word_end - 0.2 - a) / 0.02)
    # دور على أول هبوط مستمر (≥ 120ms) تحت مستوى الكلام بـ 20dB
    while i < len(db) - 6:
        if all(db[i:i + 6] < ref - 20):
            break
        i += 1
    dip = a + i * 0.02
    # بداية الصوت اللي بعده (التكبيرة)
    j = i
    while j < len(db) and db[j] < ref - 12:
        j += 1
    nxt = a + j * 0.02
    # القص قبل تكبيرة الركوع بلحظة، والسكتة بين آخر الآية والتكبيرة بتفضل كاملة
    return nxt - 0.12 if j < len(db) else dip + BREATH


def recitation_start(r, first_word_start):
    """بداية القراءة: نرجع لورا من أول كلمة لحد آخر هبوط في الصوت (بعد التكبيرة)، ونبدأ بعده بلحظة.
    لو السكتة طويلة نسيب منها ثانية بس."""
    import numpy as np
    a = max(0, first_word_start - 10)
    db = envelope(r, a, first_word_start + 3)
    if len(db) < 20:
        return first_word_start - 0.3
    ref = np.percentile(db[int((first_word_start - a) / 0.02):], 90)  # مستوى صوت القراءة نفسها
    i = min(len(db) - 1, int((first_word_start + 0.3 - a) / 0.02))
    # ارجع لورا لحد ما نلاقي هبوط مستمر (≥120ms) = السكتة بين التكبيرة والفاتحة
    while i > 6 and not all(db[i - 6:i] < ref - 20):
        i -= 1
    onset = a + i * 0.02           # أول صوت القراءة
    k = i - 6
    while k > 0 and db[k] < ref - 12:
        k -= 1
    takbir_end = a + k * 0.02      # آخر صوت التكبيرة
    return max(takbir_end + 0.12, onset - BREATH)


def rakah_ranges(r, rk, prev_floor, skip_fatiha=False):
    """نطاقات ركعة: من قبل الفاتحة بثانية لبعد آخر آية بثانية، وسكتة الفاتحة→السورة تتقصر لثانيتين."""
    W = r.words
    # توقيت كلمة التكبير من Whisper مش مضمون، فبنعتمد على الصوت: آخر الآية → السكتة → أول صوت بعدها (التكبير)
    end = recitation_end(r, W[rk["last_i"]][0], W[rk["last_i"]][1])
    fe = rk["fatiha_end_i"]
    has_surah = fe is not None and fe + 1 <= rk["last_i"]
    if skip_fatiha and has_surah:
        # مش sound_end هنا: "آمين" المصلين ممكن تتوصل بأول القراءة من غير سكتة فنقص متأخر
        # بالصوت: بعد الفاتحة فيه "آمين" (صوت قصير) وبعدها القراءة (صوت متواصل) — نبدأ قبل القراءة بلحظة
        import numpy as np
        a = W[fe][1] + 0.2
        db = envelope(r, a, a + 30)
        ref = np.percentile(db, 95)
        loud = db > ref - 15
        runs, s0 = [], None
        for k, v in enumerate(loud):
            if v and s0 is None:
                s0 = k
            elif not v and s0 is not None:
                runs.append((s0, k)); s0 = None
        # دمج الفجوات الصغيرة (< 150ms) جوه الكلام
        merged = []
        for s_, e_ in runs:
            if merged and s_ - merged[-1][1] < 8:
                merged[-1] = (merged[-1][0], e_)
            else:
                merged.append((s_, e_))
        cut_t = None
        # الإمام بيستنى "آمين" تخلص وياخد نفس: أول سكتة ≥ 2.5 ثانية، واللي بعدها هو بداية القراءة
        for n in range(1, len(merged)):
            if (merged[n][0] - merged[n - 1][1]) * 0.02 >= 2.5 and merged[n][0] * 0.02 < 28:
                cut_t = a + max(merged[n - 1][1] * 0.02 + 0.1, merged[n][0] * 0.02 - 0.8)
                break
        if cut_t is None:  # احتياطي: أول صوت متواصل ≥ 1.6 ثانية
            cut_t = a
            for n, (s_, e_) in enumerate(merged):
                if e_ - s_ >= 80:
                    prev_end = merged[n - 1][1] if n else 0
                    cut_t = a + max(prev_end * 0.02 + 0.1, s_ * 0.02 - 0.6)
                    break
        return [[cut_t, end]]
    start = max(recitation_start(r, rk["start"]), prev_floor)
    if has_surah:
        f_end = sound_end(r, W[fe][1])
        s_start = sound_start(r, W[fe + 1][0], f_end)
        if s_start - f_end > FATIHA_GAP + 0.2:
            return [[start, f_end + FATIHA_GAP / 2], [s_start - FATIHA_GAP / 2, end]]
    return [[start, end]]


def prayer_ranges(r, q, t0):
    """نطاقات القراءة الجهرية (ركعتين) بعد t0، بالقواعد."""
    r1 = rakah(r, q, t0)
    if not r1 or r1["end"] is None:
        return [], "لم أجد الفاتحة", None
    ranges = rakah_ranges(r, r1, t0)
    notes = [f"ر1: {fmt(r1['start'])}→{fmt(r1['end'])} آيات {r1['first']}→{r1['last']}"]
    # الركعة الثانية: فاتحة جديدة بعد "سمع الله لمن حمده" والسجود
    r2 = rakah(r, q, r1["end"] + 15)
    if r2 and r2["end"] and r2["start"] - r1["end"] < 600:
        cont = bool(r1["last"] and r2["first"] and r1["last"][0] == r2["first"][0]
                    and 0 <= r2["first"][1] - r1["last"][1] <= 2)
        ranges += rakah_ranges(r, r2, ranges[-1][1], skip_fatiha=cont)
        notes.append(f"ر2: {fmt(r2['start'])}→{fmt(r2['end'])} آيات {r2['first']}→{r2['last']} — "
                     + ("تكملة → حذف الفاتحة" if cont else "موضع مختلف → الفاتحة باقية"))
        after = r2["end"]
    else:
        notes.append("ر2: مش لاقيها (أو مفيش)")
        after = r1["end"]
    return ranges, " | ".join(notes), after


def taslim_after(r, t):
    i = r.find_seq("السلام عليكم ورحمه الله", t)
    return r.words[i][1] if i is not None else None


def lesson_range(r, t):
    """بداية الدرس: أول (السلام عليكم ورحمة الله وبركاته | أعوذ بالله | إن الحمد لله) بعد t."""
    # التسليمة التانية لو موجودة
    t2 = taslim_after(r, t + 1)
    if t2 and t2 - t < 15:
        t = t2
    # بداية الدرس = أول كلام متواصل بعد التسليم (≥5 مقاطع في 45 ثانية) — الشيوخ بيبدأوا بصيغ مختلفة
    segs = [s for s in r.segs if s["start"] > t + 3]
    st = None
    for k, s in enumerate(segs):
        if sum(1 for x in segs[k:k + 12] if x["start"] <= s["start"] + 45) >= 5:
            st = s["start"]
            break
    if st is None:
        return None
    st = max(st - BREATH + 0.4, t + 1)
    # النهاية: آخر "والسلام عليكم ورحمة الله وبركاته"
    end = None
    k = st
    while True:
        i = r.find_seq("والسلام عليكم ورحمه الله", k + 1)
        if i is None:
            break
        end = r.words[min(i + 4, len(r.words) - 1)][1]
        k = r.words[i][0]
    if end is None:
        end = r.words[-1][1]
    return [st - 0.4, end + 1.2]


def plan_night(r, q, m):
    out = []
    ranges, note, after = prayer_ranges(r, q, 0)
    sh = m["sheikh"]
    if ranges:
        out.append({"role": "isha", "name": f"عشاء {m['date']}هـ ش {sh}.mp3", "ranges": ranges, "note": note})
    tsl = taslim_after(r, after or 0)
    les = lesson_range(r, tsl or (after or 0))
    if les:
        out.append({"role": "lesson", "name": f"درس ش {sh} {m['date']}هـ.mp3", "ranges": [les], "note": f"التسليم {fmt(tsl) if tsl else '؟'}"})
    return out


def plan_friday(r, q, m):
    out = []
    # بداية الخطبة: "ان الحمد لله" أو "الحمد لله نحمده"
    i = r.find_seq("ان الحمد لله")
    j = r.find_seq("الحمد لله نحمده")
    starts = [r.words[x][0] for x in (i, j) if x is not None]
    if not starts:  # ملف مقصوص من قبل بيبدأ بالخطبة على طول ("الحمد لله الذي ...")
        k = r.find_seq("الحمد لله", 0, 90)
        if k is not None:
            starts = [r.words[k][0]]
    if not starts:
        return [{"name": "؟", "ranges": [], "note": "مش لاقي بداية الخطبة"}]
    k_start = min(starts)
    # نهاية الخطبة: "اقم الصلاه"
    e = r.find_seq("واقم الصلاه", k_start + 300)
    if e is None:
        e = r.find_seq("اقم الصلاه", k_start + 300)
    k_end = None
    if e is None:
        # احتياطي: الخطبة بتخلص قبل الإقامة / أول الصلاة — نرجع من الفاتحة لورا لحد آخر مقطع مش إقامة ولا تكبير
        fi = fatiha_start(r, k_start + 300)
        if fi is not None:
            si = r.words[fi][3]
            # لو فيه "قد قامت الصلاة" قبل الفاتحة نبدأ الرجوع من عندها
            qi = r.find_seq("قد قامت الصلاه", r.words[fi][0] - 180, r.words[fi][0])
            if qi is not None:
                si = r.words[qi][3]
            while si > 0 and re.search(r"أكبر|اكبر|قامت|حي على|أشهد|اشهد|استووا|اعتدلوا|^الله$|لا إله إلا الله$",
                                       r.segs[si - 1]["text"]):
                si -= 1
            k_end = r.segs[si - 1]["end"] + 0.8 if si > 0 else None
    if e is not None:
        n = min(e + 1, len(r.words) - 1)
        nxt = r.words[n + 1][0] - 0.1 if n + 1 < len(r.words) else 1e9
        k_end = min(r.words[n][1] + 0.8, nxt)
    # الجلسة: أكبر فجوة بين المقاطع في المنتصف
    segs = [s for s in r.segs if k_start <= s["start"] <= (k_end or 1e9)]
    best = None
    for a, b in zip(segs, segs[1:]):
        g = b["start"] - a["end"]
        frac = (a["end"] - k_start) / max(1, (k_end or r.duration) - k_start)
        if 0.3 < frac < 0.9 and (best is None or g > best[0]):
            best = (g, a["end"], b["start"])
    ranges = []
    note = ""
    if best and best[0] > SIT_KEEP + 1:
        half = SIT_KEEP / 2
        ranges = [[k_start - 0.4, best[1] + half], [best[2] - half, k_end or r.duration]]
        note = f"الجلسة {fmt(best[1])}→{fmt(best[2])} ({best[0]:.0f}ث → {SIT_KEEP}ث)"
    else:
        ranges = [[k_start - 0.4, k_end or r.duration]]
        note = "مش لاقي الجلسة بين الخطبتين"
    pr, pnote, _ = prayer_ranges(r, q, (k_end or k_start) + 5)
    name = m["khatib"]
    if m.get("merge_prayer"):
        out.append({"role": "khutba", "n_khutba": len(ranges), "name": f"خطبة ش {name} {m['date']}هـ.mp3", "ranges": ranges + pr,
                    "note": note + " | الصلاة مدموجة: " + pnote})
    else:
        out.append({"role": "khutba", "n_khutba": len(ranges), "name": f"خطبة ش {name} {m['date']}هـ.mp3", "ranges": ranges, "note": note})
        if pr:
            out.append({"role": "jumua", "name": f"صلاة جمعة {m['date']}هـ ش {name}.mp3", "ranges": pr, "note": pnote})
    return out


def plan(transcript, meta):
    """meta: {'kind': 'night'|'friday', 'date': '7-6-1448', 'sheikh': 'أحمد'} أو للجمعة {'khatib': 'يحيى', 'merge_prayer': True}"""
    r, q = Rec(transcript), Quran()
    files = plan_night(r, q, meta) if meta["kind"] == "night" else plan_friday(r, q, meta)
    for f in files:
        f["preview"] = [[fmt(a), r.text_around(a + 0.3, 3, 7), fmt(b), r.text_around(b - 0.3, 7, 3)] for a, b in f["ranges"]]
        f["duration"] = round(sum(b - a for a, b in f["ranges"]), 1)
    return files


def words_in(transcript, ranges):
    """كلمات التلاوة جوه النطاقات (للتحقق من السور والأخطاء) + توقيتها في الملف الناتج."""
    out, off = [], 0.0
    for a, b in ranges:
        for s in transcript["segments"]:
            for ws, we, w in s["words"]:
                if a <= ws <= b:
                    out.append((off + ws - a, w))
        off += b - a
    return out


def section_starts(ranges):
    """بداية كل نطاق داخل الملف الناتج (لتوقيتات الخطبة الأولى/الثانية/الصلاة)."""
    t, out = 0.0, []
    for a, b in ranges:
        out.append(t)
        t += b - a
    return out


def render(src, f, outdir, log=print):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    rs = f["ranges"]
    parts, labels = [], []
    for n, (a, b) in enumerate(rs):
        parts.append(f"[0:a]atrim={max(0, a):.2f}:{b:.2f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=0.04,afade=t=out:st={max(0, b - a - 0.08):.2f}:d=0.08[p{n}]")
        labels.append(f"[p{n}]")
    is_prayer = f["role"] in ("isha", "jumua")
    comp = "" if is_prayer else ",acompressor=threshold=-24dB:ratio=2.5:attack=20:release=250:makeup=2"
    chain = ";".join(parts) + f";{''.join(labels)}concat=n={len(rs)}:v=0:a=1,pan=mono|c0=0.5*c0+0.5*c1,highpass=f=70{comp}[mix]"
    target = -18 if is_prayer else -16
    tmp = outdir / (f["name"] + ".tmp.wav")
    ff = ffmpeg_bin()
    subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-filter_complex", chain, "-map", "[mix]", str(tmp)], check=True)
    meas = subprocess.run([ff, "-hide_banner", "-i", str(tmp), "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    js = json.loads(meas[meas.rfind("{"):meas.rfind("}") + 1])
    ln = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:"
          f"measured_LRA={js['input_lra']}:measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    dst = outdir / f["name"]
    subprocess.run([ff, "-y", "-v", "error", "-i", str(tmp), "-af", ln + ",aresample=44100",
                    "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact",
                    "-c:a", "libmp3lame", "-q:a", "5", "-ac", "1", str(dst)], check=True)
    tmp.unlink()
    log(f"✓ {dst.name} ({dst.stat().st_size / 1e6:.1f} MB)")
    return dst