# Status — 2026-11-06

Version 1.0.0 on branch `rebuild`, based on upstream 6.3.0 (commit a69492d). Public repo: https://github.com/7mxd/video-ad-editor

## Current state

- One plugin (`video-ad-editor`), one skill, five modes (reel, motion, podcast, montage, cover), plus CapCut export, studio and privacy blur.
- Series cards, per-video approaches and the lessons loop live under `VAE_HOME` (default `~/.video-ad-editor`).
- The paid hand-edit route, the Remotion route, `_pkg/`, the stale `.skill` file and self-update are gone.
- Audit findings 1–16: all fixed. Details in [CHANGELOG.md](CHANGELOG.md).

## Tokens (measured with `python tools/measure_tokens.py --check --json docs/tokens-after.json`, exit 0, re-measured 2026-11-06 after the pre-publish fixes)

| | Upstream 6.3.0 | Now | Budget |
|---|---|---|---|
| Listing, every session | 1,273 | 278 | 300 |
| SKILL.md body, on invoke | 14,616 | 2,990 | 3,000 |
| Mandatory reel reading path | 45,126 | 14,944 | 15,000 |
| Typical real reel (mandatory path + `moves/depth.md` 5,125 + `moves/code.md` 2,367) | ≈ 45k | 22,436 | — |

The 15k budget covers the mandatory path only. A typical reel with motion reads about 22.4k tokens before the first scene: about half of upstream, not a third.

## End-to-end run (2026-11-05, Windows 11)

**Sample.** A public Gulf-Arabic podcast clip from YouTube, 28 s from 421 s in: one speaker, one shot, three-quarter view. Neither file is in the repo; `<URL>` below stands for the clip.

```bash
python -m yt_dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]" --merge-output-format mp4   -o C:/tmp/vae-e2e/src/podcast.mp4 <URL>
ffmpeg -ss 421 -i C:/tmp/vae-e2e/src/podcast.mp4 -t 28 -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k C:/tmp/vae-e2e/sample_landscape.mp4
ffmpeg -ss 421 -i C:/tmp/vae-e2e/src/podcast.mp4 -t 28 -vf "crop=606:1080:946:0,scale=1080:1920:flags=lanczos"   -c:v libx264 -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k C:/tmp/vae-e2e/sample.mp4      # 9:16 around the speaker
```

**Install.** `claude plugin marketplace add .` (from the repo root) · `claude plugin install video-ad-editor@7mxd-plugins` · `claude plugin list` (listed once) · `claude plugin details video-ad-editor@7mxd-plugins` (Skills (1) `video-ad-editor`).

**Reel** (from `video-ad-editor/`, `W=C:/tmp/vae-e2e`):

```bash
bash scripts/00_setup.sh && bash scripts/00_setup.sh --install          # puppeteer-core 25.10.0 via npm ci
cp C:/tmp/vae-e2e/sample.mp4 $W/src.mov && cp scripts/compose.REFERENCE.html $W/compose.html
python scripts/25_scopes.py $W                                           # "leaning blue": not applied
python scripts/01_cut_plan.py $W                                         # 4 pieces, 26.37 s kept
ffmpeg -v error -i $W/src.mov -vn -ac 1 -ar 16000 -y $W/a.wav
python scripts/transcribe.py $W > $W/whisper.log 2>&1                    # openai-whisper medium, 47 s
python scripts/02a_whisper_check.py $W                                   # clean, 3 sentences
python scripts/02_captions.py $W && python scripts/10_script_edit.py $W show
python scripts/03_cut_zoom.py $W
mkdir -p $W/vfr && ffmpeg -v error -i $W/cutz.mp4 -vf fps=30 -q:v 2 -y $W/vfr/%05d.jpg
python scripts/23_headcrop.py $W --from 11.7                             # no-op on Windows -> cardTop set by hand
python scripts/05_sfx.py $W
node scripts/04_render_frames.js $W preview 1.2 5.0 12.0 14.8 20.0 25.5
bash scripts/07_contact_sheet.sh $W $W/sheet.jpg 1.2 5.0 12.0 14.8 20.0 25.5
python scripts/32_midframes.py $W                                        # -> $W/mid_1.jpg
node scripts/04_render_frames.js $W all                                  # 902 frames, 26 s
bash scripts/06_encode.sh $W $W/ad-final.mp4
bash scripts/06b_master.sh $W $W/ad-final.mp4 $W/ad-master.mp4          # -8.59 -> -14.0 LUFS
python scripts/09_srt.py $W ad-master                                    # ad-master.srt / .txt
```

