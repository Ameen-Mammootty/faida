"""The voiceover: Kokoro-82M reads the script one sentence at a time, so the
film knows when every sentence starts and can time its visuals to it.

Writes build/voice.wav, build/timings.json and build/score.json (the music's timeline). Each scene's length is its
lines plus breathing room, rounded up to whole bars of the 120 bpm bed, so
every cut lands on a downbeat of the music.

    python narration.py            # needs models/kokoro-v1.0.onnx and models/voices-v1.0.bin
"""

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
BUILD = HERE / "build"
MODELS = HERE / "models"
VOICE = "af_heart"
SPEED = 1.0
SR = 24000
BAR = 2.0  # seconds: one bar at 120 bpm
LEAD, GAP, TAIL = 0.45, 0.3, 0.55

# Names the phonemiser gets wrong, fixed in its own alphabet: Faida is the Arabic
# faa'ida, "FAH-ee-dah", not "FAY-da".
PHONEME_FIXES = {
    "fˈeɪdə": "fˈɑːiːdə",
    "kˈæɹæk": "kˈʌɹʌk",
    "dˈɛɹə": "dˈeɪɹə",
    "dˈɜːɹæmz": "dˈɜːɹhæmz",
}

# One entry per scene of film.py, in order. Every figure is illustrative and
# the display rules hold: "keeps", never profit; no food cost %.
SCRIPT = [
    ("hook", [
        "Your cafeteria sold six thousand, four hundred dirhams today.",
        "But how much did you actually keep?",
    ]),
    ("problem", [
        "Supplier invoices pile up.",
        "Prices creep up, quietly.",
        "And your margin shrinks with them.",
    ]),
    ("brand", [
        "Meet Faida.",
        "Profit, in plain sight.",
    ]),
    ("forward", [
        "Just forward the supplier's invoice on WhatsApp.",
        "Faida reads every line, checks that it adds up,",
        "and flags a price rise the moment it lands.",
    ]),
    ("plate", [
        "Every line is matched to your raw materials,",
        "and costed right down to the plate.",
        "So you know a cup of karak costs forty-nine fils, and keeps sixty-seven percent.",
    ]),
    ("dashboard", [
        "Your dashboard says it in plain words:",
        "which branch to look at first,",
        "and which dishes to push.",
    ]),
    ("brief", [
        "And every morning at seven,",
        "your numbers arrive on the phone you already carry.",
    ]),
    ("close", [
        "Every item. Every branch. Real margins.",
        "Faida. Now onboarding GCC restaurants, for our private pilot.",
    ]),
]


def speak(kokoro: Kokoro, text: str) -> np.ndarray:
    phonemes = kokoro.tokenizer.phonemize(text, "en-us")
    for wrong, right in PHONEME_FIXES.items():
        phonemes = phonemes.replace(wrong, right)
    audio, sr = kokoro.create(phonemes, voice=VOICE, speed=SPEED, is_phonemes=True)
    assert sr == SR
    return audio


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    track, scenes, t = [], [], 0.0
    for scene_id, lines in SCRIPT:
        cursor, sentences, parts = LEAD, [], [np.zeros(int(LEAD * SR), np.float32)]
        for i, line in enumerate(lines):
            audio = speak(kokoro, line)
            dur = len(audio) / SR
            sentences.append({"text": line, "start": round(cursor, 3), "end": round(cursor + dur, 3)})
            parts.append(audio)
            cursor += dur
            if i < len(lines) - 1:
                parts.append(np.zeros(int(GAP * SR), np.float32))
                cursor += GAP
        length = math.ceil((cursor + TAIL) / BAR) * BAR
        clip = np.concatenate(parts)
        clip = np.pad(clip, (0, int(length * SR) - len(clip)))
        track.append(clip)
        scenes.append({"id": scene_id, "start": t, "duration": length, "sentences": sentences})
        print(f"{scene_id:10s} {t:5.1f}s  +{length:.0f}s  ({cursor:.1f}s of speech)")
        t += length
    sf.write(BUILD / "voice.wav", np.concatenate(track), SR)
    (BUILD / "timings.json").write_text(json.dumps({"duration": t, "scenes": scenes}, indent=2))
    # the music follows the same timeline: a hit on the logo and on the close, the
    # breakdown under the morning brief, and no bell melody over the voice
    at = {s["id"]: s for s in scenes}
    score = {
        "duration": t, "cuts": [s["start"] for s in scenes[1:]],
        "drops": [at["brand"]["start"], at["close"]["start"]],
        "halfTime": [at["brand"]["start"], at["forward"]["start"]],
        "breakdown": [at["brief"]["start"], at["close"]["start"]],
        "product": at["forward"]["start"], "end": t - 2,
        "finalChord": at["close"]["start"] + at["close"]["sentences"][1]["start"],
        "melody": False, "out": str(BUILD / "music.wav"),
    }
    (BUILD / "score.json").write_text(json.dumps(score, indent=2))
    print(f"total {t:.0f}s -> build/voice.wav, build/timings.json")


if __name__ == "__main__":
    main()
