#!/bin/bash
# فحص وتجهيز الأدوات.  ./00_setup.sh          → يفحص ويقول وش ناقص
#                      ./00_setup.sh --install → ينزّل الناقص (بعد إذن المستخدم)
#                      ./00_setup.sh --extras  → الإضافات الاختيارية: تنظيف صوت ذكي · نبض · بحث بالمعنى
# ✏️ معدّل ليشتغل على ويندوز وماك ولينكس.
. "$(dirname "$0")/_compat.sh"
INSTALL=0; [ "$1" = "--install" ] && INSTALL=1
MISS=(); OK=(); NOTE=()
have(){ command -v "$1" >/dev/null 2>&1; }
line(){ printf '%s\n' "$1"; }

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) OS=win ;;
  Darwin) OS=mac ;;
  *) OS=linux ;;
esac
SKILL="$(abspath "$(dirname "$0")/..")"
# ☁️ بيئة سحابية / جوال (6 أكتوبر 2026 — قرار ماجد: ما فيه «ما يصير»): بدل ما نوقف، ننبّه ونكمّل بالمسار البديل.
#    هنا تنزيل موديل وِسبر الأصلي قد يكون محجوب وما فيه واجهة، فنستخدم السلّم بـreferences/any-environment.md
#    (faster-whisper · MODNet · كروم بلا واجهة + ffmpeg). الجلسة الأولى على الجوال أثبتت إنه يشتغل.
if [ "$OS" = linux ] && { [ -n "$CLAUDE_SANDBOX" ] || [ ! -d /Applications ]; } && ! curl -sI -m 8 https://openaipublic.azureedge.net >/dev/null 2>&1; then
  echo "☁️ بيئة سحابية (جوال/ويب): وِسبر الأصلي محجوب هنا — نكمّل بالبدائل: faster-whisper للتفريغ، MODNet لقص الشخص، كروم بلا واجهة للرسم."
  echo "   اقرأ references/any-environment.md. ما توقف ولا تقول للمستخدم «ما يصير»."
  CLOUD=1
fi

# ⛔ ما فيه تحديث ذاتي ولا فحص إصدار بالشبكة: التحديث يكون من مدير الإضافات (claude plugin update) أو git pull بيد المستخدم.

# ➕ الإضافات (v3.9، أفكار Palmier) — اختيارية، السكل يشتغل بدونها وكل وحدة ترجع للطريق القديم لو ناقصة:
#    ‹deep-filter› تنظيف صوت ذكي (02c) · ‹transformers› البحث بالمعنى (26)
# 🆕 6.0: pip القديم (قبل 23) ما يعرف --break-system-packages — كان يطلّع «no such option» ويفشل التنصيب.
#    نجرّب عادي ← لو pip يعرف الخيار نجرّبه ← وإلا --user (يشتغل بكل نسخ pip وبلا صلاحيات مدير).
pip_in(){ "$PY" -m pip install --quiet "$@" 2>/dev/null && return 0
  if "$PY" -m pip install --help 2>/dev/null | grep -q -- '--break-system-packages'; then
    "$PY" -m pip install --quiet --break-system-packages "$@" && return 0
  fi
  "$PY" -m pip install --quiet --user "$@"; }
