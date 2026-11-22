"""كتابة الوصف بأسلوب القناة (HTML لتليجرام) + برومبت العنوان للذكاء الاصطناعي."""
from .quran import Quran
from .util import fmt

ONES = ["", "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر"]
UNITS = ["", "الحادي", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع"]
TENS = {2: "العشرون", 3: "الثلاثون", 4: "الأربعون", 5: "الخمسون", 6: "الستون", 7: "السبعون", 8: "الثمانون", 9: "التسعون"}


def ordinal(n):
    """رقم الدرس بالحروف: 39 ← التاسع والثلاثون."""
    if n <= 10:
        return ONES[n]
    if n < 20:
        return ("الحادي" if n == 11 else UNITS[n - 10]) + " عشر"
    t, u = divmod(n, 10)
    if t in TENS and t < 10:
        return TENS[t] if u == 0 else f"{UNITS[u]} و{TENS[t]}"
    return str(n)


def month_tag(settings, month, year):
    return f"#{settings['months'][month - 1]}_{year}هـ"


def sheikh_line(tag):
    return f"لفضيلة الشيخ #{tag} –حفظه الله–"


def surah_phrase(runs):
    """«لفواتح سورة <b>يونس</b>» / «لخواتيم سورتي <b>ق</b> و<b>الذاريات</b>» … من نتيجة المطابقة."""
    if not runs:
        return "تلاوة ندية في صلاة"
    q = Quran()
    counts = {}
    for s, ay, _ in q.ayahs:
        counts[s] = max(counts.get(s, 0), ay)
    names = []
    for name, s, a, b in runs:
        if name not in names:
            names.append(name)
    first, last = runs[0], runs[-1]
    if len(names) == 1:
        n, s, a, b = first[0], first[1], min(r[2] for r in runs), max(r[3] for r in runs)
        if a <= 2 and b >= counts[s] - 1:
            return f"لسورة <b>{n}</b> كاملة"
        if a <= 3:
            return f"لفواتح سورة <b>{n}</b>"
        if b >= counts[s] - 2:
            return f"لخواتيم سورة <b>{n}</b>"
        return f"لما تيسر من سورة <b>{n}</b>"
    two = names[:2]
    ends = all(max(r[3] for r in runs if r[0] == nm) >= counts[next(r[1] for r in runs if r[0] == nm)] - 2 for nm in two)
    pre = "لخواتيم سورتي" if ends else "لما تيسر من سورتي"
    return f"{pre} <b>{two[0]}</b> و<b>{two[1]}</b>"


def recitation(settings, tag, prayer, runs, month, year):
    return (f"🎤 تلاوة ندية {surah_phrase(runs)} في صلاة #{prayer}\n{sheikh_line(tag)}\n\n"
            f"#تلاوات_الفروض {month_tag(settings, month, year)}")


def khutba(settings, tag, title, starts, with_prayer, month, year):
    lines = ["00:00 الخطبة الأولى"]
    if len(starts) > 1:
        lines.append(f"{fmt(starts[1])} الخطبة الثانية")
    if with_prayer and len(starts) > 2:
        lines.append(f"{fmt(starts[2])} الصلاة")
    times = "\n".join(lines) if len(starts) > 1 else ""
    body = f"🎤 #خطبة_الجمعة | <b>{title or '…'}</b>\n{sheikh_line(tag)}\n\n"
    return body + (times + "\n\n" if times else "") + month_tag(settings, month, year)


def lesson(settings, tag, day, title, month, year, series=None, number=None, subtitle=None, verses=None):
    url = settings["channel_url"]
    mt = month_tag(settings, month, year)
    style = (series or {}).get("style", "free")
    if style == "jibreel" and number:
        prev = f'\n\n👈 <a href="{url}{series["last_msg"]}">الدرس السابق ({number - 1})</a>' if series.get("last_msg") else ""
        return (f"🎙 #درس_{day} | {series['name']}\nالدرس {ordinal(number)} | <b>{title or '…'}</b>\n\n"
                f"{sheikh_line(tag)}{prev}\n\n#الدروس {mt}")
    if style == "ayah":
        sub = f"\n\n🔹 <b>{subtitle}</b>" if subtitle else ""
        return (f"🎙 #وقفة_مع_آية | <b>{verses or title or '…'}</b>{sub}\n\n{sheikh_line(tag)}\n\n"
                f"#الدروس #درس_{day} {mt}")
    if style == "fiqh":
        prev = f'\n\n👈 <a href="{url}{series["last_msg"]}">الدرس السابق في سلسلة الفقه</a>' if series.get("last_msg") else ""
        return (f"🎙 #سلسلة_الفقه | <b>{title or '…'}</b>\n\n{sheikh_line(tag)}{prev}\n\n"
                f"#الدروس #درس_{day} {mt}")
    sub = f"\n🔹 {subtitle}" if subtitle else ""
    return f"🎙 #درس_{day} | <b>{title or '…'}</b>{sub}\n\n{sheikh_line(tag)}\n\n#الدروس {mt}"


RULES = """قواعد العنوان (قناة مسجد الحَسَنِي):
- لو الشيخ/الخطيب قال العنوان صريح («خطبة بعنوان…»، «نتحدث الليلة عن…») استخدمه.
- غير كده: العنوان من موضوع الدرس/الخطبة ككل — ممنوع من المقدمة (من «إن الحمد لله نحمده…» لحد «ثم أما بعد»).
- عنوان واحد موحد قصير (2-6 كلمات) — ممنوع «عنوان + و + آية».
- لو الدرس تكملة لسلسلة، اذكر الجزئية اللي اتكلم فيها الدرس ده تحديدًا.
- اكتب العنوان بالعربي الفصيح."""


def title_prompt(kind, sheikh, transcript_text, context=""):
    """برومبت يتنسخ لأي شات ذكاء اصطناعي (أو يتبعت لـ Gemini)."""
    what = "خطبة جمعة" if kind == "khutba" else "درس"
    return (f"ده تفريغ آلي (فيه أخطاء سمع) لـ{what} للشيخ {sheikh} في مسجد الحَسَنِي.\n{context}\n\n{RULES}\n\n"
            f"المطلوب: اقترح عنوان واحد بس، وبعده سطر فيه ملخص الموضوع في جملة.\n\n--- التفريغ ---\n{transcript_text}")


def sample_text(transcript, ranges, max_words=2500):
    """نص الدرس كله لو قصير، أو عينات متوزعة على طوله (مش الأول بس)."""
    words = [w for s in transcript["segments"] for (ws, _, w) in s["words"] if any(a <= ws <= b for a, b in ranges)]
    if len(words) <= max_words:
        return " ".join(words)
    k = 8
    n = max_words // k
    step = (len(words) - n) // (k - 1)
    return " … ".join(" ".join(words[i * step:i * step + n]) for i in range(k))
