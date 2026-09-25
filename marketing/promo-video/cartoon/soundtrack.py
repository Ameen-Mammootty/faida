"""Voices, sound effects and the timeline for the cartoon cut.

Three Kokoro-82M voices read the script line by line (narrator, owner,
supervisor). Every line's start and end, every scene's start, and each
character's mouth-opening envelope (for lip sync) go to build/timings.js,
which index.html reads. Sound effects are synthesised here too, so nothing
is licensed. Writes build/voice.wav, build/sfx.wav, build/timings.js and
build/score.json (the music's timeline for ../music.mjs).

    python soundtrack.py         # needs ../manim/models/kokoro-v1.0.onnx and voices-v1.0.bin
"""

import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = Path(__file__).parent
BUILD = HERE / "build"
MODELS = HERE.parent / "manim" / "models"
SR = 24000
FPS = 30
BAR = 2.0

VOICES = {  # speaker: (voice, speed)
    "narrator": ("af_heart", 1.0),
    "owner": ("am_michael", 0.96),
    "sup": ("am_puck", 1.08),
}
PHONEME_FIXES = {"fˈeɪdə": "fˈɑːiːdə", "kˈæɹæk": "kˈʌɹʌk"}

# ("scene", id) starts a scene; ("pause", s) holds for the action; ("say", id,
# speaker, line) is a line the pictures key their beats to by id.
SCRIPT = [
    ("scene", "night"),
    ("pause", 0.8),
    ("say", "n_night", "narrator", "Every night, in cafeterias across the Gulf, a supervisor sits down to this."),
    ("pause", 0.4),
    ("say", "n_typing", "narrator", "Invoice after invoice. Line after line. All typed in by hand."),
    ("pause", 1.6),
    ("say", "s_typo", "sup", "Milk powder... four thousand seven hundred?"),
    ("pause", 0.9),
    ("say", "s_mistake", "sup", "Oh no. Okay... I made a mistake. Again."),
    ("pause", 1.0),
    ("scene", "owner"),
    ("pause", 0.5),
    ("say", "n_owner", "narrator", "Meanwhile, the owner stares at his menu."),
    ("pause", 0.3),
    ("say", "o_which", "owner", "Karak? Paratha? Chicken sixty-five?"),
    ("pause", 0.3),
    ("say", "o_money", "owner", "Which one is actually making me money?"),
    ("pause", 0.4),
    ("say", "n_costs", "narrator", "Costs keep climbing. Profit keeps sliding. And every decision is a guess."),
    ("pause", 0.5),
    ("say", "o_sigh", "owner", "Sales look fine... so where is the money going?"),
    ("pause", 1.0),
    ("scene", "faida"),
    ("pause", 0.3),
    ("say", "n_meet", "narrator", "Now, meet Faida."),
    ("pause", 0.6),
    ("scene", "fixed"),
    ("pause", 0.2),
    ("say", "n_forward", "narrator", "Just forward the invoice on WhatsApp."),
    ("pause", 0.2),
    ("say", "n_reads", "narrator", "Faida reads every line, checks the maths, and costs it right down to the plate."),
    ("pause", 0.3),
    ("say", "s_thatsit", "sup", "Wait... that's it?"),
    ("pause", 0.4),
    ("say", "n_menu", "narrator", "And your menu finally tells you what to push, and what to fix."),
    ("pause", 0.3),
    ("say", "o_push", "owner", "Push the karak. Fix that chicken price!"),
    ("pause", 1.0),
    ("scene", "end"),
    ("pause", 0.3),
    ("say", "n_end", "narrator", "Faida. Profit, in plain sight."),
    ("pause", 3.0),
]
# scenes that start on a downbeat, because the music hits there
ON_THE_BEAT = {"faida", "end"}


def speak(kokoro, text, voice, speed):
    ph = kokoro.tokenizer.phonemize(text, "en-us")
    for wrong, right in PHONEME_FIXES.items():
        ph = ph.replace(wrong, right)
    audio, sr = kokoro.create(ph, voice=voice, speed=speed, is_phonemes=True)
    assert sr == SR
    return audio