extras_status(){
  local e=()
  { [ -x "$SKILL/bin/deep-filter" ] || [ -x "$SKILL/bin/deep-filter.exe" ] || have deep-filter; } && e+=("تنظيف-الصوت✅") || e+=("تنظيف-الصوت—")
  "$PY" -c "import transformers,PIL" 2>/dev/null && e+=("البحث-بالمعنى✅") || e+=("البحث-بالمعنى—")
  "$PY" -c "import cv2" 2>/dev/null && e+=("البلر✅") || e+=("البلر—")
  [ -s "${VAE_HOME:-$HOME/.video-ad-editor}/models/face_detection_yunet_2023mar.onnx" ] && e+=("وجوه-البلر✅") || e+=("وجوه-البلر—")
  echo "${e[*]}"
}
if [ "$1" = "--extras" ]; then
  pipx2(){ pip_in "$@"; }
  mkdir -p "$SKILL/bin"
  DFV=0.5.6
  case "$OS-$(uname -m)" in
    mac-arm64)          T=aarch64-apple-darwin ;;
    mac-x86_64)         T=x86_64-apple-darwin ;;
    win-*)              T=x86_64-pc-windows-msvc.exe ;;
    linux-x86_64)       T=x86_64-unknown-linux-musl ;;
    *)                  T="" ;;
  esac
  DF="$SKILL/bin/deep-filter"; [ "$OS" = win ] && DF="$DF.exe"
  if [ -n "$T" ] && [ ! -x "$DF" ]; then
    line "⏬ تنظيف الصوت الذكي (DeepFilterNet3، ~20 ميقا)…"
    if curl -sfL -m 180 -o "$DF" "https://github.com/Rikorose/DeepFilterNet/releases/download/v$DFV/deep-filter-$DFV-$T" \
       && [ "$(wc -c < "$DF")" -gt 1000000 ]; then
      # 🔒 بصمة SHA-256 مثبّتة (checksums.txt جنب هالسكربت) — لو ما طابقت نحذف الملف
      WANT="$(awk -v f="deep-filter-$DFV-$T" '$2==f{print $1}' "$(dirname "$0")/checksums.txt" 2>/dev/null | tr -d '\r')"
      if have sha256sum; then GOT="$(sha256sum "$DF" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$DF" | awk '{print $1}')"; fi
      if [ -z "$WANT" ] || [ "$GOT" != "$WANT" ]; then
        rm -f "$DF"; line "   ⚠️ البصمة ما طابقت (checksums.txt) — حذفته، يبقى فلتر ffmpeg العادي"
      else
      chmod +x "$DF"; [ "$OS" = mac ] && xattr -d com.apple.quarantine "$DF" 2>/dev/null
      "$DF" --help >/dev/null 2>&1 && line "   ✅ جاهز" || { rm -f "$DF"; line "   ⚠️ نزل بس ما اشتغل — يبقى فلتر ffmpeg العادي"; }
      fi
    else rm -f "$DF"; line "   ⚠️ ما قدرت أنزّله — يبقى فلتر ffmpeg العادي"; fi
  fi
  "$PY" -c "import torch" 2>/dev/null || { line "⏬ torch (أساس الموديلات)…"; pipx2 torch; }
  "$PY" -c "import transformers,PIL" 2>/dev/null || { line "⏬ البحث بالمعنى (transformers — الموديل ~1.5 قيقا ينزل أول بحث)…"; pipx2 "transformers>=4.49" pillow sentencepiece protobuf || line "   ⚠️ فشل"; }
  # البلر (blur_track.py): python -m pip install --no-deps opencv-python-headless==4.10.0.84
  #   ⛔ لازم --no-deps ومثبّت: بدونه ينزل numpy 2 ويخرب torch/whisper (numpy يبقى 1.26.x)
  "$PY" -c "import cv2" 2>/dev/null || { line "⏬ البلر (opencv)…"; pipx2 --no-deps opencv-python-headless==4.10.0.84 || line "   ⚠️ فشل"; }
  # وجوه البلر التلقائي (YuNet ~0.2 ميقا، بصمة بـchecksums.txt) — بدونه الوجوه بالطريق الثاني (keyframes + boxes)
  YN="face_detection_yunet_2023mar.onnx"; VM="${VAE_HOME:-$HOME/.video-ad-editor}/models"
  if [ ! -s "$VM/$YN" ]; then
    line "⏬ نموذج الوجوه (YuNet)…"; mkdir -p "$VM"
    if curl -sfL -m 120 -o "$VM/$YN" "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/$YN"; then
      WANT="$(awk -v f="$YN" '$2==f{print $1}' "$(dirname "$0")/checksums.txt" 2>/dev/null | tr -d '')"
      if have sha256sum; then GOT="$(sha256sum "$VM/$YN" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$VM/$YN" | awk '{print $1}')"; fi
      if [ -z "$WANT" ] || [ "$GOT" != "$WANT" ]; then rm -f "$VM/$YN"; line "   ⚠️ البصمة ما طابقت — حذفته"; else line "   ✅ جاهز"; fi
    else rm -f "$VM/$YN"; line "   ⚠️ ما قدرت أنزّله — الوجوه بالطريق الثاني"; fi
  fi
  line "الإضافات: $(extras_status)"
  exit 0
fi

have ffmpeg  && OK+=("ffmpeg")  || MISS+=("ffmpeg")
have ffprobe && OK+=("ffprobe") || MISS+=("ffprobe")
"$PY" -c "import whisper" 2>/dev/null && OK+=("whisper") || MISS+=("whisper")
"$PY" -c "import numpy"   2>/dev/null && OK+=("numpy")   || MISS+=("numpy")

