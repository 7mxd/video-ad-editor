# Changelog

## 1.0.0 — 2026-11-05

First release of this rebuild, based on upstream 6.3.0, commit a69492d ([majedphotos/video-ad-editor](https://github.com/majedphotos/video-ad-editor) by Majed Alzaabi, MIT). Finding numbers refer to [docs/AUDIT.md](docs/AUDIT.md) §3.

### Findings fixed

1. **45k tokens before the first scene:** one router skill; each mode's steps in `references/<mode>.md`; `moves.md` split into `moves/INDEX.md` plus per-family files; situational text moved to on-demand references with a one-line trigger. Mandatory reel reading path 45,126 → 14,944 tokens; a typical reel with motion (plus `moves/depth.md` and `moves/code.md`) reads 22,436, about half of upstream.
2. **`python3` resolves to the Microsoft Store stub on Windows:** docs say `python`; `_compat.sh` and `_find_chrome.js` pick the working interpreter; no bare `python3` call left in scripts (hygiene tests enforce it).
3. **Hand-edit route needs paid DaVinci Resolve Studio:** the route and every mention are removed. No replacement engine is shipped (HyperFrames stays a possible later option in the audit).
4. **Self-update downloads releases and runs `rsync --delete` with no checksum:** removed from `00_setup.sh`, together with the GitHub version check. The plugin manager handles updates.
5. **`deep-filter` downloaded without a checksum:** 0.5.6 downloads are verified against pinned SHA-256 values in `scripts/checksums.txt` and deleted on mismatch.
6. **Studio listens on all interfaces with no auth:** binds `127.0.0.1` by default; `--lan` binds all interfaces and requires a random token on every `/api/` call.
7. **Packaging leftovers:** the stale `video-ad-editor.skill` and the ~30 MB `_pkg/` folder are deleted; three compressed README images are kept in `docs/img/`.
8. **Mac-only features advertised to Windows users:** `00_setup.sh` (step 0) prints a capability block from `scripts/_caps.py`, which checks `swiftc`, `cv2` and `mlx_whisper` on the machine and lists what will not work there; `references/start.md` tells the agent to say so up front, and `references/windows.md` has the full table. Podcast face tracking (`15`, `24`) and the hook centre (`22b`) use Vision when `swiftc` exists (Mac unchanged), otherwise an OpenCV Haar fallback (`scripts/_faces.py`, same JSON), otherwise no tracking (centre crop). Without `swiftc` the podcast plan skips the "head out of the card" scenes. Every `swiftc` call site now stops or falls back with one Arabic line instead of a traceback.
9. **Four overlapping skills costing 1,233 listing tokens:** merged into one skill by fix 1; listing now 278 tokens.
10. **Chrome lookup mac-only or partial in some scripts:** one shared lookup (`_find_chrome.js` and `_chrome.py`) in every renderer: `CHROME_PATH`, then Chrome, then Edge, on Windows, macOS and Linux.
11. **Render fetches Google Fonts:** every family in `motion/fonts` is served locally through generated `@font-face` rules; Google is used only for families that are not bundled.
12. **Docs reference files that don't exist:** dead references removed or fixed (a phone probe script, a clip-ranking script, old skill links); duplicate Windows note removed. A hygiene test checks every `scripts/` name in the docs.
13. **Upstream-specific strings:** partner discount code and `majed-*` install hints removed; setup no longer points at upstream release URLs. The upstream paid-course ad and Instagram group line were also removed from the skill.
14. **Whisper `medium` on CPU is slow on Windows (partly fixed):** the reel path (`scripts/transcribe.py`, used by reel step 4 and `02a_whisper_check.py`) uses faster-whisper (int8, word timestamps) when installed and falls back to openai-whisper with the same JSON output. `--extras` does not install faster-whisper (`pip install faster-whisper` by hand), and podcast, long transcription, seam check and episode cuts (`15`, `18`, `19`, `20`) still call openai-whisper.
15. **Remotion is an unused second engine:** its setup script, template bundle and reference are deleted.
16. **Three lossy JPEG generations:** reel frame extraction now uses `-q:v 2` (measured +17.7 % file size, no time cost).

### New

- **One router skill, five modes:** reel, motion, podcast, montage, cover (plus CapCut export, studio and blur as side routes).
- **Series, approaches, lessons:** series cards and global lessons under `VAE_HOME` (default `~/.video-ad-editor`, untouched by updates); six approach files chosen per video; after approval, corrections become one-line rules (`scripts/lessons.py`, `scripts/approach.py`).
- **Privacy blur:** `scripts/blur_track.py` tracks a marked target (reference image or box), widens the blur on uncertain frames and refuses to render a gap longer than one second unless re-marked or accepted as a full-width band.
- **Token measurement:** `tools/measure_tokens.py --check` measures the listing, the SKILL.md body and the mandatory reel reading path against budgets (300 / 3,000 / 15,000).
- Hygiene tests for removed paths, dead script references, promo strings, `python3` use and attribution.

### Removed

- DaVinci Resolve route and mentions.
- Remotion engine.
- `_pkg/` (README GIFs) and the stale `video-ad-editor.skill`.
- Self-update in `00_setup.sh`.
- Upstream course ad and Instagram group line.

### Visible changes

- **Cairo now actually loads** in podcast compose (upstream asked for Cairo but it never loaded; captions there now use Cairo).
- **Lalezar now loads** (upstream requested weights Google does not serve, so it never loaded); the bundled Regular is used.
- **Tajawal 800 = ExtraBold and IBM Plex Sans Arabic 600 = SemiBold** are bundled — the same files Google served — so those weights look as before, offline.
- Frame extraction uses `-q:v 2`: sharper frames, slightly larger intermediate files.
- **New voice-montage defaults:** `--shot 3 --xfade 0.8` (slow dissolves; no upstream equivalent; tune per series card).
- Plugin renamed to `video-ad-editor`; marketplace `7mxd-plugins`.
