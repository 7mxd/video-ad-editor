/* الخطوط المحلية للراسمات بـnode — نفس جدول _fonts.py (اختبار tests/test_fonts.py يتأكد إنهم متطابقين).
   const { fontCss, BASE_URL } = require(path.join(__dirname, '_fonts.js'));
   fontCss('Cairo', [700, 900]) ← @font-face من motion/fonts · عائلة مو بالحزمة ← @import قوقل */
const path = require('path');
const { pathToFileURL } = require('url');

const FONTS_DIR = path.join(__dirname, '..', 'motion', 'fonts');
const BASE_URL = pathToFileURL(FONTS_DIR).href + '/';
const WEIGHTS = {
  'Cairo': { 400: 'Cairo-VF.ttf' },
  'Tajawal': { 400: 'Tajawal-Regular.ttf', 700: 'Tajawal-Bold.ttf', 800: 'Tajawal-ExtraBold.ttf', 900: 'Tajawal-Black.ttf' },
  'IBM Plex Sans Arabic': { 400: 'IBMPlexSansArabic-Regular.ttf', 600: 'IBMPlexSansArabic-SemiBold.ttf', 700: 'IBMPlexSansArabic-Bold.ttf' },
  'Readex Pro': { 400: 'ReadexPro-VF.ttf' },
  'Noto Kufi Arabic': { 400: 'NotoKufiArabic-VF.ttf' },
  'Lalezar': { 400: 'Lalezar-Regular.ttf' },
  'Aref Ruqaa': { 400: 'ArefRuqaa-Regular.ttf', 700: 'ArefRuqaa-Bold.ttf' },
  'Amiri Quran': { 400: 'AmiriQuran-Regular.ttf' },
  'Inter': { 400: 'Inter-VF.ttf' },
};
const VF = new Set(['Cairo', 'Readex Pro', 'Noto Kufi Arabic', 'Inter']);

function nearest(fam, w) {
  const have = WEIGHTS[fam];
  if (VF.has(fam) || have[w]) return have[w] || have[400];
  const ws = Object.keys(have).map(Number);
  ws.sort((a, b) => Math.abs(a - w) - Math.abs(b - w) || (w >= 500 ? b - a : a - b));
  return have[ws[0]];
}

function fontCss(family, weights, baseUrl = BASE_URL) {
  const ws = [...new Set(weights.map(Number))].sort((a, b) => a - b);
  if (WEIGHTS[family]) return ws.map(w =>
    `@font-face{font-family:'${family}';font-style:normal;font-weight:${w};src:url('${baseUrl}${nearest(family, w)}')}`).join('\n');
  return `@import url('https://fonts.googleapis.com/css2?family=${family.replace(/ /g, '+')}${ws.length ? ':wght@' + ws.join(';') : ''}&display=swap');`;
}

module.exports = { fontCss, BASE_URL, FONTS_DIR, BUNDLED: Object.keys(WEIGHTS) };
