<!-- بنك الحركات — حركات المتحدث المقصوص 51–61. الفهرس: `references/moves/INDEX.md` -->

## 3ب) حركات المتحدث المقصوص (51–61)

`orbit couchWall uiWorld frameBreak headlineWall doodleBoil coverStory glassType phoneMockup greenScreen paperCut`
- تاخذ `person` (المتحدث مقصوص، إطار كامل) و`video` (الفيديو كامل). `glassType` ياخذ `draw` بدال الاثنين، و`phoneMockup` ياخذ `video` بس.
- **القصّ ماك بس** (`mask: required` و`mac: true` بالكتالوج). جهّزه للمدى قبل الرسم: `node scripts/11_behind_text.js <work> person 12.4-15.8`
  (قصّ بس بلا تأثير ثاني). بالمشهد مرّر `person: MV.person` **كما هو** — FX يسأل `MV.person.ok()`.
- بلا قصّ (مو ماك، أو الفريم برّا المدى) كل حركة ترجع لبديلها لحالها: الفيديو بكرت (المدار يلف حول الكرت، الغلاف فوق الفيديو، القرين سكرين وجهك بفقاعة). `uiWorld` و`doodleBoil` (`mask: optional`) أحلى بالقصّ وتشتغل بلاه.
- `o.out` = وقت الطلعة (ترجع للفيديو بنفس الحركة بالعكس).
```js
MV.ready(() => { const s = MV.wordTime(4, 0).s;
  MV.scene('cover', t => { if (t >= s && t < s + 3) FX.coverStory(MV, t, { s, out: s + 2.5, person: MV.person, video: Y => MV.video(Y), title: 'مكينة' }); }); });
```