| Input file | Value |
|---|---|
| `theme.json` | `bg #0E2A3B · ink #F5F7FA · acc #F2B33D · clay #C98B18 · mut #98A2B3 · font Tajawal · handle @<channel> · grade false · faceAnchor 0.30 · badgeUntil 0 · capStyle card · outro {l1 <show name>, l2 <guest line>, cta «الحلقة كاملة», word «يوتيوب», sub «الرابط بالبايو»}` |
| `studio.json` | `{"cardTop": 0.24}` (by hand, from a frame) |
| `sfx.json` | `{"outro": 3.0, "whoosh_up": [11.7], "whoosh_down": [16.6], "tap": [14.56]}` |
| `fixes.json` | 3 sentences, 18/21/5 words (same counts as whisper), `hot: ["بنتحرك","الكويت"]` |
| `compose.html` scenes | `R_FULL 0–11.7 · R_DOWN 11.7–16.6 (route panel الإمارات→الكويت, gb 470) · R_FULL 16.6–end`; captions only outside the R_DOWN scene |

**Result.** `C:/tmp/vae-e2e/ad-master.mp4`: 1080×1920 H.264 High, 30 fps, plus AAC 48 kHz stereo, 30.07 s, −14.0 LUFS (ebur128), peak −6.1 dBFS.

**Regression against upstream a69492d** (`C:/tmp/vae-e2e-up/`). Both runs used the same `src.mov`, `fixes.json`, `theme.json`, `compose.html`, `studio.json` and `sfx.json`. The upstream run followed upstream's SKILL.md (whisper through `python -m whisper … --model medium`), with three changes for this PC, applied to the upstream run only:
- `PYTHONUTF8=1` and `PY=python`: `python3` is the Microsoft Store stub, and upstream scripts crash on Arabic under cp1252.
- `npm ci` in the upstream skill folder instead of `00_setup.sh --install`, because the install's `npm i` rewrites upstream's package.json.
- No upstream file was edited.

The transcript was identical (44/44 words and times). The two docs extract frames at different JPEG quality: rebuild `reel.md` uses `-q:v 2`, upstream uses `-q:v 3`.

| t (s) | 1.2 | 5.0 | 12.5 | 14.8 | 20.0 | 28.5 | min |
|---|---|---|---|---|---|---|---|
| SSIM, each run as its docs say (q:v 2 vs 3) | 0.978 | 0.978 | 0.982 | 0.984 | 0.979 | 0.998 | **0.978**, 3/6 below 0.98 |
| SSIM, upstream vfr re-extracted at q:v 2 | 1.000 | 1.000 | 0.987 | 0.988 | 0.984 | 0.998 | **0.984** |

With matched frames, all 902 rendered frames (`out/*.jpg`) are byte-identical. What remains comes from libx264: encoding the same frames twice gives different streams (SSIM 0.993–1.000 at these points). The audio streams are identical. Side-by-side sheet: `C:/tmp/vae-e2e/ssim/side-by-side.jpg`. A visual check found it OK (Arabic shaping, caption position, safe zone).

**Blur.** The first target, a dark TV screen, was refused as too flat to track. Final target, the wall socket:

