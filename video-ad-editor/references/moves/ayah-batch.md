<!-- بنك الحركات — الدفعة ج: 74 و88–100. الفهرس: `references/moves/INDEX.md` -->

## 3هـ) الدفعة ج: 74 و88–100 (الآية · بوست · فاتورة · بحث · باب · صدى)

`ayahCalm echoStack warpWave` (كلام) · `bentoCut doorway lumaMelt` (انتقالات، تاخذ `A` و`B`) · `bodyFollow swishSettle motionEcho` (كاميرا) · `postCard palmHold receiptPrint searchBar pointerCursor` (كروت وطبقات).

**⛔ 74 آية بسكينة (`ayahCalm`) — قواعد القرآن قبل الحركة:**
- **النص من مصدر موثوق بس**: Tarteel MCP (`search_ayahs_text`) أو quran.com بالرسم العثماني، ومرّره `text` **كما جا حرفاً بحرف**. ⛔ لا تكتب آية من الذاكرة، ولا تعدّل حرف ولا تشكيل. الدالة ما تغيّر النص: تقسمه على الفراغات بس (وعلامة الوقف مثل ۗ تلتصق بكلمتها).
- ⛔ **62 «نقاط تنزل» ممنوعة نهائياً على نص القرآن** (تفكك الرسم والإعجام)، ومثلها 66 والكشيدة والقلتش وأي حركة كلام ثانية. على الآية: `ayahCalm` بس (وورا الآية `girihBloom` 84 مسموحة — هندسة بلا كائنات).
- `manual: true` بالكتالوج: اللوحة (`plan`) ما تختارها أبداً — تستخدمها بس لما الفيديو فيه آية.
- الخط `Amiri Quran` (عثماني، SIL OFL — `motion/fonts/AmiriQuran-Regular.ttf`): بالمحرّك محمّل؛ بريل الكلام `04_render_frames.js`/`08_safe_check.js` ينسخونه لمجلد الشغل لما compose.html فيه `ayahCalm`، و`MV.needFont` يحمّله (الفريم ينتظر الخط).
- رقم الآية داخل ۝: `digits: 'arabic'` (الافتراضي، ٢٨ — ينرسم مباشرة بلا تحويل الأرقام الغربي حق المحرّك) أو `'western'`. `surah` فوق، و`ref` (مثلاً `'13 : 28'`) تحت اختياري.
- الخلفية الثيم أو `video` مغمّق 60% — بلا صور كائنات حية فوق الآية. الكلمات تطلع بهدوء وحدة وحدة (`stagger`، أو `times` من توقيت التلاوة).
```js
MV.ready(() => { const s = MV.lineSpan(4).s;   // النص من search_ayahs_text كما هو
  MV.scene('ayah', t => { if (t >= s && t < s + 6) FX.ayahCalm(MV, t, { s, out: s + 5.3, text: AYAH_TEXT, surah: 'الرعد', ayah: 28, ref: '13 : 28' }); }); });
```
**الباقي:**
- `bodyFollow` (89) يحتاج الوجه (`face: MV.faceAt` من `36_facetrack.py` — ماك)؛ بلاه يرجع لـ`handheld` (31). بطبقة `'video'`.
- `motionEcho` (100) يحتاج فريم بوقت ثاني: `videoAt: MV.frameAt`، وبالقصّ (`mask: optional`) `person: MV.person, personAt: MV.personAt` فالصدى على جسمك بس. بلاهم تتخطى. حطها مع `FX.ramp` (20) على نفس الضربة.
- `palmHold` (91) يحتاج الكف (`hand: optional`): `python scripts/29_handtrack.py <work> <من> <إلى>` يطلّع `palm.js` — حطه بـcompose.html ومرّر `palm: MV.palmAt`. بلاه العنصر ثابت تحت يسار.
- `postCard` (88): ⚠ لا تسوي بوست مزيف لشخص حقيقي — يا لقطة حقيقية، يا كلام صاحب الحساب نفسه. بلا شعار أي منصة.
- `receiptPrint` (93) الأسعار بأرقام غربية والعملة من `currency`. `searchBar` (94) و`pointerCursor` (98) سهم ماوس بحبر الثيم؛ `pointerCursor` ياخذ `steps` (عدة نقرات) و`targets` (أزرار يرسمها).
- `swishSettle` (95) بداية مشهد (يلف `draw`)، يكبر لحاله لين ما يبين طرف الفريم. `doorway` (97) و`lumaMelt` (99) يرسمون `A` بكانفس جانبي.
```js
MV.ready(() => { const h = MV.wordTime(3, 2).s;
  MV.scene('echo', t => { if (t >= h - 0.1 && t < h + 0.7) FX.motionEcho(MV, t, { s: h, video: Y => MV.video(Y), videoAt: MV.frameAt, person: MV.person, personAt: MV.personAt }); }, 'video'); });
```
