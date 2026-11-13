# Changelog

## 1.1.3 — 2026-11-13

### Added

- **Barcode bars in a route B box:** an item in `boxes.json` can say `"kind": "bars"` (default `"text"`; any other value exits 2 naming `kind`). Bars look alike at every height, so a tracked box can slide short of them. A `bars` box grows by 0.6 × its short side across the bars (`BOX_PAD_BARS`), except on a side another blurred target already covers: that side keeps the normal margin, so a text line next to the barcode stays as sharp as before. When both sides are covered, both get 0.6 × (privacy first). `boxes` tracks text items first and bars items last, so it knows where the text lines are.

### Fixed

- **Tracker drift on fast, motion-blurred moves:** every tracked frame is now checked against its anchor (warped back, normalised correlation ≥ 0.5). A frame that fails is found again from the motion of its checked neighbours, against a template smeared by that motion. Before, the tracker drifted while still reporting high confidence.
- **An anchor box that holds only part of the line** (it ran off the frame edge, or glare hid its end): its neighbours' extent is carried to it, along the line only, so a nearby line stays sharp.
- **A box stretched by ECC:** ECC may move and turn the patch, but not stretch either side by more than 8 %. On bars it had stretched boxes by up to 60 %.
- **A box whose shape went wrong between anchors:** each frame uses the anchor's box moved, scaled and turned to fit the tracked patch, not the patch's own shape.
- **Bar sides on a repeated time:** when two boxes of one item share a `t`, the first one wins, for its bar sides too. Only tracked or widened frames count as neighbours when choosing bar sides (held and lost frames don't).

### Not changed

- The text-line margin stays at 0.35 × the short side. On the real clip, the line just above the barcode is still blurred on part of the clip because of the certificate's own margin.

## 1.1.2 — 2026-11-09

### Fixed

- **A subagent box that misses part of the text:** before tracking, `boxes` snaps each box to the ink of the text line it sits on (edge rows around its strongest row, then the columns of those rows). A box that missed the first character or the tops of the characters grows to cover them; a box is never made smaller.
- **A thin text line lost by the tracker:** a box tight to one small line has too few features to follow. `boxes` now tracks a patch one short side taller above and below the box and maps the result back onto the box through the same homography. On a real clip this took the lost frames of a certificate line from 126 to 0. Snapping and the taller patch apply only to a text-line box (long side at least 3 × the short side); any other box is tracked as drawn.
- **Fast motion:** `references/blur.md` says to run `keyframes --every 1 --max 16` when the camera moves fast. With an anchor only every 2 s the tracker drifted between anchors while still reporting high confidence.

### Not changed

- The route B margin stays as in 1.1.1 (largest of 6 px, 0.35 × short side, 0.04 × long side, on every side), and the subagent is still asked for a box with a margin. A tighter top and bottom margin kept the line above the number sharp, but on fast motion it left digits readable between anchors. Privacy comes first, so a line just above or below the blurred text can still lose its edge.

## 1.1.1 — 2026-11-09

### Fixed

- **Text at the edge of a box stayed readable:** route B boxes (`keyframes` → `boxes`) grow on every side by the largest of 6 px, 0.35 × the box's short side and 0.04 × its long side, following the tracked perspective. A box drawn tight to the text no longer leaves the first or last characters sharp. The subagent prompt in `references/blur.md` asks for a margin on all sides.
- **One soft keyframe stopped the whole item:** when a keyframe is too blurred to track from (too few features), `boxes` drops that anchor, prints a note and tracks the item from its other anchors. It still exits 2 when no anchor is usable.
- **Malformed `boxes.json`:** exits 2 with one Arabic line naming the bad field (`id`, `t`, `box`, `items`, `not_found`) instead of a Python traceback.
- **`--replace` that finds nothing:** `boxes` and `detect` now refuse (exit 2) and say the old `blur.json` was kept, instead of silently leaving the old targets in place.
- **Stale keyframes:** `kf/keyframes.json` stores the video's width, height, fps and frame count; `boxes` refuses (exit 3, as `apply` and `qa` do) when the video does not match.
- **Docs:** `references/blur.md` names `<work>/kf/keyframes.json` everywhere.

## 1.1.0 — 2026-11-08

### Added

- **Auto-detect blur:** `blur_track.py detect --kinds qr,barcode,face` finds QR codes, barcodes and faces by itself (built-in OpenCV detectors; faces use the 0.2 MB YuNet model fetched by `00_setup.sh --extras`, pinned in `checksums.txt`). Each instance is its own target; barcode boxes are measured from the bars, since the detector's own box is rough.
- **Anything named in words:** `keyframes` exports up to 12 frames (every ~2 s plus scene cuts); a subagent returns boxes as JSON; `boxes` tracks each item through the video.
- **QA sheet shows clear frames:** up to 6 frames with no blur are added, so an item the detector missed is visible in the one review.

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
