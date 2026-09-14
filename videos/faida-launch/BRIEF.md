---
workflow: product-launch-video
flow: automation
storyboard: yes
message: "Forward the invoice you already have. Know what every item earns."
destination: linkedin-feed
aspect: 1080x1080
language: en
audience: GCC cafeteria owners and multi-branch chain operators; investors and partners seeing the launch
length: 30s
angle: the-invoice-journey
narration: yes
---

## Intent

A 30-second launch video for Faida, the profit-visibility product for GCC cafeterias and
multi-branch karak and paratha chains, fed through WhatsApp.
The founder asked for a video "mainly focussing on the key benefits of Faida, how its solving the
problem and enabling profitable growth for companies."

The telling the founder chose is **the invoice's journey**: one supplier invoice photo, forwarded
on WhatsApp the way the team already does, is read, checked, mapped to a raw material, tagged into
a recipe, and lands as a fils-precise plate margin. Then the whole menu carries a margin per item,
and the owner knows what to push and what not to push, branch by branch.

The problem, said without a word in the first seconds: supplier invoices pile up as photos in
WhatsApp and nobody knows what any item actually earns. The benefit: the owner sees the margin on
every item they sell, with every number traceable to the invoice it came from, and grows the
profitable items instead of guessing.

Sell, not tour: the captured product screens are evidence inside the story, never a site
walkthrough.

Tone: confident, plain, grounded. No hype words. The product's own voice from the landing page:
"No new workflow. No unexplained numbers. No pretending an estimate is verified profit."

## Assets

- ../../apps/web/public/brand/faida-mark.svg - the brand mark, for the opening WhatsApp bubble and the closing sting.
- ../../apps/web/public/brand/faida-primary-horizontal.svg - the horizontal wordmark, for the closing frame.
- https://faida-web-nine.vercel.app - the live landing page, to capture for brand tokens, copy and the hero proof card (invoice -> price alert).

## Customizations

- Voiceover: a short generated narration carries the benefits; music bed under it, ducked to the voice.
- Count-up treatment on the plate cost and the margin figure - the concept lands on a number appearing.
- Website capture of the live landing page for brand tokens and screens; the repo's own SVG marks are the logo source.
- Square frame: crop captured product screens to the panel each beat needs (the checked invoice card, the plate cost, the margin line); lean on phone-shaped WhatsApp screens, which fit 1:1. Never shrink a full laptop dashboard into the square.

- Voice: Marcia (HeyGen starfish 05f19352e8f74b0392a8f411eba40de1), the pipeline default; not user-picked, so not recorded as a preference. Swap with `--voice` and re-run audio.mjs + sync-durations + the frame packets if changed.
- Music: the retrieved HeyGen track is cut from 10.0 s (its first 10 s were a ~5 dB quieter build) to 33 s with a 0.8 s fade-in and 2.6 s fade-out (`assets/bgm/track-cut.mp3`, volume 0.12); SFX pruned to ten short cues, at most two per frame.
- Captions: the preset skin with the active word as ink on the Karak Gold chip (cream on gold failed 3:1) and upcoming words at 72% ink.

## Notes

- Brand palette (from apps/web/src/app/globals.css): Warm Cream #fbf6ec ground, Service Ink #172421 text, Date Palm #153e35 primary, Karak Gold #e3a13b accent only, Confirmed Green #1d6d50, Attention Amber #80520a. Display font Manrope, body Inter.
- Product display rules that the video must respect: whole-dirham headline figures, fils-precise per-plate costs and margins; purchases divided by net sales is never called "food cost %"; contribution is never called net profit; nothing is called "verified profit".
- WhatsApp is the input channel: invoice photos are forwarded to one number; the reply is a quoted reply to the photo. The daily brief arrives on WhatsApp at 07:00.
- Currency is AED. Example figures may come from the demo seed (a karak and paratha chain with three branches, e.g. Deira).
- Avoid: generic floating-dashboard SaaS promo, feature bullets flying in, stock upbeat music.
