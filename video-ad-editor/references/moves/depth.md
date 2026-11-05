<!-- بنك الحركات — لحظات العمق. الفهرس: `references/moves/INDEX.md` -->

## 3و) لحظات العمق — الأصل من أول مسودة (6.0، من ريل بوبيان)

ريل بوبيان (اعتمده البنك وانتشر) نجح لأن الموشن كان **عميق من أول نسخة**. الأصل: تتعب على الأداء والموشن — مو أشياء هادية.
البطاقات والأختام والشارات مو ممنوعة؛ استخدمها لما الموضوع يستاهل. بس قبل ما ترسم، **خطّط 2–3 لحظات عمق** للريل وقلها بسطر:
«لحظات العمق: موجة صوتك ورا راسك عند (مقابلة بصوت) · خريطة الكويت عند (أول مرة) · مدار يلف حولك عند (العميل/الشغل/الموظفين)».

| الأداة | متى | شلون |
|---|---|---|
| **ورا الشخص** | أي عنصر (موجة، خريطة، مدار) يمر ورا راسه | قصّ المدى: `node scripts/11_behind_text.js <work> person 5.8-7.7` · ارسم بطبقة `'video'` ثم `MV.person(X)` فوقه |
| **موجة صوته** | «صوت»، «يتكلم»، «مقابلة»، ذكاء اصطناعي يرد | `python scripts/37_env.py <work>` ← `env.js` · `<script src="env.js">` · الارتفاع = `MV.env(t)` |
| **خريطة نقاط** | مكان، «أول مرة بالكويت»، انتشار | `FX.dotMap` بـ`cities:[]` وألوان فاتحة، تكبر ببطء ورا راسه |
| **مدار 3D** | 3 أشياء (عميل · شغل · موظفين) | حلقة بيضوية: النص اللي ورا ينرسم قبل `MV.person` واللي قدّام بعده |
| **شكل من هوية العميل** | رقم، انتقال | قوس شعاره يرتسم = عدّاد (`k` من 0 لـ1) أو مسحة تبلع الشاشة وداخلها اللقطة الجاية |
| **دخلة ون تيك** | تغيّر لقطة | الكاميرا تغوص بالشعار/التابلت (زوم 1→10 + غباش) وتطلع باللقطة الجاية — `MV.frameAt` للفريم المجمّد |
| 🆕 6.1 **إضاءة بلون العميل ورا الشخص** | اسم العميل، «اعتمدوه»، لحظة البراند | الجدار ورا يتصبغ بهويته (`multiply` + هالة `screen`) ثم `MV.person(X)` فوقه — **وجهه بلا أي تعديل لوني**. تشتعل مثل لمبة (رمشات بأول 0.3 ث) |
| 🆕 6.1 **انتقال سبارك** | كل تغيّر مكان/لقطة — نفس اللغة بالريل كله | اللقطة الجاية تنكشف **داخل شكل من هويته** (أيقونة/علامة) يلف ويكبر لين يغطي الشاشة، بحافة بلون التمييز — `sparkReveal` تحت |

```js
/* موجة صوته ورا راسه — طبقة الفيديو، والشخص فوقها */
MV.scene('wave', t => { if (t < 5.86 || t > 7.62) return;
  const n = 43, cx = 540, cy = 790; X.save(); X.fillStyle = '#fff';
  for (let i = 0; i < n; i++) { const x = 40 + i * (1000 / (n - 1)), d = Math.abs(x - cx) / 500;
    const h = 18 + 420 * MV.env(t - d * 0.22) * (1 - d * 0.3); X.fillRect(x - 7, cy - h / 2, 14, h); }
  X.restore(); MV.person(X); }, 'video');

/* خريطة نقاط ورا راسه — ألوان فاتحة، بلا مدن */
const MAPC = Object.assign({}, MV, { P: Object.assign({}, MV.P, { mut: '#FFFFFF', bg: '#FFFFFF', ink: '#FFFFFF' }) });
MV.scene('map', t => { if (t < 11.8 || t > 14.4) return;
  FX.dotMap(MAPC, t, { s: 11.8, y: 140, cities: [], total: null, title: null }); MV.person(X); }, 'video');

/* مدار: اللي ورا قبل الشخص، واللي قدّام بعده (orbitDraw دالتك: front=false يرسم النص الخلفي من الحلقة) */
MV.scene('orbit', t => { if (t < 31 || t > 38) return; orbitDraw(t, false); MV.person(X); orbitDraw(t, true); }, 'video');

/* دخلة ون تيك بنقطة (px,py) عند القطع tc */
function dive(t, tc, px, py) { if (t < tc - 0.38 || t > tc + 0.36) return;
  if (t < tc) { const k = Math.pow(2, 10 * ((t - tc + 0.38) / 0.38) - 10), s = 1 + 9 * k;
    X.save(); X.filter = `blur(${(k * 14).toFixed(1)}px)`; X.translate(px, py); X.scale(s, s); X.translate(-px, -py); MV.video(X); X.restore(); }
  else { const k = 1 - Math.pow(2, -10 * ((t - tc) / 0.36)), s = 1.45 - 0.45 * k;
    X.save(); X.filter = `blur(${((1 - k) * 12).toFixed(1)}px)`; X.translate(540, 900); X.scale(s, s); X.translate(-540, -900); MV.video(X); X.restore(); } }
```

