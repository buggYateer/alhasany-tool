"""مطابقة التلاوة بنص المصحف: تحديد السور والآيات + فحص الأخطاء (تنبيه فقط)."""
import difflib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

QURAN = Path(__file__).parent / "data" / "quran-simple-clean.json"
_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
FATIHA_TXT = ("الحمد لله رب العالمين الرحمن الرحيم مالك يوم الدين اياك نعبد واياك نستعين "
              "اهدنا الصراط المستقيم صراط الذين انعمت عليهم غير المغضوب عليهم ولا الضالين")


def norm(s):
    s = _DIAC.sub("", s)
    s = re.sub("[إأآٱا]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")
    s = re.sub(r"[^ء-ي\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Quran:
    _inst = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
            cls._inst._load()
        return cls._inst

    def _load(self):
        data = json.loads(QURAN.read_text(encoding="utf-8"))["data"]["surahs"]
        self.names, self.ayahs = {}, []
        for s in data:
            self.names[s["number"]] = _DIAC.sub("", s["name"]).replace("ٱ", "ا").replace("سورة ", "").strip()
            for a in s["ayahs"]:
                self.ayahs.append((s["number"], a["numberInSurah"], norm(a["text"]).split()))
        df = Counter()
        self.index = defaultdict(list)
        for i, (_, _, w) in enumerate(self.ayahs):
            for t in set(w):
                df[t] += 1
                self.index[t].append(i)
        n = len(self.ayahs)
        self.idf = {t: math.log(n / c) for t, c in df.items()}

    def best(self, text):
        words = set(norm(text).split())
        score = Counter()
        for w in words:
            idf = self.idf.get(w)
            if idf and idf > 2.0:
                for i in self.index[w]:
                    score[i] += idf
        if not score:
            return None
        i, sc = score.most_common(1)[0]
        su, ay, w = self.ayahs[i]
        tot = sum(self.idf.get(x, 0) for x in set(w)) or 1e-9
        cover = sum(self.idf.get(x, 0) for x in set(w) if x in words) / tot
        return su, ay, sc, cover

    def runs(self, texts):
        """[(اسم السورة, رقمها, من, إلى)] بترتيب التلاوة، من غير الفاتحة."""
        hits = []
        for t in texts:
            r = self.best(t)
            if r and r[2] >= 8 and r[3] >= 0.35:
                hits.append((r[0], r[1]))
        out = []
        for su, ay in hits:
            if out and out[-1][0] == su and 0 <= ay - out[-1][2] <= 15:
                out[-1][2] = max(out[-1][2], ay)
            elif out and out[-1][0] == su and out[-1][1] <= ay <= out[-1][2]:
                continue
            else:
                out.append([su, ay, ay])
        res = [(self.names[s], s, a, b) for s, a, b in out if s != 1]
        # مقاطع آية واحدة وسط سورة تانية غالبًا مطابقة غلط
        return [x for i, x in enumerate(res) if x[2] != x[3] or len(res) == 1 or
                not (0 < i < len(res) - 1 and res[i - 1][1] == res[i + 1][1])]

    def ref_words(self, su, a, b):
        out = []
        for s, ay, w in self.ayahs:
            if s == su and a <= ay <= b:
                if ay == 1 and su not in (1, 9) and w[:4] == ["بسم", "الله", "الرحمن", "الرحيم"]:
                    w = w[4:]
                out += [(x, ay) for x in w]
        return out


def check_recitation(words, q=None):
    """مقارنة كلمات التلاوة المسموعة (list of (t, word)) بالمصحف — بيرجع تنبيهات بالتوقيت.
    تنبيه بس: Whisper نفسه ممكن يغلط، والقرار بالسمع."""
    q = q or Quran()
    heard = [norm(w) for _, w in words]
    heard = [h for h in heard if h and h != "امين"]
    W = [(t, norm(w)) for t, w in words if norm(w) and norm(w) != "امين"]
    if not heard:
        return []
    chunks = [" ".join(heard[i:i + 12]) for i in range(0, len(heard), 8)]
    runs = q.runs(chunks)
    # الفاتحة: موجودة لو «مالك يوم الدين» في أول الكلام (Whisper ساعات بيفوّت أولها)
    has_f = "مالك يوم الدين" in " ".join(heard[:25])
    ref = [(x, 0, False) for x in norm(FATIHA_TXT).split()] if has_f else []
    # المرجع = كل المقاطع اللي اتعرفت بالترتيب، مع آية احتياطي قبل/بعد (متعلّمة pad — نقصها مش غلط)
    for _, su, a, b in runs:
        ref += [(x, ay, ay < a or ay > b) for x, ay in q.ref_words(su, max(1, a - 1), b + 1)]

    def chars(ws):
        s, own = [], []
        for k, w in enumerate(ws):
            for ch in w:
                s.append(ch)
                own.append(k)
        return "".join(s), own
    rs, rown = chars([x for x, _, _ in ref])
    hs, hown = chars(heard)
    sm = difflib.SequenceMatcher(a=rs, b=hs, autojunk=False)
    issues = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or max(i2 - i1, j2 - j1) < 3 or not hown or not rown:
            continue
        wj1 = hown[min(j1, len(hown) - 1)]
        wj2 = hown[min(max(j2 - 1, j1), len(hown) - 1)]
        wi1 = rown[min(i1, len(rown) - 1)]
        wi2 = rown[min(max(i2 - 1, i1), len(rown) - 1)]
        got = " ".join(heard[wj1:wj2 + 1]) if op != "delete" else ""
        exp = " ".join(x for x, _, _ in ref[wi1:wi2 + 1]) if op != "insert" else ""
        # ناقص في الأول/الآخر (قبل أول كلمة اتسمعت أو بعد آخر كلمة) أو في آية الاحتياط ← مش غلط
        pads = [p for _, _, p in ref[wi1:wi2 + 1]]
        if op == "delete" and (j1 == 0 or j1 >= len(hs) or (any(pads) and pads.count(False) <= 1)):
            continue
        kind = {"replace": "مختلفة", "delete": "ناقصة", "insert": "زيادة"}[op]
        if op == "insert" and got and got in " ".join(heard[max(0, wj1 - 25):wj1]):
            kind = "إعادة"
        if got.startswith("سمع") or len(exp.split()) > 6 or len(got.split()) > 8:
            continue
        issues.append({"t": W[wj1][0], "kind": kind, "expected": exp, "heard": got, "ayah": ref[wi1][1] if ref else 0})
    return issues