# كروم: البحث الموحّد (_chrome.py). لو بايثون نفسه مو شغّال بعد، بحث bash بنفس الترتيب
find_chrome(){
  "$PY" "$(dirname "$0")/_chrome.py" 2>/dev/null && return 0
  "$PY" -c "import sys" >/dev/null 2>&1 && return 1   # بايثون شغّال وما لقى كروم
  local k c pf="${ProgramFiles:-${PROGRAMFILES:-}}" p86 la="${LOCALAPPDATA:-}" gc=/Google/Chrome/Application/chrome.exe me=/Microsoft/Edge/Application/msedge.exe
  p86="$(printenv 'ProgramFiles(x86)' 2>/dev/null)"
  for k in "${CHROME_PATH:-}" "${CHROME:-}"; do [ -n "$k" ] && { echo "$k"; return 0; }; done
  for c in "${pf:+$pf$gc}" "${p86:+$p86$gc}" "${la:+$la$gc}" "${p86:+$p86$me}" "${pf:+$pf$me}" \
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser; do
    [ -n "$c" ] && [ -f "$c" ] && { echo "$c"; return 0; }
  done
  for c in google-chrome chromium chromium-browser; do command -v "$c" 2>/dev/null && return 0; done
  return 1
}
CHROME="$(find_chrome)" && OK+=("chrome") || MISS+=("chrome")

# puppeteer-core: يُبحث عنه من مجلد السكل نفسه (هناك ينزّل)
( cd "$SKILL" && node -e "require.resolve('puppeteer-core')" ) 2>/dev/null \
  && OK+=("puppeteer-core") || MISS+=("puppeteer-core")

line "النظام: $OS · بايثون: $PY"
[ -n "$CHROME" ] && line "كروم: $CHROME"
line "الجاهز: ${OK[*]:-لا شيء}"
line "الإضافات (اختيارية — 00_setup.sh --extras): $(extras_status)"
# 🧭 جدول القدرات (AUDIT 8): وش ما يشتغل على هالجهاز — فحص فعلي (swiftc · cv2 · mlx_whisper) بـ_caps.py
CAPS="$("$PY" "$(dirname "$0")/_caps.py" 2>/dev/null)"
if [ -n "$CAPS" ]; then line "$CAPS"
elif ! have swiftc; then line "⛔ ميزات الماك (swiftc/Vision) ما تشتغل هنا: «الكلام ورا الشخص» · قصّ الشخص · تتبّع الوجه والكف · محوّل HDR — قل للمستخدم من البداية"; fi

if [ ${#MISS[@]} -eq 0 ]; then
  line "✅ كل شي جاهز — نقدر نبدأ."
  [ ${#NOTE[@]} -gt 0 ] && printf 'ℹ️  %s\n' "${NOTE[@]}"
  exit 0
fi
line "الناقص: ${MISS[*]}"
if [ $INSTALL -eq 0 ]; then line "شغّل: $0 --install"; exit 10; fi

pipi(){ pip_in "$@"; }
for m in "${MISS[@]}"; do
  case "$m" in
    ffmpeg|ffprobe)
      [ "$m" = ffprobe ] && continue
      line "⏬ ffmpeg…"
      if   [ "$OS" = win ] && have winget; then winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements || NOTE+=("ffmpeg فشل — نزّله من ffmpeg.org وضفه للـPATH")
      elif have brew;  then brew install ffmpeg || NOTE+=("ffmpeg فشل")
      elif have apt;   then sudo apt install -y ffmpeg || NOTE+=("ffmpeg فشل")
      else NOTE+=("نزّل ffmpeg يدوياً من ffmpeg.org وضفه للـPATH"); fi ;;
    whisper) line "⏬ openai-whisper… (الموديل ينزل أول تشغيل، 1.4 قيقا)"
      pipi openai-whisper || NOTE+=("whisper فشل") ;;
    numpy)   pipi numpy || NOTE+=("numpy فشل") ;;
    puppeteer-core) line "⏬ puppeteer-core…"
      # npm ci = النسخة المقفولة بـpackage-lock.json، وما يعدّل package.json (التنصيب العادي كان يرفع النسخة ويوسّخ المستودع)
      ( cd "$SKILL" && npm ci --silent --no-audit --no-fund ) || NOTE+=("puppeteer-core فشل") ;;
    chrome) NOTE+=("كروم مو منصّب — نزّله من google.com/chrome أو حدّد CHROME_PATH") ;;
  esac
done

FAIL=0
have ffmpeg || FAIL=1
"$PY" -c "import whisper,numpy" 2>/dev/null || FAIL=1
find_chrome >/dev/null || FAIL=1
( cd "$SKILL" && node -e "require.resolve('puppeteer-core')" ) 2>/dev/null || FAIL=1
[ ${#NOTE[@]} -gt 0 ] && printf '⚠️  %s\n' "${NOTE[@]}"
[ $FAIL -eq 0 ] && line "✅ كل شي جاهز الحين." || { line "❌ باقي ناقص — شوف الملاحظات فوق."; exit 11; }