def envelope(track, duration):
    """Mouth opening per frame, 0..1, from the loudness of that speaker's own track."""
    n = int(duration * FPS) + 1
    hop = SR // FPS
    rms = np.array([np.sqrt(np.mean(track[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
    ref = np.percentile(rms[rms > 1e-3], 90) if np.any(rms > 1e-3) else 1
    env = np.clip(rms / ref, 0, 1) ** 0.7
    env[rms < 0.004] = 0
    return [round(float(v), 2) for v in env]


# ---------- sound effects, synthesised ----------
rng = np.random.default_rng(7)


def sfx_click(gain=0.25):
    n = int(0.018 * SR)
    x = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.003 * SR))
    return np.diff(x, prepend=0) * gain


def sfx_tick(gain=0.18):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * math.pi * 2400 * t) * np.exp(-t * 180) * gain


def sfx_buzz(gain=0.3):
    out = []
    for f in (196, 147):
        t = np.arange(int(0.22 * SR)) / SR
        out += [np.sign(np.sin(2 * math.pi * f * t)) * 0.6 * np.minimum(1, (0.22 - t) * 40) * gain, np.zeros(int(0.04 * SR))]
    return np.concatenate(out)


def sfx_whoosh(dur=0.45, gain=0.35):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    y, out = 0.0, np.zeros(n)
    for i in range(n):
        k = i / n
        a = 1 - math.exp(-2 * math.pi * (300 + 5000 * math.sin(math.pi * k)) / SR)
        y += a * (x[i] - y)
        out[i] = y * math.sin(math.pi * k) ** 2
    return out * gain


def sfx_ding(f=1318.5, gain=0.25, dur=0.9):
    t = np.arange(int(dur * SR)) / SR
    return (np.sin(2 * math.pi * f * t) + 0.4 * np.sin(2 * math.pi * 2 * f * t) * np.exp(-t * 9)) * np.exp(-t * 4) * gain


def sfx_pop(gain=0.3):
    t = np.arange(int(0.12 * SR)) / SR
    return np.sin(2 * math.pi * (300 + 900 * np.exp(-t * 40)) * t) * np.exp(-t * 30) * gain


def sfx_sigh_boing(gain=0.22):
    t = np.arange(int(0.6 * SR)) / SR
    return np.sin(2 * math.pi * (220 * np.exp(-t * 1.6)) * t * 1.0) * np.exp(-t * 3) * gain


def place(track, clip, at):
    i = int(at * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(clip))
    track[i:j] += clip[: j - i]


def main():
    BUILD.mkdir(exist_ok=True)
    kokoro = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    clips, lines, scenes, t = [], {}, [], 0.0
    for item in SCRIPT:
        kind = item[0]
        if kind == "scene":
            if item[1] in ON_THE_BEAT:
                t = math.ceil(t / BAR) * BAR
            scenes.append({"id": item[1], "start": round(t, 3)})
        elif kind == "pause":
            t += item[1]
        else:
            _, line_id, speaker, text = item
            voice, speed = VOICES[speaker]
            audio = speak(kokoro, text, voice, speed)
            clips.append((t, speaker, audio))
            lines[line_id] = {"speaker": speaker, "text": text, "start": round(t, 3), "end": round(t + len(audio) / SR, 3)}
            t += len(audio) / SR
    duration = math.ceil(t * FPS) / FPS
    n = int(duration * SR) + SR
    voice = np.zeros(n)
    by_speaker = {s: np.zeros(n) for s in VOICES}
    for start, speaker, audio in clips:
        place(voice, audio, start)
        place(by_speaker[speaker], audio, start)

    # sound effects on the same timeline
    fx = np.zeros(n)
    L = lines
    at = {s["id"]: s["start"] for s in scenes}
    for k in np.arange(0.2, at["owner"], 1.0):  # the clock, faster during the typing montage
        place(fx, sfx_tick(), k)
    for k in np.arange(L["n_typing"]["start"] - 0.2, L["s_typo"]["start"] + 1.2, 0.5):
        place(fx, sfx_tick(0.12), k)
    tt = L["n_night"]["end"] - 1.2
    while tt < L["s_typo"]["end"] + 0.4:  # typing
        place(fx, sfx_click(0.22 + 0.1 * rng.random()), tt)
        tt += 0.07 + 0.09 * rng.random()
    place(fx, sfx_buzz(), L["s_typo"]["end"] + 0.1)
    for s in scenes[1:]:
        place(fx, sfx_whoosh(0.5, 0.3), max(0, s["start"] - 0.3))
    place(fx, sfx_sigh_boing(), L["n_costs"]["end"] - 0.3)
    place(fx, sfx_ding(1567.98, 0.28), at["faida"] + 0.25)
    for i in range(5):  # invoices flying into the phone, each with a tick of confirmation
        place(fx, sfx_whoosh(0.3, 0.18), L["n_reads"]["start"] + 0.2 + i * 0.55)
        place(fx, sfx_pop(0.22), L["n_reads"]["start"] + 0.45 + i * 0.55)
    place(fx, sfx_ding(1318.5, 0.2), L["n_forward"]["end"] - 0.2)
    for i in range(3):
        place(fx, sfx_pop(0.25), L["n_menu"]["start"] + 1.0 + i * 0.35)
    place(fx, sfx_ding(1046.5, 0.25), at["end"] + 0.35)

    sf.write(BUILD / "voice.wav", voice.astype(np.float32), SR)
    sf.write(BUILD / "sfx.wav", fx.astype(np.float32), SR)
    timings = {
        "duration": duration, "fps": FPS, "scenes": scenes, "lines": lines,
        "mouth": {s: envelope(by_speaker[s], duration) for s in ("owner", "sup")},
    }
    (BUILD / "timings.js").write_text("window.T = " + json.dumps(timings) + ";\n")
    score = {
        "duration": duration, "cuts": [s["start"] for s in scenes[1:]], "calmUntil": at["faida"],
        "drops": [at["faida"], at["end"]], "halfTime": [at["faida"], at["fixed"]],
        "breakdown": [at["end"], at["end"]], "product": at["fixed"], "end": duration - 1.5,
        "finalChord": at["end"] + 0.3, "melody": False, "out": str(BUILD / "music.wav"),
    }
    (BUILD / "score.json").write_text(json.dumps(score, indent=2))
    for s in scenes:
        print(f"{s['id']:7s} {s['start']:5.1f}s")
    print(f"total {duration:.1f}s")


if __name__ == "__main__":
    main()