**🆕 6.1 من ريل «1000$ بيوم» (ماجد: «وصل مستوى ثاني») — الوصفتين اللي انمدحت:**
```js
/* إضاءة بلون العميل ورا الشخص: الجدار يتصبغ والوجه ما ينلمس. القصّ للمدى أول (ماك):
   node scripts/11_behind_text.js <work> person 32.3-36.3   ← يغطي on-0.05 لين off+0.45
   الألوان = هوية العميل الرسمية من facts.md (بوبيان: #C8102E · #961428) — لحظة هويته، مو ثيم الريل */
MV.ready(() => { const RL = { on: MV.wordTime(19, 4).s - 0.06, off: MV.lineSpan(20).e + 0.05 };   // «…بوبيان» ← آخر الجملة 20
MV.scene('brandLight', t => {
  if (t < RL.on - 0.05 || t > RL.off + 0.45 || !MV.person.ok()) return;            // ⛔ بلا قصّ لهالفريم لا تصبغ — بيصبغ وجهه
  const fl = t < RL.on + 0.32 ? [1, 0.25, 0.95, 0.4, 1][Math.min(4, Math.floor((t - RL.on) / 0.065))] : 1;   // تشتعل مثل لمبة
  const a = pr(t, RL.on, RL.on + 0.05) * fl * (1 - eio(pr(t, RL.off, RL.off + 0.45))); if (a <= 0) return;
  X.save(); X.globalAlpha = a; X.globalCompositeOperation = 'multiply';              // الجدار الفاتح ياخذ اللون (الغامق ما يبين عليه)
  const g = X.createRadialGradient(560, 820, 60, 560, 900, 1250); g.addColorStop(0, '#FF4D5E'); g.addColorStop(0.45, '#C8102E'); g.addColorStop(1, '#961428');
  X.fillStyle = g; X.fillRect(0, 0, 1080, 1920); X.restore();
  X.save(); X.globalAlpha = a * 0.55; X.globalCompositeOperation = 'screen';         // هالة ناعمة ورا الراس
  const g2 = X.createRadialGradient(560, 760, 20, 560, 760, 620); g2.addColorStop(0, 'rgba(255,90,100,.85)'); g2.addColorStop(1, 'rgba(255,90,100,0)');
  X.fillStyle = g2; X.fillRect(0, 0, 1080, 1920); X.restore();
  MV.person(X);                                                                      // هو فوق الصبغة كما هو — صفر تعديل لوني على صورته
}, 'video'); });

/* انتقال سبارك: tc = أول فريم باللقطة الجاية · shape(Y,x,y,size,rot,col) يرسم شكل هويته معبّى بـcol.
   قبل القطع: A = الفيديو الحي و B = أول فريم باللقطة الجاية مجمّد · بعده: A = آخر فريم مجمّد و B = الحي */
let SPARK_CV = null;   // ⚠️ لا تسمّي ثوابتك AR أو MARK — المحرّك معرّفها (خطأ «already declared» يطيّح سكربت مشاهدك كله)
function sparkReveal(Y, t, tc, shape, o = {}) {
  const d0 = o.d0 || 0.34, d1 = o.d1 || 0.42; if (t < tc - d0 || t > tc + d1) return false;
  const FR = 1 / 30, A = Z => (t < tc ? MV.video(Z) : MV.frameAt(Z, tc - FR)), B = Z => (t >= tc ? MV.video(Z) : MV.frameAt(Z, tc + FR));
  const xi = u => u <= 0 ? 0 : Math.pow(2, 10 * u - 10), xo = u => u >= 1 ? 1 : 1 - Math.pow(2, -10 * u), k = pr(t, tc - d0, tc + d1);
  const g = k < 0.5 ? 0.5 * xi(k * 2) * 0.85 + 0.5 * (k * 2) * 0.15 : 0.5 + 0.5 * xo((k - 0.5) * 2);   // يبطّئ ← ينطلق عند القطع ← يهدى
  const S = lerp(10, 12500, g), rot = -0.9 + 1.6 * eio(k), cx = o.cx || 540, cy = o.cy || 900;
  if (!SPARK_CV) { SPARK_CV = document.createElement('canvas'); SPARK_CV.width = 1080; SPARK_CV.height = 1920; }
  const G = SPARK_CV.getContext('2d');
  A(Y);
  Y.save(); Y.globalAlpha = 1 - pr(k, 0.75, 1); shape(Y, cx, cy, S * 1.045, rot, o.edge || MV.P.acc); Y.restore();   // حافة التمييز ورا القناع
  G.setTransform(1, 0, 0, 1, 0, 0); G.globalCompositeOperation = 'source-over'; G.clearRect(0, 0, 1080, 1920); B(G);
  G.globalCompositeOperation = 'destination-in'; shape(G, cx, cy, S, rot, '#000'); G.globalCompositeOperation = 'source-over';
  Y.drawImage(SPARK_CV, 0, 0); return true;
}
/* شكل الهوية كـPath2D (حاد بأي حجم، بلا تحميل): المسار من SVG شعاره بـviewBox 0 0 100 100 */
const BRAND_PATH = new Path2D('M50 0 L61 39 L100 50 L61 61 L50 100 L39 61 L0 50 L39 39 Z');   // مثال: نجمة — حط مسار علامته
const brandMark = (Y, x, y, s, r, col) => { Y.save(); Y.translate(x, y); Y.rotate(r); Y.scale(s / 100, s / 100); Y.translate(-50, -50); Y.fillStyle = col; Y.fill(BRAND_PATH); Y.restore(); };
MV.scene('sparks', t => { for (const [tc, cx, cy] of [[262 / 30, 760, 905], [1639 / 30, 540, 440]]) sparkReveal(X, t, tc, brandMark, { cx, cy }); }, 'video');
```
- **مركز الشكل** = شي باللقطة يستاهل (الشعار بالخلفية، الجوال، الراس) — بريل 1000$ مرة على الجوال (760, 905) ومرتين فوق الراس (540, 440).
- الشكل صورة (أيقونة PNG)؟ لوّنها بـ`source-in` بكانفس جانبي، وخل الصورة تتحمّل قبل الرسم (`MV.settle` لازم ينتظرها) — Path2D أبسط وأحدّ.
- القطع `tc` من قطعات `cut.json` (فريم أول لقطة جديدة)، و`MV.frameAt` يحتاج `vfr/` (موجود من الخطوة 6). `08_safe_check.js` يحسب الفريم المجمّد فيديو.
- الاثنين بملء الشاشة (`R_FULL`) — `MV.video` و`MV.person` يرسمون الإطار كامل؛ بوضع الكرت تخرب التخطيط.
- نفس الانتقال بكل تغيير مكان (3 مرات بريل الدقيقتين) — اللغة الثابتة جزء من المستوى. و«إضاءة العميل» لحظة وحدة من لحظات العمق الـ2–3، مو بكل جملة.
- هذي أفكار مو قوالب: كل ريل يخترع لحظاته من كلامه وهوية عميله (بوبيان: قوس الشعار عدّاد 90 ثانية، سباق «من أوائل»، كرت أحمر مدرّج).
- أي جملة كلامها مكتوب بالموشن = `nocap` لهالجملة (`references/scenes.md`).
- النص اللي لازم يبين قدّام الشخص (وضع `cutout`) = طبقة `'afterPerson'` أو `window.AFTER_PERSON`.
- `08_safe_check.js` يحسب الفريم المجمّد (`MV.frameAt`) فيديو مو نص — الانتقالات ما تعطي إنذار كاذب (6.0).
