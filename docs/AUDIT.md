# Audit: majedphotos/video-ad-editor v6.3.0

- Date: 2026-11-05
- Audited commit: upstream `main` as of 2026-11-05 (103 commits, MIT, © Majed Alzaabi)
- Machine: Windows 11, Python 3.12, Node 22.23, ffmpeg 9.0.2, Chrome installed
- Method: no Majed plugin was installed, enabled or run. The plugin's scripts were read, not executed.
  - Token numbers are measured, not estimated. Each text was sent to the model (`claude -p --tools ""`), and the input-token count was compared with an empty-payload baseline of 7,855 tokens.
  - Arabic text costs about 2.3 bytes per token here, so byte counts understate the cost.

## 1. Token cost

### 1.1 What you pay today (measured)

| Item | When it is paid | Tokens |
|---|---|---|
| `video-ad-editor` listing (name + description) | every session | 202 |
| `motion-video` listing | every session | 351 |
| `podcast-video` listing | every session | 241 |
| `montage-video` listing | every session | 221 |
| `thumbnail-video` listing | every session | 218 |
| **majed-video plugin, 5 skills** | **every session** | **1,233** |
| The other 4 plugins from the same marketplace: content-engine-v5 (7 skills) 1,257 · live-stage 325 · script 378 · davinci 229 | every session | 2,189 |
| **Whole `majed-plugins` install, all enabled** | **every session** | **3,422** |
| `video-ad-editor/SKILL.md` body (33.7 KB) | on invoke | 14,606 |
| `motion-video` / `podcast-video` / `montage-video` / `thumbnail-video` body | on invoke | 1,514 / 1,662 / 786 / 1,598 |
| `references/start.md` (step 0, `SKILL.md:77` says "read and run it") | every run | 4,134 |
| `references/any-environment.md` (`SKILL.md:66` "read") | every run | 2,167 |
| `motion-rules.md` + `scenes.md` + `moves.md` + `styles.md` (`SKILL.md:250-254`, "before any scene, read") | every reel with motion | 2,847 + 3,495 + 14,381 + 3,426 = 24,149 |
| **A standard talking-head reel, before the first scene is written** | **per run** | **45,056** |

### 1.2 Your concern (a): "5 plugins where one would do"

This is partly true.

- `majed-video` was already **one** plugin with 5 skills.
- The 5 plugins came from installing the **marketplace**. The other 4 (script, content engine, DaVinci, live stage) are separate products.
- When all 5 were enabled, they cost 3,422 tokens per session. `majed-video` alone cost 1,233.
- The bigger waste is not the listing. It is the **45k tokens per run**: a 14.6k-token SKILL.md plus six references the skill orders the agent to read up front. `moves.md` alone is 14.4k tokens and describes the private API of the custom engine.

### 1.3 Decision: 1 skill with progressive disclosure

The 4 small skills are already routers. Each one says "all `scripts/` and `references/` live in `../video-ad-editor`" (`montage-video/SKILL.md:7-8`, `motion-video/SKILL.md:9`, `podcast-video/SKILL.md:9`, `thumbnail-video/SKILL.md:9`), so merging them loses nothing.

- **The new skill:** one SKILL.md that holds a short mode router (reel, motion, podcast, montage, cover) plus the fixed rules.
- **Loaded on demand:** each mode's steps live in `references/<mode>.md`, and the agent loads only the one it needs.
- **`moves.md`** is split into a one-screen index plus per-family files.

| Metric | Upstream (measured) | Rebuild target | Measured after rebuild |
|---|---|---|---|
| Skills listed at session start | 5 (bundle: 15) | 1 | 1 |
| Session-start tokens | 1,233 (bundle: 3,422) | ≤ 300 | 278 (same tool on upstream: 1,273) |
| Tokens on invoke (SKILL.md body) | 14,606 | ≤ 3,000 | 2,990 (same tool on upstream: 14,616) |
| Tokens before the first scene of a talking-head reel | 45,056 | ≤ 15,000 | 14,944 mandatory path (same tool on upstream: 45,126) |

Measured 2026-11-05 with `python tools/measure_tokens.py --check` (exit 0) and re-measured after the end-to-end run with `python tools/measure_tokens.py --check --json docs/tokens-after.json` (exit 0; last re-measured 2026-11-06 after the pre-publish fixes: listing 278, body 2,990, reel path 14,944, typical reel 14,944 + 5,125 + 2,367 = 22,436; per-file counts in `docs/tokens-after.json`). That tool re-measured upstream 6.3.0 as its baseline, which is why its upstream numbers differ slightly from §1.1 (newer CLI).

