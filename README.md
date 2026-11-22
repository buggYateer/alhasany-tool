# أداة الحَسَنِي

أداة لقناة تليجرام مسجد الحَسَنِي: بتاخد **التسجيل الخام** من المايك وتطلّع:

- **ملفات مقصوصة ومضغوطة** — تلاوة العشاء (من غير تكبيرات، والركعة الثانية بقواعدها) والدرس، أو الخطبة وصلاة الجمعة
- **فحص التلاوة** — تنبيه بالتوقيت على أي كلمة زيادة/ناقصة/مختلفة (التعديل بيفضل بإيد المسؤول)
- **مسودة الوصف** بأسلوب القناة — الهاشتاجات، السور، توقيتات الخطبة، رقم الدرس ولينك الدرس السابق
- **برومبت العنوان** — يتبعت لـ Gemini أو يتنسخ لأي شات ذكاء اصطناعي

> المرحلة الحالية: **المحرك** (سطر أوامر). الواجهة (كمبيوتر + موبايل على نفس الواي فاي) جاية.

## التشغيل

المتطلبات: Windows · Python 3.12 · [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) · كارت شاشة NVIDIA (اختياري — من غيره أبطأ)

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m alhasany info "D:\...\261117_1928.wav"
.venv\Scripts\python -m alhasany process "D:\...\261117_1928.wav"
```

أول تشغيل بينزّل موديل Whisper (حوالي 1.6 جيجا).

## الإعدادات والأسرار

- `%APPDATA%\AlhasanyTool\settings.json` — المشايخ وأيامهم، السلاسل، الفولدرات (الافتراضي في `alhasany/data/defaults.json`)
- `%APPDATA%\AlhasanyTool\secrets.json` — توكن البوت ومفتاح Gemini

**الأسرار عمرها ما بتترفع على GitHub** — كل جهاز بيدخلها في الإعدادات بتاعته.

## المكونات

| الملف | الوظيفة |
|---|---|
| `alhasany/asr.py` | التفريغ (faster-whisper) + إصلاح تلقائي لما Whisper يعلّق أو يفوّت جزء |
| `alhasany/cutter.py` | نقاط القص وإخراج الملفات |
| `alhasany/quran.py` | مطابقة التلاوة بالمصحف وفحص الأخطاء |
| `alhasany/captions.py` | قوالب الوصف وبرومبت العنوان |
| `alhasany/hijri.py` | التاريخ الهجري من اسم الملف |
| `alhasany/pipeline.py` | الخط الكامل |

## نص القرآن

`alhasany/data/quran-simple-clean.json` — نص Tanzil (simple-clean) عن طريق alquran.cloud، بيُستخدم للمطابقة فقط.
