#!/usr/bin/env bash
# The cartoon cut, end to end: voices + sound effects -> music -> mix -> frames -> MP4.
#   ./build.sh           -> ../out/faida-cartoon.mp4 (1080p, 30 fps)
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python}"
"$PY" soundtrack.py                      # build/voice.wav, sfx.wav, timings.js, score.json
node ../music.mjs build/score.json       # build/music.wav: calm under the problem, the drop on Faida
# The voices lead; the music ducks under them; the effects sit in between.
ffmpeg -y -loglevel error -i build/voice.wav -i build/sfx.wav -i build/music.wav -filter_complex "
  [0:a]aresample=48000,highpass=f=80,acompressor=threshold=0.1:ratio=3:attack=5:release=120,pan=stereo|c0=c0|c1=c0,asplit=2[vox][key];
  [1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,volume=0.9[fx];
  [2:a]aresample=48000,volume=0.3[bed];
  [bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=400[ducked];
  [ducked][fx][vox]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 build/mix.wav
node ../render.mjs --page cartoon/index.html --audio cartoon/build/mix.wav --fps 30 --out out/faida-cartoon.mp4