**Read this honestly:** the 14,944 figure is the mandatory reading path only (`SKILL.md`, `start.md`, `series.md`, `reel.md`, `motion-rules.md`, `scenes.md`, `moves/INDEX.md`, `styles.md`). A typical real reel with motion also opens `references/moves/depth.md` (5,125) and `references/moves/code.md` (2,367), so a realistic reel reads about **22.4k tokens before the first scene, against about 45k upstream** — roughly half, not a third.

## 2. Video engine

### 2.1 Which one is "the complicated editor"?

The repo has **three** render paths:

| Engine | Where | Used by default? | Setup cost | Notes |
|---|---|---|---|---|
| **Custom canvas engine**: a `compose.html` the agent writes, rendered frame by frame by Puppeteer | `scripts/04_render_frames.js`, `scripts/compose.REFERENCE.html` (1,133 lines), `scripts/moves-compose.js`, `motion/engine.js` (904 lines) | **Yes, every reel** | `puppeteer-core` plus system Chrome. Small to install. | Every source frame is first dumped to JPEG (`SKILL.md:228`). Each output frame is drawn, turned into a base64 JPEG and written to disk (`04_render_frames.js` `grab()`), then re-encoded (`06_encode.sh`). That makes 3 lossy generations and about 1,800 JPEGs per minute. The agent must learn a private API (`window.init/draw/shot/setFrame`, `MV.*`, `FX.*`). That is where the 24k tokens of references go. |
| **Remotion**, "the second engine" | `scripts/04b_remotion.sh`, `scripts/remotion-template.bundle.json` (20 KB), `references/remotion.md` | No, opt-in | `04b_remotion.sh:3` says it downloads about 500 MB on first run. Scenes are React/TSX. | The licence is not free for companies of 4 or more people (`references/remotion.md:14`). It is a second engine with a second scene language. |
| **DaVinci Resolve** | separate plugin `majed-davinci` | No | Needs Resolve installed. External scripting needs Resolve Studio. | Already removed from this machine in step 2. Only README mentions remain (`README.md:184,227,295,373,404`). |

**Verdict (confirmed by you on 2026-11-05): the editor is DaVinci Resolve.**

- DaVinci is the "edit it yourself on a timeline" route ("سوّه بدافنشي", `video-ad-editor/SKILL.md:40-44`).
- It is not built in. It lives in a separate plugin (`majed-davinci`) that drives Resolve over its Python scripting API.
- What it costs to set up and run:
  - **A paid Resolve Studio licence.** The free edition lost Python scripting in 21.1 (`majed-davinci/davinci-video/SKILL.md:16`).
  - A second plugin to install (+229 tokens per session, measured).
  - Resolve must be open while it builds.
  - The skill itself warns that long builds in one call hang Resolve (`davinci-video/SKILL.md:30`).
- Already removed in step 2. What remains in this repo:
  - the pointer at `SKILL.md:40-44`
  - DaVinci wording in `22_hook.py:13,14,221,273` and `references/podcast-hook.md:24`
  - README mentions at `README.md:184,227,295,373,404`
- The other two engines were reviewed as well:
  - **Remotion** is an unused, opt-in second engine (500 MB, licence condition), so it is removal-worthy on its own.
  - The **custom Puppeteer engine** is the default and works. Its token cost is handled by finding 1, not by an engine swap.

### 2.2 HyperFrames (researched from the official repo and tested here)

Facts from https://github.com/heygen-com/hyperframes and https://hyperframes.heygen.com:

- Apache-2.0 licence. v0.9.15 was released 2026-11-05. It is fast-moving 0.x: three releases in two days.
- You author plain HTML with `data-start`, `data-duration` and `data-track-index`, plus a paused GSAP timeline.
- `npx hyperframes render` seeks each frame in headless Chrome and encodes with FFmpeg. It renders `<video>` directly, so there is no JPEG pre-extraction.
- The CLI has `lint`, `check`, `snapshot`, `transcribe` and `doctor`.
- Windows is documented as supported (FAQ). Open Windows issues: #4058, #4060, #4845, #6481.
- Arabic issue #5885 is open. Per-letter splits break letter joining, and per-word stagger without `dir` reverses word order. No bundled font covers Arabic.
- Anonymous telemetry is on by default. Turn it off with `hyperframes telemetry disable`.
- Its own Claude plugin ships 9 skills. We would **not** install those, to keep context small.