```bash
python scripts/blur_track.py box C:/tmp/vae-e2e cutz.mp4 4.2 0,60,125,100   # نوافذ 1 · فريمات 813 · غير مؤكد 13 · مفقود>1ث 0
python scripts/blur_track.py apply C:/tmp/vae-e2e cutz.mp4 cut_blur.mp4
python scripts/blur_track.py qa C:/tmp/vae-e2e cut_blur.mp4 qa.jpg          # 14 tiles; visual QA OK
```

The probed rate was 30/1, and the 813 frames match ffprobe's count.

**Defects the run found, now fixed (each with a test):**
- Setup's `npm i` rewrote package.json and the lockfile; it now runs `npm ci`.
- 24 scripts crashed on Arabic under cp1252; they now carry a UTF-8 shim.
- Hand-edited landscape crops were overwritten when 03 re-ran. They are now tracked against an `auto` crop and the source signature.
- Python called WSL's `bash.exe`; `_shell.find_bash` now picks Git Bash.
- `blur_track.py` resolved bare names against the current folder instead of `<work>`.
- Setup did not list the head-crop step as Mac-only.

**Fixed before publishing (each with a test):** whisper no longer runs twice on a fresh reel (`transcribe.py` reuses the step-0 `a.json` unless `--force` or a newer `a.wav`); a source with a silent soundtrack is offered the beat montage, not the voice montage; a reel with speech no longer prints the beat warning.

(The full run log lives in a local, git-excluded working note and is not part of the repo.)

## Verified

- Full test suite (`python -m pytest -q`): unit tests for token measurement, studio auth, fonts, transcription wrapper, series and lessons, approach choice, blur tracking, plus repo hygiene (removed paths, no dead script references, no `python3` calls, no upstream promo, attribution).
- `claude plugin validate .` passes.
- Routing smoke check: 5/5 modes routed to the right reference; carousel requests declined.
- Blur: tracking, fail-safe and frame-index handling tested on synthetic footage.
- Bundled fonts: same files Google serves for the weights used (Tajawal 800, IBM Plex Sans Arabic 600 checked).

## Pending

- **End-to-end checks:** the visual checks of the side-by-side sheet and of the blur QA sheet came back OK. The whole-branch code review is run separately.
- **Install from GitHub:** `claude plugin marketplace add 7mxd/video-ad-editor` then `claude plugin install video-ad-editor@7mxd-plugins`, replacing the local-clone install.
- **After that:** move the existing series cards and lessons onto this plugin.

## Known limitations

- **Studio `--lan`:** every path needs the token (a cookie after the first visit) and there is no directory listing, but the share link carries the full-power token: anyone you send it to can edit and render. Default (`127.0.0.1`) accepts POST only from `127.0.0.1`/`localhost`.
- **Beat detection has no confidence score:** a clip with ambient audio can be offered a beat montage it does not suit. Pick the voice or plain montage instead.
- **Blur:** tested on synthetic footage and one real clip (the end-to-end run). No automatic face or plate detection: you mark the target, and a flat, featureless target (a dark TV screen) is refused as "not enough detail".
- **Mac-only features stay Mac-only on Windows:** person cut-out (text behind the person, the three cut styles, collage, backdrop, "head out of the card" podcast scenes), hand tracking, gallery face tracking (`36`) and the HDR converter. Setup lists them at step 0. On Windows a landscape source is cropped from the centre and the head-crop step (23) keeps `faceAnchor`: fix the crop by hand in `shots.json` and `cardTop` in `studio.json`. Podcast face tracking on Windows uses OpenCV Haar: less accurate than Vision, and its mouth signal is a contrast proxy, not a lip measurement. It has not been checked on a real multi-cam session.
- Static pages (onboarding, studio share/mobile, the moves gallery) still load fonts from Google; rendering does not.
- On Linux without `/Applications` (or with `CLAUDE_SANDBOX` set), setup sends one `curl -I` to the Whisper model host to tell a sandbox with no internet from a normal machine.
