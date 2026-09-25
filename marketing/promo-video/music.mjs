// A soundtrack synthesised from scratch, so the film carries no licensed audio:
// 120 bpm, one bar per two seconds, so every scene cut lands on a downbeat.
// With no argument it scores index.html's 48-second cut and writes
// out/music.wav (44.1 kHz, 16-bit stereo); `node music.mjs score.json` scores
// another cut (the narrated one: manim/score.json) from its own timeline.
import { writeFileSync, mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
// drops: the two hits (the logo, the close); halfTime follows the first, breakdown
// precedes the second; product is where the arpeggio and melody take over.
const SCORE = process.argv[2] ? JSON.parse(readFileSync(process.argv[2], "utf8")) : {
  duration: 48, cuts: [4, 10, 14, 22, 29, 37, 41], drops: [10, 41], halfTime: [10, 14], breakdown: [37, 41],
  product: 14, end: 46, finalChord: 44, melody: true, out: "out/music.wav",
};
const SR = 44100, DUR = SCORE.duration, N = SR * DUR, BEAT = 0.5, BAR = 2;
const L = new Float32Array(N), R = new Float32Array(N);
const CUTS = SCORE.cuts, [D1, D2] = SCORE.drops, END = SCORE.end;

// deterministic noise so every render sounds identical
let seed = 7;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
const add = (i, l, r = l) => { if (i >= 0 && i < N) { L[i] += l; R[i] += r; } };
const lpA = (fc) => 1 - Math.exp((-2 * Math.PI * fc) / SR);

// section map: what plays where
// calmUntil: no drums or arpeggio before it, only the pad (the cartoon's problem half)
const calm = (t) => t < (SCORE.calmUntil || 0);
const full = (t) => !calm(t) && (t >= 0 && t < D1 - 0.5) || (t >= SCORE.halfTime[1] && t < SCORE.breakdown[0]) || (t >= D2 && t < END);
const halfTime = (t) => t >= SCORE.halfTime[0] && t < SCORE.halfTime[1];
const breakdown = (t) => t >= SCORE.breakdown[0] && t < SCORE.breakdown[1];

// Am  F  C  G, one chord per bar
const CHORDS = [
  { bass: 55.0, pad: [220.0, 261.63, 329.63] },
  { bass: 43.65, pad: [174.61, 220.0, 261.63] },
  { bass: 65.41, pad: [261.63, 329.63, 392.0] },
  { bass: 49.0, pad: [196.0, 246.94, 293.66] },
];
const chordAt = (t) => CHORDS[Math.floor(t / BAR) % 4];

// kick envelope, used again to duck the pad and bass
const kickTimes = [];
for (let t = 0; t < END; t += BEAT) {
  const b = Math.round(t / BEAT) % 4;
  if (full(t) || (halfTime(t) && (b === 0 || b === 2))) kickTimes.push(t);
}
const duck = new Float32Array(N).fill(1);

function kick(t0, gain = 0.9) {
  const s = Math.floor(t0 * SR);
  let ph = 0;
  for (let i = 0; i < SR * 0.45; i++) {
    const t = i / SR, f = 52 + 160 * Math.exp(-t * 26);
    ph += (2 * Math.PI * f) / SR;
    const env = Math.exp(-t * 8) * (t < 0.002 ? t / 0.002 : 1);
    // body, then a short knock around 180-250 Hz and a click: what a phone speaker actually plays
    const knock = Math.sin(2 * Math.PI * 190 * t) * Math.exp(-t * 30) * 0.55 + Math.sin(ph * 3) * Math.exp(-t * 40) * 0.25;
    add(s + i, (Math.sin(ph) * env * 0.45 + knock) * gain + (i < 180 ? rnd() * 0.45 * (1 - i / 180) : 0));
  }
  for (let i = 0; i < SR * 0.3; i++) {
    const k = s + i;
    if (k < N) duck[k] = Math.min(duck[k], 1 - 0.65 * Math.exp(-(i / SR) * 12));
  }
}

function hat(t0, gain = 0.2, len = 0.05, pan = 0.15) {
  const s = Math.floor(t0 * SR);
  let prev = 0;
  for (let i = 0; i < SR * len; i++) {
    const x = rnd(), hp = x - prev; prev = x;
    const v = hp * Math.exp((-i / SR) * (4 / len)) * gain;
    add(s + i, v * (1 - pan), v * (1 + pan));
  }
}

function clap(t0, gain = 0.5) {
  const s = Math.floor(t0 * SR), a = lpA(2200);
  let y = 0, prev = 0;
  for (let i = 0; i < SR * 0.22; i++) {
    const t = i / SR;
    const bursts = t < 0.03 ? (Math.floor(t / 0.01) % 2 === 0 ? 1 : 0.4) : 1;
    const x = rnd(); y += a * (x - y);
    const bp = y - prev * 0.6; prev = y;
    add(s + i, bp * Math.exp(-t * 18) * bursts * gain * 2.2, bp * Math.exp(-t * 16) * bursts * gain * 2.2);
  }
}

function pluck(t0, f, gain = 0.1, pan = 0) {
  const s = Math.floor(t0 * SR), a = lpA(4200);
  let ph = 0, y = 0;
  for (let i = 0; i < SR * 0.28; i++) {
    const t = i / SR;
    ph = (ph + f / SR) % 1;
    const saw = 2 * ph - 1;
    y += a * (saw - y);
    const v = y * Math.exp(-t * 14) * gain;
    add(s + i, v * (1 - pan), v * (1 + pan));
  }
}

// a bell for the melody: a sine with a decaying FM shimmer
function bell(t0, f, gain = 0.1, len = 0.6, pan = 0) {
  const s = Math.floor(t0 * SR);
  for (let i = 0; i < SR * len; i++) {
    const t = i / SR;
    const v = Math.sin(2 * Math.PI * f * t + 1.6 * Math.exp(-t * 7) * Math.sin(2 * Math.PI * 2 * f * t))
      * Math.exp(-t * (5 / len)) * Math.min(1, t / 0.003) * gain;
    add(s + i, v * (1 - pan), v * (1 + pan));
  }
}

function whoosh(tc, gain = 0.3) {
  const s = Math.floor((tc - 0.45) * SR), len = Math.floor(0.6 * SR);
  let y = 0;
  for (let i = 0; i < len; i++) {
    const k = i / len, fc = 300 + 5500 * Math.sin(Math.PI * k);
    y += lpA(fc) * (rnd() - y);
    const env = Math.sin(Math.PI * k) ** 2;
    add(s + i, y * env * gain * (1.2 - k), y * env * gain * (0.4 + k));
  }
}

function riser(t0, t1, gain = 0.2) {
  const s = Math.floor(t0 * SR), len = Math.floor((t1 - t0) * SR);
  let y = 0, ph = 0;
  for (let i = 0; i < len; i++) {
    const k = i / len;
    y += lpA(200 + 7000 * k * k) * (rnd() - y);
    ph += (2 * Math.PI * (220 + 660 * k * k)) / SR;
    add(s + i, (y * 0.9 + Math.sin(ph) * 0.15) * k * k * gain);
  }
}

function impact(t0, gain = 0.9) {
  const s = Math.floor(t0 * SR);
  let ph = 0, y = 0;
  for (let i = 0; i < SR * 2.2; i++) {
    const t = i / SR;
    ph += (2 * Math.PI * (38 + 60 * Math.exp(-t * 10))) / SR;
    y += lpA(900) * (rnd() - y);
    add(s + i, (Math.sin(ph) * Math.exp(-t * 2.2) + y * Math.exp(-t * 5) * 0.8) * gain);
  }
}

// ---------- arrange ----------
kickTimes.forEach((t) => kick(t));
for (let t = 0; t < END; t += BEAT) {
  const b = Math.round(t / BEAT) % 4;
  if (full(t) || breakdown(t)) hat(t + BEAT / 2, breakdown(t) ? 0.13 : 0.22);
  if (full(t)) { hat(t + BEAT / 4, 0.08, 0.03, -0.3); hat(t + (3 * BEAT) / 4, 0.08, 0.03, -0.3); }
  if (full(t) && t >= 4 && (b === 1 || b === 3)) clap(t);
  if (halfTime(t) && b === 2) clap(t, 0.4);
}
// sixteenth-note arpeggio over the chord, from the product scenes on
for (let t = 0; t < END; t += BEAT / 4) {
  if (!full(t) && !breakdown(t)) continue;
  const i = Math.round(t / (BEAT / 4)), c = chordAt(t).pad;
  const f = c[[0, 1, 2, 1, 2, 0, 1, 2][i % 8]] * 2;
  pluck(t, f, breakdown(t) ? 0.14 : t < SCORE.product ? 0.1 : 0.12, i % 2 ? 0.35 : -0.35);
}
// the hook: an eighth-note bell melody over each chord, from the product scenes on (0 = rest)
const MELODY = [
  [659.25, 0, 523.25, 587.33, 659.25, 0, 783.99, 659.25],
  [698.46, 0, 659.25, 523.25, 440.0, 0, 523.25, 0],
  [783.99, 0, 659.25, 783.99, 880.0, 0, 783.99, 659.25],
  [587.33, 0, 493.88, 587.33, 659.25, 0, 587.33, 0],
];
for (let t = SCORE.product; t < END && SCORE.melody; t += BEAT / 2) {
  if (!full(t) && !breakdown(t)) continue;
  const f = MELODY[Math.floor(t / BAR) % 4][Math.round((t % BAR) / (BEAT / 2)) % 8];
  if (f) bell(t, f, breakdown(t) ? 0.18 : 0.16, 0.5, 0.1);
}
// the logo and the close ring out as a chord
[[D1, [440.0, 523.25, 659.25, 880.0]], [D2, [349.23, 440.0, 523.25, 698.46]], [SCORE.finalChord, [440.0, 523.25, 659.25, 880.0]]].forEach(([t, ch]) =>
  ch.forEach((f, j) => bell(t + j * 0.04, f, 0.09, 2.4, (j - 1.5) * 0.2)));
CUTS.forEach((c) => whoosh(c));
riser(D1 - 2, D1 - 0.05, 0.24);
riser(D2 - 2, D2 - 0.05, 0.22);
impact(D1);
impact(D2, 0.8);
kick(D1, 1.0);
kick(D2, 1.0);

// pad and sub bass, ducked under the kick
{
  const aP = lpA(3000), aB = lpA(1600);
  const phP = new Float64Array(6); let phB = 0, yPL = 0, yPR = 0, yB = 0;
  for (let i = 0; i < N; i++) {
    const t = i / SR, c = chordAt(t);
    const fadeIn = Math.min(1, t / 1.2), fadeOut = t > END - 1 ? Math.max(0, 1 - (t - END + 1) / (DUR - END + 1)) : 1;
    const gap = t >= D1 - 0.1 && t < D1 ? 0 : 1;
    let l = 0, r = 0;
    c.pad.forEach((f, j) => {
      phP[j] = (phP[j] + (f * 1.003) / SR) % 1; phP[j + 3] = (phP[j + 3] + (f * 0.997) / SR) % 1;
      l += 2 * phP[j] - 1; r += 2 * phP[j + 3] - 1;
    });
    yPL += aP * (l - yPL); yPR += aP * (r - yPR);
    const padG = (halfTime(t) || breakdown(t) ? 0.14 : 0.1) * fadeIn * fadeOut * gap;
    const dk = duck[i];
    L[i] += yPL * padG * dk; R[i] += yPR * padG * dk;

    if (t < END && gap) {
      // eighth-note bass pulse
      const e = (t % (BEAT / 2)) / (BEAT / 2);
      const env = Math.exp(-e * 3.5) * (breakdown(t) ? 0.4 : 1);
      phB = (phB + (c.bass * 2) / SR) % 1;
      yB += aB * (2 * phB - 1 - yB);
      const sub = Math.sin(Math.PI * phB);
      const v = (yB * 0.9 + sub * 0.2) * env * 0.3 * dk * fadeOut;
      L[i] += v; R[i] += v;
    }
  }
}

// ---------- master: high-pass at 40 Hz, soft clip, normalise, write ----------
{
  const a = lpA(40); let lo = 0, ro = 0;
  for (let i = 0; i < N; i++) { lo += a * (L[i] - lo); ro += a * (R[i] - ro); L[i] -= lo; R[i] -= ro; }
}
let peak = 0;
for (let i = 0; i < N; i++) { L[i] = Math.tanh(L[i] * 1.2); R[i] = Math.tanh(R[i] * 1.2); peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i])); }
const g = 0.89 / peak;
const buf = Buffer.alloc(44 + N * 4);
buf.write("RIFF", 0); buf.writeUInt32LE(36 + N * 4, 4); buf.write("WAVE", 8);
buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34);
buf.write("data", 36); buf.writeUInt32LE(N * 4, 40);
for (let i = 0; i < N; i++) {
  buf.writeInt16LE(Math.round(L[i] * g * 32767), 44 + i * 4);
  buf.writeInt16LE(Math.round(R[i] * g * 32767), 46 + i * 4);
}
const outPath = path.resolve(here, SCORE.out);
mkdirSync(path.dirname(outPath), { recursive: true });
writeFileSync(outPath, buf);
console.log(path.relative(here, outPath));