**Spike on this machine** (`C:\tmp\hf-spike`):

- Input: a 1080×1920 4-second clip, with whole-word Arabic `<span>`s in a `dir="rtl"` line and a GSAP highlight per word.
- `hyperframes lint` gave 0 errors.
- `render` produced an H.264 + AAC MP4 at 1080×1920, 30 fps, 4.0 s, 6.0 MB, in 12.3 s (30.7 s wall time including the npx start).
- A frame grab at 2.6 s shows correct right-to-left word order, joined letters, and the 5th word highlighted on time. The #5885 bugs are avoided by using whole-word spans plus `dir="rtl"`.
- Disk cost: 107 MB npx package plus 270 MB of `~/.cache/hyperframes` (chrome-headless-shell), about 377 MB in total.

### 2.3 Comparison: the "edit it by hand" route

| | (1) Keep DaVinci (separate add-on) | (2) User choice: DaVinci or HyperFrames | (3) Replace DaVinci with HyperFrames |
|---|---|---|---|
| Licence and cost | paid Resolve Studio | Studio only if you pick it | free (Apache-2.0) |
| Install | Resolve (multi-GB) + second plugin | both possible | `npx hyperframes@0.9.15`, about 377 MB, no GUI install |
| Windows | Resolve runs on Windows; Python scripting setup is manual | — | tested here: 4 s portrait Arabic clip rendered in 12.3 s |
| How you edit | Resolve timeline | — | `npx hyperframes preview` (browser studio) or ask Claude to change the HTML; each caption, hook and card is its own clip |
| Context cost | +229 tokens per session for the add-on | small pointer in our skill | one reference file, loaded only when asked |
| Arabic | Resolve text | — | whole-word spans + `dir="rtl"` (tested); #5885 still open for per-letter effects |
| Risk | Resolve API changes; hangs on long builds | two routes to document | HyperFrames is 0.x, so pin the version |
| Effort | 0 h (pointer stays) | ≈ 7 h | ≈ 6 h |

There is also a GUI route already in the repo: the CapCut project export (`references/capcut.md`, `scripts/40_capcut.py`). Its media sandboxing is mac-specific (`40_capcut.py:15,47,58`), so Windows support is unverified.

### 2.4 Recommendation: (3), replace DaVinci with HyperFrames

- **Remove every DaVinci pointer:** `SKILL.md:40-44`, the README, and the `22_hook.py` and `podcast-hook.md` wording (make it engine-neutral).
- **Add one "editable project" export.** A small script, `hf_export.py`, writes the finished reel as a HyperFrames project:
  - the cut video
  - each caption line, the hook and the cards as separate clips, with the bundled Arabic font
  - `dir="rtl"` and whole-word spans
- You edit the export in `hyperframes preview` or by chatting. `hyperframes render` produces the MP4.
- Pin `hyperframes@0.9.15`, run `telemetry disable` before the first render, and do not install HyperFrames' own 9 skills.
- **Keep the built-in engine as the default renderer.** It is Arabic-tuned and already free on Windows. Its token cost is cut by finding 1.
- **Delete Remotion** (finding 15).

Why not (1)? It needs a paid licence, a second plugin and a running Resolve. Why not (2)? Two hand-edit routes double the docs, and you don't have Studio set up.
If you later want a full switch to HyperFrames as the renderer, that is ≈ 30 h for move-bank parity. I'd leave it out of this rebuild.

## 3. Findings (ranked)

