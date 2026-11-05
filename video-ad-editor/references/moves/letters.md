<!-- بنك الحركات — الدفعة 62–73. الفهرس: `references/moves/INDEX.md` -->

## 3ج) الدفعة 62–73 (حروف عربية · ستيكر · ربط · فصول)

`ijamDrop qalamWrite videoText joinSnap kufiGrid redact` (كلام) · `pageTurnRTL` (انتقال) · `tilt3D` (كاميرا) · `stickerFreeze beamConnect lightRays dynamicIsland` (كروت وطبقات).
- **حركات الحروف** (62 نقاط تنزل، 63 القلم، 66 تتلاصق، 67 كوفي): تحلّل السطر المرسوم كامل لأجزاء متصلة (حرف موصول/نقطة/علامة)، فالوصلات ما تنكسر، وكلها تخلص على الكلمة المتصلة الصحيحة. 66 الوحيدة اللي تعرض الحروف منفصلة (بشكلها المنفرد) — هذا معنى الحركة نفسها. ⛔ 62 و66 ممنوعة على نص القرآن.
- 63 تستخدم Aref Ruqaa لو محمّل (محرّك الموشن)، وإلا خط الثيم. 67 تستخدم `kufi` (Noto Kufi بالمحرّك، وخط الثيم بريل الكلام).
- `videoText` ترسم الإطار كامل لين `out`؛ بعده ارجع لـ`MV.video` بنفسك (القطع مطابق). `tilt3D` و`lightRays` و`stickerFreeze` يرسمون الفيديو بنفسهم (مرّر `video`).
- `tilt3D` = نفس الحركة لكل فصل بالفيديو (قاعدة) — غيّر `title` و`num` بس.
- **`stickerFreeze` يحتاج فريم بوقت ثاني** — إضافة المحرّك (17 أكتوبر) بـ`moves-compose.js`:
  `MV.frameAt(Y, t, R?)` فريم الفيديو عند t (`vfr/`)، و`MV.personAt(Y, t, R?)` القصّ عند t (`bt/person/`). أول طلب يحمّل الصورة، و`04_render_frames.js` ينتظر `MV.settle()` ويعيد رسم الفريم قبل اللقطة، فالنتيجة حتمية.
  القصّ لازم يغطي لحظة التجميد: `node scripts/11_behind_text.js <work> person <من-إلى>` والمدى فيه `s`. بلا قصّ ترجع بولارويد للفريم كامل (`videoAt: MV.frameAt`).
```js
MV.ready(() => { const s = MV.wordTime(6, 0).s;
  MV.scene('freeze', t => { if (t >= s && t < s + 2.4) FX.stickerFreeze(MV, t, { s, out: s + 2, person: MV.person, personAt: MV.personAt, video: Y => MV.video(Y), videoAt: MV.frameAt, text: 'وقف!' }); }); });
```
