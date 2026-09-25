#!/usr/bin/env bash
# The narrated cut, end to end: voice -> music -> pictures -> one MP4.
#   ./build.sh          1080p60 -> ../out/faida-promo-narrated.mp4
#   ./build.sh -ql      480p15 draft
set -euo pipefail
cd "$(dirname "$0")"
QUALITY="${1:--qh}"
PY="${PYTHON:-python}"
MANIM="${MANIM:-manim}"

"$PY" narration.py                         # build/voice.wav, timings.json, score.json
node ../music.mjs build/score.json         # build/music.wav, cut to the same timeline
"$MANIM" "$QUALITY" --disable_caching --progress_bar none film.py Film
VIDEO=$(ls -t media/videos/film/*/Film.mp4 | head -1)

# The voice leads; the music sits under it and ducks further whenever she speaks.
ffmpeg -y -loglevel error -i "$VIDEO" -i build/voice.wav -i build/music.wav -filter_complex "
  [1:a]aresample=48000,highpass=f=80,acompressor=threshold=0.1:ratio=3:attack=5:release=120,pan=stereo|c0=c0|c1=c0,asplit=2[vox][key];
  [2:a]aresample=48000,volume=0.32[bed];
  [bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=400[ducked];
  [ducked][vox]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[mix]" \
  -map 0:v -map "[mix]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  ../out/faida-promo-narrated.mp4
echo "../out/faida-promo-narrated.mp4"