| # | Severity | Finding | Evidence | Fix | Effort (h) |
|---|---|---|---|---|---|
| 1 | High | About 45k tokens are read before the first scene of every reel | §1.1 measurements; `SKILL.md:66,77,250-254` | One router skill. Mode steps go in `references/<mode>.md`. Split `moves.md` into an index plus families. Drop "read X first" for anything optional. | 6 |
| 2 | High | `python3` is written 114 times in the docs (23 in `SKILL.md`). On this machine `python3` resolves to the Microsoft Store stub `…\WindowsApps\python3.exe`, not Python 3.12. | `grep -c 'python3 '`; `Get-Command python3`; `SKILL.md:69-71` tells the agent to translate by hand; `13_collage.js:49`, `23_beatfx_render.js:69` call `python3` from code | Docs use `python`. A `scripts/py` launcher (and `_compat.sh` `$PY`) picks `python3` or `python`. Fix the 2 JS call sites. | 2 |
| 3 | High | The hand-edit route depends on DaVinci Resolve Studio (paid) through a separate plugin | §2.1; `SKILL.md:40-44`; `davinci-video/SKILL.md:16,30` | §2.4: replace with a HyperFrames project export | 6 |
| 4 | Med | Self-update downloads `releases/latest` and runs `rsync --delete` over the skill folder with no checksum. It also queries GitHub on every setup run. | `00_setup.sh:38-40,45` | Remove it; the plugin manager handles updates | 0.5 |
| 5 | Med | `deep-filter` binary is downloaded with no checksum | `00_setup.sh` :83; only a size check plus `--help` | Pin SHA-256 per OS | 1 |
| 6 | Med | The studio server listens on all interfaces with no auth. Anyone on the Wi-Fi can call `/api/render`, `/api/recut` and `/api/comment`. | `studio/studio.py:273` | Default `127.0.0.1`; `--lan` opt-in with a random token in the URL | 1 |
| 7 | Med | Packaging leftovers: `video-ad-editor.skill` (3.8 MB) is stale. It holds VERSION 4.4.2 against 6.3.0 and still ships `scripts/davinci/*`. `_pkg/` is about 30 MB of README GIFs and the repo is 59 MB. | `python -m zipfile -l video-ad-editor.skill`; `du` | Delete both. Keep 2–3 compressed README images in `docs/img`. | 0.5 |
| 8 | Med | Mac-only features are advertised to Windows users: 11 `swiftc` call sites, `mlx_whisper`, behind-the-person text, podcast face tracking and the HDR converter | `11_behind_text.js:47-54`, `15_podcast.py:80,402`, `18_long_transcribe.py:15`, `windows.md:13-15` | A capability table at step 0 that says "not on Windows" up front. Route podcast face tracking to the OpenCV fallback where one exists. | 2 |
| 9 | Med | 4 skills overlap in triggers with each other ("Not for … use video-ad-editor") and cost 1,233 tokens of listing | §1.1; each description ends with a cross-reference | Merged by fix 1 | (in 1) |
| 15 | Med | Remotion is an unused second engine: about 500 MB on first setup, TSX scenes, a licence condition for companies | `04b_remotion.sh:3`, `references/remotion.md:14`, `scripts/remotion-template.bundle.json` | Delete | 0.5 |
| 10 | Low | Chrome lookup is mac-only in one script and partial in two | `13_collage.js:10`; `28_cover.py:33`; `33_thumb.py:19` | Reuse `_chrome_flags.js`/`04_render_frames.js:25-39` lookup | 0.5 |
| 11 | Low | Render needs the network: Google Fonts is fetched at render time | `22_hook.py:233`, `28_cover.py:171`, `30_demo.js:77` | Use bundled `motion/fonts` | 1 |
| 12 | Low | The docs reference files that don't exist | `phone-cloud-playbook.md:29` (`30_probe.sh`), `podcast-upgrades.md:45` (`23_rank_clips.py`), `README.md:404` (`davinci-video/SKILL.md`); the Windows note is duplicated at `SKILL.md:69` and `:71` | Remove or fix | 0.5 |
| 13 | Low | Upstream-specific strings | `keyword-automation.md:26` (partner discount code "MAJED"); `SKILL.md:41-43` (`majed-*` install hints); `00_setup.sh:30-45` (Majed's release URLs) | Retarget to the new repo; drop the promo code | 0.5 |
| 14 | Low | Whisper `medium` runs on CPU here (`--fp16 False`, `SKILL.md:162`). That is slow on Windows. | `SKILL.md:160-166` | Optional: use `faster-whisper` when installed, falling back to `whisper` | 2 |
| 16 | Low | The default engine dumps every frame to JPEG and re-encodes, giving 3 lossy generations | `SKILL.md:228`; `04_render_frames.js` `grab()` | Optional: raise `-q:v` to 2, or try PNG. Measure size and speed first. | 2 |

Not issues (checked):

- No `eval` or embedded secrets.
- `rmtree` only removes self-made work subfolders.
- Every script is referenced from some doc.
- The versions agree (6.3.0) except in the stale `.skill`.
- `windows.md` is honest about what is mac-only.
