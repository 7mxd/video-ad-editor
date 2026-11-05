/* كروم وبايثون: نفس البحث على ويندوز وماك ولينكس (نفس الترتيب في _chrome.py).
   const { findChrome, pickPython } = require(path.join(__dirname, '_find_chrome.js')); */
const fs = require('fs'), { spawnSync } = require('child_process');

const NOT_FOUND = 'ما لقيت كروم — حدّد CHROME_PATH';
const MAC_CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const LINUX = ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
const WHICH = ['google-chrome', 'chromium', 'chromium-browser'];

function which(name) {
  const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', [name], { encoding: 'utf8' });
  return r.status === 0 ? (r.stdout || '').split(/\r?\n/).find(Boolean) || null : null;
}

function findChrome(env = process.env, exists = fs.existsSync, whichFn = which) {
  for (const k of ['CHROME_PATH', 'CHROME']) if (env[k]) return env[k];
  const PF = env.ProgramFiles, P86 = env['ProgramFiles(x86)'], LA = env.LOCALAPPDATA;
  const cands = [
    ...[PF, P86, LA].filter(Boolean).map(b => b + '/Google/Chrome/Application/chrome.exe'),
    ...[P86, PF].filter(Boolean).map(b => b + '/Microsoft/Edge/Application/msedge.exe'),
    MAC_CHROME, ...LINUX];
  for (const c of cands) { try { if (exists(c)) return c; } catch (e) { } }
  for (const n of WHICH) { const f = whichFn(n); if (f) return f; }
  throw new Error(NOT_FOUND);
}

/* ويندوز: python3 غالباً اختصار متجر مايكروسوفت يفشل — نجرّب python ثم python3 ثم py (نفس _compat.sh)، ونتخطّى python 2 */
let _py = null;
function pickPython() {
  if (process.env.PY) return process.env.PY;
  if (_py) return _py;
  for (const c of ['python', 'python3', 'py']) {
    const r = spawnSync(c, ['-c', 'import sys; sys.exit(sys.version_info < (3, 8))'], { stdio: 'ignore' });
    if (r.status === 0) return (_py = c);
  }
  return (_py = 'python');
}

module.exports = { findChrome, pickPython };
