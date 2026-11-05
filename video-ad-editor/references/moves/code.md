<!-- بنك الحركات — الاستخدام بالكود (الحركات 1–50 وكل الحركات). الفهرس: `references/moves/INDEX.md` -->

## 3) الاستخدام بالكود

**بمحرّك الموشن** (`motion/` — فيلم الموشن، الونشوت، أي مشهد ينرسم بـ`render.js`): نادِ الدالة مباشرة.
```js
draw(t, lt, ctx) {
  const { X, P, FX } = ctx;
  X.fillStyle = P.bg; X.fillRect(0, 0, ctx.W, ctx.H);
  FX.riseUp(ctx, t, { text: 'الفكرة أهم من الأداة', s: ctx.wordTime('l2', 0).s, accent: [1] });    // 3 طلعة متتابعة
  FX.whip(ctx, t, { s: 4.2, A: Y => drawIntro(Y), B: Y => drawStats(Y) });                         // 11 سحبة
  const tau = FX.ramp(t, { hit: ctx.wordTime('l3', 2).s });                                          // 20 تبطيء الضربة: استخدم tau مكان t
}
```
- الألوان من `ctx.P` (ثيم المستخدم) تلقائياً. لا تمرر ألوان ثابتة.
- `o.s` لازم يكون توقيت كلمة حقيقية (`ctx.wordTime`). `FX.caption` ياخذ `line: 'l2'` ويتزامن مع الصوت كلمة كلمة.
- الانتقالات (`crossZoom softWipe iris whip zoomWipe dotZoom dipFade slideOver clockWipe slices glitch flip lightLeak` و`compare`) تاخذ `A` و`B` كدوال ترسم الإطار كامل. حطها داخل مشهد واحد مكان انتقال المحرّك.
  `glitch` و`flip` يرسمون A/B على الإطار نفسه وياخذون لقطة منه، فأي FX داخل A/B (مثلاً `MV.panel(Y, () => FX.ringStat(MV, t, …))`) يطلع صح.
- الكاميرا (`pushIn pullOut handheld kenBurns snapZoom shake`) تلف `draw`؛ `rackFocus` و`dollyZoom` ياخذون `back` و`front`؛ `parallax` ياخذ `layers:[{draw, depth}]`. بريل الكلام حطها بطبقة `'video'`.
- `lowerThird` تحت يمين داخل المنطقة الآمنة (y ≤ 1500 و x ≤ 920) — لا تحرّكه لزاوية الأزرار.
- `jcut` و`matchCut` قواعد توقيت، مو رسم: J-cut = صوت اللقطة الجاية يسبق صورتها بـ4–12 فريم. القطع المطابق = الشكل نفسه بنفس المكان والحجم على فريم القص.

**بريل الكلام** (`compose.html`): نفس الدوال، بس الـctx اسمه `MV` (من `scripts/moves-compose.js`: أدوات النص والتوقيت وألوان `theme.json` وخطه فوق كانفس المحرّك).
`compose.REFERENCE.html` يحمّل `moves.js` و`moves-compose.js` من مجلد الشغل، و`04_render_frames.js`/`08_safe_check.js` ينسخونهم وحدهم لو ناقصين.
مشاهدك بآخر `compose.html` (بعد سطر التحميل):
```js
MV.ready(() => {                                   // caps.json يوصل بـinit — أي wordTime/lineSpan برّا الرسم داخل ready
  MV.hideCaption(MV.lineSpan(0).s, MV.lineSpan(2).e + 0.5);                 // FX.caption بدال كابشن المحرّك
  MV.scene('cap', t => { const n = [2,1,0].find(i => t >= MV.lineSpan(i).s);   // آخر جملة بدت — الجاية تاخذ مكانها
    if (n !== undefined && t < MV.lineSpan(n).e + 0.5) FX.caption(MV, t, { line: n, y: 1280, out: MV.lineSpan(n).e }); });   // 1 · يقعد بعد صوته ويطلع (6.1)
  const s = MV.wordTime(3, 0).s;
  MV.scene('push', t => { if (t >= s && t < MV.lineSpan(4).e)
    FX.pushIn(MV, t, { s, to: 1.18, focus: [540, 560], blur: false, draw: Y => MV.video(Y) }); }, 'video');   // 12 طبقة الفيديو
  const w = MV.wordTime(5, 0).s - 0.3;
  MV.scene('whip', t => { if (t >= w && t < MV.lineSpan(5).e)
    FX.whip(MV, t, { s: w, A: Y => MV.video(Y), B: Y => MV.panel(Y, () => FX.riseUp(MV, t, { text: 'الفكرة', s: w + 0.35 })) }); });   // 11
});
```
- السطر = رقم الجملة بـ`caps.json` (`MV.wordTime(3, 0)` = أول كلمة بالجملة 3). `line: 0` يشتغل.
- `MV.video(Y, R?)` يرسم فريم الفيديو الحالي (ملء الشاشة افتراضياً) — هو مشهد A/B للانتقالات و`draw` لحركات الكاميرا.
- `MV.panel(Y, fn)` = خلفية الثيم + رسمك: شاشة كاملة بين لقطتين. كابشن المحرّك يبقى فوقها.
- `MV.scene(name, fn, 'video')` لحركة تشتغل على الفيديو نفسه (pushIn/pullOut) فالكابشن يبقى فوقها؛ بدون طبقة = فوق الفيديو وتحت الكابشن.
- ⛔ 6.1 **العنصر ما يختفي مع آخر كلمة:** `out` (بداية الطلعة) = آخر كلمة — و+0.3 لو طلعة الحركة أسرع من 0.4 ث (مثل `speechBubble`) — ونافذة المشهد لين `out + 0.7`. لا تقطع النافذة عند `lineSpan(n).e` (`motion-rules.md` §3).
- ⚠ `FX.caption` بثيم غامق: الحدّ حول الكلمات يصير الأغمق من `ink`/`bg` تلقائياً، والكلمة الحالية بلون `onAcc` فوق الكبسولة.
