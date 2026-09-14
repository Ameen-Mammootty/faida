---
format: 1080x1080
duration: 30s
message: "Forward the invoice you already have. Know what every item earns."
arc: BAB — before (invoices pile up, margins unknown) → bridge (forward one) → step 1 (checked) → step 2 (line → material → recipe) → wow (every item's margin, push and fix) → proof (the morning brief) → CTA
audience: GCC cafeteria owners and multi-branch chain operators; investors and partners seeing the launch
mode: collaborative
music: calm confident underscore, warm acoustic pulse, no drums until the reveal, minimal
---

## Video direction

- **Palette system** (from `frame.md`): canvas is the warm cream `bg`; every headline and figure is `text` ink; Date Palm `primary` carries the chat chrome, the filled bars, the hero "keeps" figure and the closing lockup; `gold` (#E3A13B) appears only as a chip, a quote strip or a marker sweep, never as text on cream and never as a fill larger than a chip; `gold-soft` is the attention surface (the "Fix" chip, the "14 photos" chip); `positive` (#1D6D50) is the only colour for "sums agree", "mapped ✓" and "Push"; `negative` (plum #65415F) only for the one margin below zero. Cards are white with the 20% primary border and no shadow, corners 14 px. Type by role: display ramp is Manrope, body ramp is Inter, figures in `tabular-nums`.
- **Motion grammar + reveal model**: long-tail settles (`power3` default, `expo.out` on a fast arrival), never bouncy. Every frame reveals on the voiceover's cues: at t=0 only what the line is saying then; each further piece lands as the line names it, most of it in the back half. During a hold, stillness; at most a subtle low-amplitude jitter on the held hero. No breathing, no back-half pan or push.
- **Rhythm / held frames**: 04 (the kept figure lands and then reads still for the last ~1 s) and 07 (the lockup holds to the end) are the held reads; 01 and 05 are the busy frames; 02, 03 and 06 are surface-operated with one camera move each at most.
- **Fonts on disk**: `assets/fonts/manrope-variable.woff2` (Manrope, weight axis 200–800) and `assets/fonts/inter-variable.woff2` (Inter, weight axis 100–900). Every frame declares both with `@font-face` pointing at these project-root-relative paths; no other family is named.
- **Square discipline**: 1080×1080; all content inside the top 83% (y ≤ 896 px). Product screens are never shown whole: a captured screen is a layout reference or a cropped panel, and the chat and phone surfaces are built at the frame's own scale so their type is legible in a feed.
- **Negative list**: no full dashboard in the square, no laptop mockups, no purple/blue "AI" gradients, no stock bokeh, no bouncy or elastic entrances, no slideshow (front-load then freeze) and no screensaver (elements floating independently), no `repeat`/`yoyo`, no randomness. Wording that never appears on screen: "food cost %", "net profit", "verified profit", "variance", "waste", "shrinkage". Narration text is never printed as on-screen copy; captions do that.

## Frame 1 — The pile

- scene: Supplier invoice photos land one after another in a WhatsApp chat until they cover the screen; no numbers, no answers
- voiceover: "Supplier invoices already land in WhatsApp. Your margins never do."
- duration: 4.963s
- transition_in: cut
- status: animated
- src: compositions/frames/01-the-pile.html
- type: hook
- persuasion: Pain validation
- beat: overwhelm → curiosity
- blueprint: overwhelm-surround
- asset_candidates: assets/invoice-kas-1.png — a demo supplier paper, portrait; assets/invoice-kas-2.png — a second demo supplier paper, portrait; assets/invoice-gulf-foods-demo1.png — the hero paper (Gulf Foods Trading, AED 745.76)

narrativeRole: Say the problem without a word of product: the paper already flows through WhatsApp, and none of it ever tells the owner what an item earns.
keyMessage: The data is already in your hands. The answer is not.

- blueprint: overwhelm-surround (Adapt)
- focal: assets/invoice-gulf-foods-demo1.png
- roles: invoice-gulf-foods-demo1.png = cutout (the centre bubble, most legible) · invoice-kas-1.png = supporting (two bubbles) · invoice-kas-2.png = supporting (two bubbles)
- sfx: message-pop-soft ×5 (one per bubble, quiet), keyboard-tick-soft

Adapt: keep the signature - accumulation until the frame is crowded, camera static, the crowd IS the pain - drop the avatar morph and the radial close-in; the resolution is the clutter-accumulation register's typed question, in the chat's own input bar.
Scene 1 (0.0–0.7s): the WhatsApp-style chat chrome (Date Palm header "Suppliers · Al Qusais", cream field, the empty input bar at the bottom) is present at t=0 — full-width strip, top band; the first photo bubble (invoice-kas-1, portrait, slightly rotated) arrives as a **chat-message entry** growing from the sender's corner (`compositions/components/chat-message.html` — its measured entry; smooth settle, → `spring-pop-entrance` smooth register). Layout: the chat surface fills the square; bubbles asymmetric, left-heavy.
Scene 2 (0.7–3.0s) — "Supplier invoices already land in WhatsApp": four more photo bubbles arrive one every ~0.35 s (kas-2, the hero paper at centre full size, kas-1 again, kas-2 again), each a chat-message entry with its own slight rotation, overlapping the last so the pile builds toward the centre; as the fourth lands the gold-soft chip "14 photos this week" pops at the right (→ `spring-pop-entrance`). Density: the pile covers ≥ 60% of the field; 3 depth layers (chrome · bubbles · chip).
Scene 3 (3.0–5.0s) — "Your margins never do.": the pile holds crowded and still; in the input bar the question "so what does a karak earn?" **types on with a caret** (→ `discrete-text-sequence` + `context-sensitive-cursor`, caret in ink), finishing as the line ends; the caret blinks to the end of the frame. No camera move anywhere in this frame.


## Frame 2 — Forward one

- scene: One invoice photo is forwarded to the Faida number; the quoted reply comes back under it - Checked, Gulf Foods Trading, two lines, AED 745.76, the sums agree
- voiceover: "Forward one to Faida. It reads every line and checks the sums."
- duration: 4.702s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/02-forward-one.html
- type: product_intro
- persuasion: Friction reduction
- beat: relief
- blueprint: device-surface-showcase
- asset_candidates: assets/invoice-gulf-foods-demo1.png — the hero paper the reply quotes; assets/faida-mark.svg — the brand mark on the reply bubble; assets/screen-invoice-review.png — the review screen's checked-fields column, supporting only if it fits the square

narrativeRole: The bridge. The product is introduced by doing its core loop once, inside the surface the team already uses: a photo goes to one number, a quoted reply comes back.
keyMessage: No new workflow. One forward, one checked reply.

- blueprint: device-surface-showcase (Adapt)
- focal: assets/invoice-gulf-foods-demo1.png
- roles: invoice-gulf-foods-demo1.png = cutout (inside the outgoing bubble, cropped to the header and the table) · faida-mark.svg = supporting (the header avatar and the reply's sender mark) · screen-invoice-review.png = supporting, leave out — the square is full; it is a reference for what "checked" looks like, not a placed asset
- sfx: send-whoosh-soft, typing-dots-soft, receive-pop, tick-soft

Adapt: static-tour register — the chat surface IS the device and fills the square (no bezel, the sketch's layout); keep the signature - the surface is operated on its own face and its state advances (send → typing → reply → checked) - and drop the side headline and the camera entirely.
Scene 1 (0.0–0.9s) — "Forward one to Faida.": the Faida chat chrome (mark + "Faida · business account") is present at t=0; the outgoing bubble with the forwarded paper slides up from the bottom-right corner and settles as a **chat-message entry** (→ `spring-pop-entrance` smooth), "↪ Forwarded" label above the photo, the double-tick fading in at its foot. Layout: asymmetric 40/60, the outgoing bubble upper right.
Scene 2 (0.9–1.9s) — "It reads every line": a typing indicator (three dots stepping their opacity on a shared finite phase, a few stepped `set` calls on the one timeline) appears lower left for ~0.6 s, then is replaced by the reply bubble popping in with only its quote strip ("↩ IMG_2048.jpg · quoted reply", gold left rule) and "✓ Checked" (→ `spring-pop-entrance`).
Scene 3 (1.9–3.6s) — "and checks the sums.": inside the reply, the supplier name, then the invoice meta, then each of the two lines reveal one per beat (→ `dynamic-content-sequencing`, line by line, short slide-up + fade); as each line lands a thin **gold marker sweep** underlines it left→right (→ `css-marker-patterns` highlight, low opacity) — the "checked" feel.
Scene 4 (3.6–4.7s): the total "AED 745.76" lands by a **count-up** climbing 0.00 → 745.76 in ~0.6 s (the installed `compositions/components/count-up.html` primitive's eased count and restrained landing pulse, `tabular-nums`, two decimals, prefix "AED "), then the "sums agree" chip pops in Confirmed Green beside it; hold still to the end.


## Frame 3 — Line to plate

- scene: One invoice line - "Milk Powder 2.5kg NIDO · 12 sack · 54.50" - travels three stations: the printed line, the raw material it is filed under (Milk Powder, per kg), then its place in the Karak Tea (Flask 1 L) recipe beside tea dust, sugar and evaporated milk
- voiceover: "Every line becomes a raw material. Every material, part of a recipe."
- duration: 5.224s
- transition_in: crossfade
- status: animated
- src: compositions/frames/03-line-to-plate.html
- type: feature_showcase
- persuasion: Show-don't-tell proof
- beat: clarity
- blueprint: spatial-pan-stations
- asset_candidates: assets/invoice-gulf-foods-demo1.png — the source line is cropped from this paper

narrativeRole: The mechanism, in the product's own chain: extracted line → inventory raw material → recipe ingredient. This is the four-layer demo bar said in one pan.
keyMessage: The invoice is not filed. It is wired into the menu.

- blueprint: spatial-pan-stations (Adapt)
- focal: assets/invoice-gulf-foods-demo1.png
- roles: invoice-gulf-foods-demo1.png = cutout (the table's first row, cropped tight, inside station 1)
- sfx: pan-whoosh-soft ×2, tick-soft (on "mapped ✓"), pill-pops-soft

Adapt: the three stations are stacked vertically (the sketch's confirmed layout) and the camera travels DOWN, not across; keep the signature - one virtual camera traversing pre-placed stations, each stop revealing its callout, landing held - and let the landed state be the whole chain in view. The world is the sketch's 1080-wide canvas; the camera opens pushed in on station 1 and pulls back as it lands.
Scene 1 (0.0–1.4s) — "Every line": camera framed on station 1 at ~1.25× (→ `viewport-change` pan/zoom on one `.world` wrapper, sequenced by `multi-phase-camera`); the cropped invoice row (cutout) sits left, the typed line "1 · Milk Powder 2.5kg NIDO / 12 sack · 54.50 · 654.00" beside it; a **gold marker sweep** runs across the row as the word "line" is said (→ `css-marker-patterns`); the Date Palm connector below the card begins to **self-draw** downward (→ `svg-path-draw`).
Scene 2 (1.4–2.8s) — "becomes a raw material.": the camera **pans down** to station 2, easing in-out, scale easing toward 1.1×; the "Milk Powder" card's title fades up as the pan lands, "filed under · per kg" beside it, and the "mapped ✓" chip pops in Confirmed Green (→ `spring-pop-entrance`, smooth); the connector keeps drawing to station 3.
Scene 3 (2.8–4.5s) — "Every material, part of a recipe.": the camera pans down again and **pulls back to 1.0×**, landing the whole chain in the square exactly as sketched; the recipe card's title "Karak Tea (Flask 1 L)" fades up, then the ingredient pills **assemble in a staggered cascade** (→ `spring-pop-entrance` staggered, ≤ 0.5 s total) — "Milk powder" first and filled Date Palm, the other four outlined — and the small note "one plate = 1 L · yield and usable share applied" fades in last.
Scene 4 (4.5–5.2s): hold on the landed chain, camera static; at most a subtle jitter on the filled pill.


## Frame 4 — What it keeps

- scene: Karak Tea (Flask 1 L): sells at AED 35.00, costs AED 6.20 a portion, keeps AED 27.13 - 81.4%. The cost and the kept share count up as the line names them (the dashboard set of figures, used everywhere in the video)
- voiceover: "So every item shows what it costs, and what it keeps."
- duration: 4.206s
- transition_in: crossfade
- status: animated
- src: compositions/frames/04-what-it-keeps.html
- type: benefit_highlight
- persuasion: Feature-to-benefit translation
- beat: confidence
- blueprint: dataviz-countup
- asset_candidates: assets/screen-menu.png — the Menu screen's table row shape (sells at / costs / margin), for layout only

narrativeRole: The value claim lands as one number appearing: a fils-precise plate cost and the share the item keeps. Typography only; the number is the picture.
keyMessage: A margin per item, not a guess.

- blueprint: dataviz-countup (Adapt)
- focal: none — typography and one bar are the picture
- roles: screen-menu.png = background, not placed — a layout reference for the sells-at / costs / margin row only; nothing is cropped from it
- sfx: riser-soft (into the count), tick-low (as the figure lands)

Adapt: one instrument, no push-through and no camera; keep the signature - the hero number counts up while its paired graphic fills on the SAME ease, so number and bar land as one beat.
Scene 1 (0.0–0.7s) — "So every item": the small label "One item" and the title "Karak Tea (Flask 1 L)" reveal **per-word staggered** (→ `dynamic-content-sequencing`), upper third; the two upper cards' frames fade in empty beneath. Layout: the sketch's stack — title, two cards, the big keeps card; centred, hero card ≥ 40% of the frame.
Scene 2 (0.7–1.9s) — "shows what it costs,": "Sells at" fills first, its figure "AED 35.00" snapping in with the small "AED 33.33 net of VAT" line; then "Costs" and its figure **count up** 0.00 → 6.20 in ~0.5 s (→ `counting-dynamic-scale`, two decimals, `tabular-nums`) with "a portion, at today's prices" fading beneath.
Scene 3 (1.9–3.4s) — "and what it keeps.": the keeps card's border tints to Date Palm; "AED 27.13" **counts up** from 0.00 with its scale growing to the final size (→ `counting-dynamic-scale`) while the progress bar **fills to 81.4%** on the same ease (→ `stat-bars-and-fills`, `scaleX` from the left) and "81.4%" counts beside it; a faint **ambient glow** in `accent-light` blooms behind the card and stays ≤ 0.3 (→ `ambient-glow-bloom`).
Scene 4 (3.4–4.2s): the note "contribution before overheads (estimate) · costed at the prices in force on 31 Aug" fades in; then the frame **holds still** — this is a held read, no motion.


## Frame 5 — Push and fix

- scene: The menu ranked by what each item keeps: Sulaimani 92.3%, Karak Tea (Cup) 82.9%, Karak Tea (Flask 1 L) 81.4% ... Chicken 65 Dry 38.1%, Mint Lemonade -5.3%. The product's own sentence lands under it: "Chicken 65 Dry sold AED 3,774 and kept 38.1%; the menu keeps 67.4%."
- voiceover: "Push what earns. Fix what quietly loses. Branch by branch."
- duration: 4.754s
- transition_in: push-slide LEFT
- status: animated
- src: compositions/frames/05-push-and-fix.html
- type: benefit_highlight
- persuasion: Negative contrast
- beat: control
- blueprint: grid-card-assemble
- asset_candidates: assets/screen-dashboard.png — the real dashboard, a layout reference for the ranked rows and the quote card, never shown whole

narrativeRole: The wow: the whole menu carries a margin, ranked, and the owner knows what to push and what not to. Three branches named in the corner say it scales.
keyMessage: Know what to push and what to fix.

- blueprint: grid-card-assemble (Reproduce — the stacked-list variant)
- focal: none — the built list is the picture
- roles: screen-dashboard.png = background, not placed — the layout reference for the ranked rows and the quote card; the figures on screen are the dashboard payload's own, not a crop
- sfx: tick-soft ×7 (one per row, quiet cascade), thump-low (the plum row), chip-pop-soft

Scene 1 (0.0–0.6s): the label "What each item keeps" and the three branch chips (Al Quoz filled Date Palm, Karama and Deira outlined) are present at t=0, top band; the white list card is present and empty.
Scene 2 (0.6–1.9s) — "Push what earns.": rows 1–3 (Sulaimani 92.3%, Karak Tea (Cup) 82.9%, Karak Tea (Flask 1 L) 81.4%) **assemble in a staggered cascade** — each fades and slides a short distance into its slot (→ `spring-pop-entrance` staggered, smooth, ≈ 0.12 s gap); on each arrival its bar **fills to its value** (→ `stat-bars-and-fills`, `scaleX`) and its percentage counts (→ `counting-dynamic-scale`); the three "Push" chips pop in Confirmed Green after the bars land.
Scene 3 (1.9–3.2s) — "Fix what quietly loses.": rows 4–7 (Butter Chicken 64.2%, Egg Paratha 51.0%, Chicken 65 Dry 38.1%, Mint Lemonade -5.3%) cascade in the same way; Mint Lemonade's bar fills plum from the left as a short negative stub and its figure reads plum; the two "Fix" chips pop in gold-soft on "loses".
Scene 4 (3.2–4.8s) — "Branch by branch.": the filled branch chip **cycles in place** Al Quoz → Karama → Deira once, quickly, landing on Deira (→ `discrete-text-sequence` in-place token cycle on the chip fill); the quote card with the gold left rule slides up beneath the list and its sentence "Chicken 65 Dry sold AED 3,774 and kept 38.1%; the menu keeps 67.4%." fades in as one block with "the dashboard's own sentence · estimated" under it; hold.


## Frame 6 — Every morning

- scene: A phone at 07:00 with the real daily brief card: the latest day, the month so far, materials share, the three branches, earning most and least, and the price spike "Milk Powder up AED 3.40 per kg since 21 Aug, AED 109 at stake"
- voiceover: "Every morning on your phone, every number traceable to its invoice."
- duration: 4.284s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/06-every-morning.html
- type: social_proof
- persuasion: Show-don't-tell proof
- beat: trust + peace of mind
- blueprint: device-surface-showcase
- asset_candidates: assets/daily-brief-card.png — the real 07:00 brief card; assets/faida-mark.svg — the sender mark on the phone

narrativeRole: Proof that the output is real and arrives without being asked for, on the same phone the invoices left from. The traceability line is the trust promise from the landing page.
keyMessage: It comes to you, and every figure has a source.

- blueprint: device-surface-showcase (Adapt)
- focal: assets/daily-brief-card.png
- roles: daily-brief-card.png = cutout (the message inside the phone screen, full width of the screen) · faida-mark.svg = supporting (the sender mark in the phone's header)
- sfx: notification-chime-soft, scroll-swish-soft, tick-soft

Adapt: static-tour register with one phone (`compositions/components/device-frame-stage.html` for the bezel, restyled to `frame.md`: ink bezel, cream screen) at the left as sketched; keep the signature - the surface is operated on its own face and its screen advances - by scrolling the brief card inside the screen; no camera.
Scene 1 (0.0–0.8s) — "Every morning on your phone,": the phone **slides in from the left edge and settles** (→ `spring-pop-entrance` smooth, x-translate); its header (mark, "Faida", "07:00") is on the screen at t=0, the screen otherwise empty; at right the label "Every morning" fades up and "07:00" **hard-cuts in** big on the word "morning" (→ `discrete-text-sequence`). Layout: asymmetric 40/60, phone left, copy column right.
Scene 2 (0.8–2.3s): inside the screen the brief card arrives as a **chat-message entry** growing from the sender's corner (`compositions/components/chat-message.html`), showing its top (the four tiles); then the screen **scrolls the card upward** by ~40% of its height inside the clipped screen (→ `3d-page-scroll`, flat `translateY` inside the phone; the moving layer marked `data-layout-allow-overflow`), bringing the branch table and the price spike line into view; at right the description line "Sales, kept, materials, branches, the dish to push and the price that moved." fades in.
Scene 3 (2.3–3.6s) — "every number traceable to its invoice.": the small bubble under the card ("Milk Powder up AED 3.40 per kg since 21 Aug · AED 109 at stake") pops in, and a **gold marker sweep** underlines "AED 109 at stake" (→ `css-marker-patterns`); at right the card "Every number → its invoice / tap a figure, see the paper it came from" slides up (→ `spring-pop-entrance` smooth) on "invoice".
Scene 4 (3.6–4.3s): hold; at most a subtle jitter on the phone.


## Frame 7 — Faida

- scene: The stage clears; the mark draws itself and the wordmark completes the lockup; under it the landing page's own line, "Know the profit margin on every item you sell." and "Private pilot · faida-web-nine.vercel.app"
- voiceover: "Faida. Know the margin on every item you sell."
- duration: 3.422s
- transition_in: crossfade
- status: animated
- src: compositions/frames/07-faida.html
- type: cta
- persuasion: Future pacing
- beat: inevitability
- blueprint: logo-assemble-lockup
- asset_candidates: assets/faida-wordmark-horizontal.svg — the primary lockup; assets/faida-mark.svg — the mark that draws on first

narrativeRole: Name the product once, restate the message in the landing page's words, and point at the pilot.
keyMessage: Faida. Every item. Every branch. Real margins.

- blueprint: logo-assemble-lockup (Adapt)
- focal: assets/faida-wordmark-horizontal.svg
- roles: faida-wordmark-horizontal.svg = cutout (the finished lockup, centred) · faida-mark.svg = supporting (the mark's paths, drawn on first, then replaced in place by the lockup's own mark at identical geometry)
- sfx: brand-sting-soft, pill-pop-soft

Adapt: the parts-arrive / settled-reveal register on a static frame — the stage is already clear (a cream field); keep the signature - the mark comes to exist and resolves into the centred lockup - by self-drawing the mark's outline and letting the wordmark arrive beside it; no camera push, no streak.
Scene 1 (0.0–0.9s) — "Faida.": on the cream field the mark's outline **self-draws** in Date Palm (→ `svg-path-draw`), then its fills (Date Palm and the gold leaf) fade in; the wordmark "faida" **rises in beside it** letter by letter (a short staggered `fromTo` rise, each letter cut to full opacity on arrival - never faded), completing the horizontal lockup at the sketch's position (centre, upper third). This is the final frame: the lockup is the hero at ≥ 40% width.
Scene 2 (0.9–2.2s) — "Know the margin on every item you sell.": the two-line title reveals **per-word staggered** beneath (→ `dynamic-content-sequencing`), ink, Manrope.
Scene 3 (2.2–2.9s): the Date Palm pill "Private pilot · faida-web-nine.vercel.app" settles in from a slightly smaller scale on a long-tail ease; the small line "Every item. Every branch. Real margins." fades in under it.
Scene 4 (2.9–3.4s): hold to the end; as the final frame a quiet settle is allowed — no exit motion.

