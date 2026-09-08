# The two faces the picture card draws with

The morning brief's picture card (`brief_card.py`, M10 WP-106) is drawn by the
API, on a server with no fonts of its own, so the two faces travel with the
code.
They are the brand's own (`Docs/brand/faida-brand-guidelines.md`): Manrope for
the brand voice - the wordmark, the four figures, the panel titles - and Inter
for the product voice, which is everything else.

Both are licensed under the **SIL Open Font License, Version 1.1**, which
permits bundling and redistribution with software.
The licence text of each is beside it, as the licence requires.

| File | Face | Source | sha256 |
|---|---|---|---|
| `Manrope[wght].ttf` | Manrope, variable weight 200-800 | https://github.com/google/fonts/blob/main/ofl/manrope/Manrope%5Bwght%5D.ttf | `d0639be45d0af36e798172419d7bd173c4bd4f29e2b76cbb69db1d11bf8b0a40` |
| `Inter[opsz,wght].ttf` | Inter, variable optical size and weight | https://github.com/google/fonts/blob/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf | `29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031` |
| `OFL-Manrope.txt` | the licence | https://github.com/google/fonts/blob/main/ofl/manrope/OFL.txt | - |
| `OFL-Inter.txt` | the licence | https://github.com/google/fonts/blob/main/ofl/inter/OFL.txt | - |

Fetched from Google Fonts' own repository on 2026-09-08.
Both upstream directories ship the variable font only, so a weight is chosen
here by its named instance (`Bold` for Manrope, `Regular` and `Medium` for
Inter) rather than by a separate file: `brief_card._font` pins the instance
when it loads the face, so no weight is ever synthesised.

The files live under `src/faida_api/` on purpose: they are package data, read
through `importlib.resources`, so an installed wheel finds them without
knowing where the source tree was.

Both faces carry Latin and Latin Extended only.
The brief is English for the pilot (`Docs/M10_DECOMPOSITION.md` §1); a card in
Arabic or Malayalam needs a face that carries the script, which is a font
question before it is a layout one.
