# الأسلوب: مونتاج على الصوت (voice-montage)

**متى:** مقاطع تمشي على صوت ملقى — قصيدة أو سرد — بلا متحدث للكاميرا. أو مقاطع هادية بلا نبضة واضحة.
**الخطوات:** `references/montage.md`، بس القطع على وقفات السطور مو على النبضة. البطاقة تغلب هذي الافتراضيات.

## القص على وقفات السطور
1. الصوت ← `<work>/a.wav` (`ffmpeg -v error -i <الصوت> -vn -ac 1 -ar 16000 -y <work>/a.wav`)، ونفس الملف ← `<work>/bg-audio.mp3`.
2. `python scripts/approach.py <work> --pauses` ← يفرّغ لو ناقص، ويكتب `<work>/pauses.json` (نص كل فراغ بين سطرين).
3. `python scripts/12_montage.py <work> plan --beats <work>/pauses.json --on beats --shot 3` — كل قطعة على وقفة.
4. `python scripts/12_montage.py <work> build <work>/montage.mp4 --xfade 0.8` — تلاشٍ بطيء بين اللقطات.
- 🆕 `--shot 3` و`--xfade 0.8` افتراضيات جديدة لهالأسلوب (ما لها مقابل بـupstream؛ المواصفة تطلب «تلاشٍ بطيء») — البطاقة تغلبها.
- ما فيه كلام ولا نبضة؟ نفس `--xfade 0.8` على `plan --shot 3` بلا `--beats`.

## الترجمة
- `captions` بالبطاقة يحكم. قصيدة (`poem: true`) والبطاقة ما قالت ← اسأل مرة، واحفظ الجواب بالبطاقة.
- on أو both ← `.srt` بس (مسار المونتاج ما يرسم كابشن على الفيديو — قله بجملة): صحّح `fixes.json` ثم `02_captions.py` و`09_srt.py`. off ← `.srt` بس.
- ⛔ **لا تخترع كلام ما قاله** — القصيدة حرفياً.

## الصوت
`bash scripts/06b_master.sh <work> <work>/montage.mp4 <work>/montage-master.mp4` — الصوت الملقى هو الخلفية.
