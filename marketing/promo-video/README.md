# Faida promo video

A 48-second, 1080p60 film for prospective clients: `out/faida-promo.mp4`
(poster frame: `out/faida-promo-poster.png`).

| Time | Scene | What it says |
| --- | --- | --- |
| 0-4 s | The hook | AED 6,420 sold. How much did you keep? |
| 4-10 s | The problem | Invoices pile up. Prices move. Quietly. |
| 10-14 s | The brand | The Margin Fold mark, "Profit, in plain sight." |
| 14-22 s | 01 Forward the invoice | A photo in, the product's own reply out ("Read it", the lines, "Milk powder is up AED 4.00", "Reply OK") |
| 22-29 s | 02 Costed to the plate | Invoice line → raw material → Karak chai at AED 0.49 a cup, keeping 67% |
| 29-37 s | 03 Know what to push | The dashboard: the two-bullet answer, the three tiles, the branch league, worth a look |
| 37-41 s | The morning brief | 07:00 on the owner's phone |
| 41-48 s | Close | Every item. Every branch. Real margins. Private pilot. |

Every figure is illustrative and the close says so. The words follow the display rules:
"kept after ingredients" and "materials share of costed sales", never food cost % or profit.

## How it is made

- `index.html` is the whole film as one pure function, `window.renderFrame(t)`, in the brand's
  colours and its bundled Manrope and Inter (read from `apps/api/src/faida_api/fonts`).
  Open it in a browser with `?play` to watch it in real time, or `?t=12.5` to freeze a frame.
- `render.mjs` steps that function frame by frame in headless Chromium with Playwright and pipes
  each screenshot into ffmpeg (H.264, loudness normalised to -14 LUFS for web and WhatsApp).
- `music.mjs` synthesises the soundtrack from scratch (120 bpm, every cut on a downbeat), so the
  film carries no licensed audio. It is mixed for phone and laptop speakers, which play nothing
  under about 150 Hz: the kick carries a knock and a click, the bass sits an octave up, and a bell
  melody carries the hook. Check a change with
  `ffmpeg -i out/faida-promo.mp4 -vn -af "highpass=f=300,highpass=f=300,ebur128" -f null -`,
  which should read about -18 LUFS; the first cut read -25 and sounded silent on a phone.
- To swap only the soundtrack, keep the picture and re-mux:
  `ffmpeg -i out/faida-promo.mp4 -i out/music.wav -map 0:v -map 1:a -c:v copy -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:a aac -b:a 192k -shortest out/remux.mp4`.

```bash
cd marketing/promo-video
npm install                                   # Playwright; needs ffmpeg on PATH
npm run render                                # music + full render, about 5 minutes
node render.mjs --stills 2.5,20,34            # single frames to out/frames/ for review
npm run preview                               # 15 fps draft
```

To change a line, edit it in `index.html`; timings live in each scene's function (`s1` to `s8`)
and the scene table at the top of the script. If a cut moves, move it in `music.mjs`'s `CUTS` too.

## The narrated cut (Manim + Kokoro)

`out/faida-promo-narrated.mp4`: 66 seconds, 1080p60, a voiceover over the same story, with the
pictures drawn in Manim and the voice read by Kokoro-82M. Everything lives in `manim/`:

- `narration.py` holds the script, one list of sentences per scene. Kokoro reads it a sentence at a
  time with the `af_heart` voice, so the film knows when each sentence starts. Each scene is
  rounded up to whole bars of the music so every cut lands on a downbeat. Names the phonemiser gets
  wrong are corrected in `PHONEME_FIXES`; Faida is said "FAH-ee-dah", not "FAY-da". It writes
  `build/voice.wav`, `build/timings.json` and `build/score.json`.
- `film.py` is the Manim film. Each scene starts its beats when the sentence it illustrates starts
  (`self.until(self.said(i))`), and every animation is rounded to whole frames, so the picture
  cannot drift from the voice.
- `../music.mjs build/score.json` scores the same timeline: a hit on the logo and on the close, a
  breakdown under the morning brief, and no melody over the voice.
- `build.sh` runs all of the above and mixes the result with ffmpeg: the voice leads, and the music
  sits under it and ducks further whenever the voice speaks.

```bash
cd marketing/promo-video/manim
apt-get install ffmpeg libcairo2-dev libpango1.0-dev pkg-config   # once
pip install -r requirements.txt
# Manim reads the brand fonts from the system: install apps/api/src/faida_api/fonts/*.ttf
mkdir -p models && curl -sSL -o models/kokoro-v1.0.onnx \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -sSL -o models/voices-v1.0.bin \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
./build.sh -ql     # draft, about a minute
./build.sh         # 1080p60
```

To change a line, edit `SCRIPT` in `narration.py`; scene lengths and cuts follow on their own. To
try another voice, set `VOICE` (`am_michael`, `bf_emma` and `bm_george` are the other good
English ones). The model files are the ONNX export of Kokoro-82M v1.0 (Apache 2.0) from the
kokoro-onnx releases, not Hugging Face, which this build environment cannot reach.

## The cartoon cut (the problem, told with characters)

`out/faida-cartoon.mp4`: about a minute, 1080p at 30 fps. A supervisor types invoices in by hand
at midnight, mistypes 47.00 as 4700 and rubs his head ("Okay... I made a mistake. Again."); the
owner stares at a menu whose red and green tags will not settle, while costs climb and profit
slides. Then Faida arrives: the invoices fly into WhatsApp, the supervisor sips his tea, and the
menu settles into PUSH and FIX. Everything lives in `cartoon/`:

- `soundtrack.py` holds the script (narrator, owner, supervisor, each a Kokoro voice) and writes
  the timeline every beat keys to (`build/timings.js`), each character's mouth movement taken
  from the loudness of their own voice, the sound effects (typing, the clock, the error buzzer,
  whooshes, pops), all synthesised, and the music's timeline (`build/score.json`).
- `index.html` draws the characters in SVG and animates them as a pure function of time. The owner
  is a Gulf restaurateur (white kandura with its tassel, ghutra and agal, a kept beard, a gold
  watch); the supervisor is at his desk in shirt and tie. Each arm is one smooth curve from shoulder
  to wrist, bent toward the elbow a two-bone solve gives, so no pose shows a joint, and ends in a
  cartoon hand shaped for the moment (fist, open palm, pointing, thumbs-up, holding a cup or a
  phone). Eyelids, brows, sweat and stress marks carry the rest. Spoken lines show as speech bubbles and
  the narrator as a caption, so the film works with the sound off.
- `../music.mjs` scores it: only the pad under the problem (`calmUntil`), the drop when Faida
  appears.
- `build.sh` runs it all: voices and effects, music, the mix (voices lead, music ducks), then
  `../render.mjs --page cartoon/index.html` for the frames.

Red and green carry meaning on the menu here because that is the joke, but never alone: the tags
read "?" while nobody knows, then "PUSH · 67%" or "FIX · 38%".
