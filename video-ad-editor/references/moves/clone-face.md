<!-- بنك الحركات — الدفعة 75–87. الفهرس: `references/moves/INDEX.md` -->

## 3د) الدفعة 75–87 (نسخ · خريطة · رافعة · طرفية · زجاج · وجه)

`morphWord` (كلام) · `nuqtaCurtain glassLens scanLine` (انتقالات، تاخذ `A` و`B`) · `craneUp punchCut` (كاميرا) · `cloneTrio dotMap rimOutline terminalType lineChartDraw girihBloom speechBubble` (كروت وطبقات).
- **القصّ (ماك):** `cloneTrio` و`rimOutline` (`mask: required`) — بلاه: 3 كروت فيديو / شعاع على إطار كرت. `girihBloom` (`optional`) ورا الشخص بالقصّ، وفوق الفيديو بلاه.
  `cloneTrio` ياخذ `personAt: MV.personAt` (النسخ متأخرة 0.2/0.4 ث) و`videoAt: MV.frameAt` للبديل — نفس شرط القصّ بـ`letters.md`.
- **الوجه (ماك، `face: optional` بالكتالوج)** — `speechBubble` و`punchCut`: إضافة المحرّك (17 أكتوبر):
  `python scripts/36_facetrack.py <work> <من> <إلى>` يطلّع `face.js` (نفس `facetrack.swift` حق البودكاست، منعّم σ=5 فريم). حطه بـcompose.html: `<script src="face.js"></script>`، ومرّر `face: MV.faceAt`.
  `MV.faceAt(t)` = `{x,y,w,h,mx,my}` بإحداثيات الكانفس (بنفس تأطير `MV.video`) أو `null` — والحركة ترجع لمكان افتراضي.
  `punchCut` يثبّت الوجه على أول فريم بكل لقطة (الكاميرا الحقيقية ما تلحق)، والحد ×2.
- `glassLens` العدسة تشيل المشهد الجديد معها (`carry`)، فاللي بنص B يظل كامل داخلها — خل عنوان B كلمة أو كلمتين (أعرض شي ~400px) عشان ما تنقص كلمة على حافتها.
- `scanLine` ياخذ `Aat: MV.frameAt` (القديم مجمّد تحت الخط). `craneUp` ياخذ `A` (الفيديو) و`B` (الكرت الجاي) — بعد `at + 0.5` ارسم `B` بنفسك. الكروت صور ثابتة (`cards`).
- `dotMap` خريطتها مضمّنة (يابسة مبسّطة، من الأطلسي لليابان) — المدن برّا هالمدى ما تبين. `terminalType` الأمر والناتج إنقليزي (خط Menlo/monospace)، والتعليق العربي بسطره.
```js
MV.ready(() => { const s = MV.wordTime(5, 0).s;
  MV.scene('bubble', t => { if (t >= s && t < MV.lineSpan(5).e + 1) FX.speechBubble(MV, t, { s, out: MV.lineSpan(5).e + 0.3, line: 5, face: MV.faceAt }); });   // يقعد بعد صوته (6.1)
  const p = MV.wordTime(7, 0).s;
  MV.scene('cam2', t => { if (t >= p && t < MV.lineSpan(7).e) FX.punchCut(MV, t, { s: p, out: MV.lineSpan(7).e, video: Y => MV.video(Y), face: MV.faceAt }); }, 'video'); });
```
