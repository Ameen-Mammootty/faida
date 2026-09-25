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
