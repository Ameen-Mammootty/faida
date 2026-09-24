// A 48-second soundtrack synthesised from scratch, so the film carries no
// licensed audio: 120 bpm, one bar per two seconds, so every scene cut in
// index.html lands on a downbeat. Writes out/music.wav (44.1 kHz, 16-bit stereo).
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SR = 44100, DUR = 48, N = SR * DUR, BEAT = 0.5, BAR = 2;
const L = new Float32Array(N), R = new Float32Array(N);
const CUTS = [4, 10, 14, 22, 29, 37, 41];

// deterministic noise so every render sounds identical
let seed = 7;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
const add = (i, l, r = l) => { if (i >= 0 && i < N) { L[i] += l; R[i] += r; } };
const lpA = (fc) => 1 - Math.exp((-2 * Math.PI * fc) / SR);

// section map: what plays where
const full = (t) => (t >= 0 && t < 9.5) || (t >= 14 && t < 37) || (t >= 41 && t < 46);
const halfTime = (t) => t >= 10 && t < 14;
const breakdown = (t) => t >= 37 && t < 41;

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
for (let t = 0; t < 46; t += BEAT) {
  const b = Math.round(t / BEAT) % 4;
  if (full(t) || (halfTime(t) && (b === 0 || b === 2))) kickTimes.push(t);
}
const duck = new Float32Array(N).fill(1);

function kick(t0, gain = 0.9) {
  const s = Math.floor(t0 * SR);
  let ph = 0;
  for (let i = 0; i < SR * 0.45; i++) {
    const t = i / SR, f = 45 + 110 * Math.exp(-t * 28);
    ph += (2 * Math.PI * f) / SR;
    const env = Math.exp(-t * 7.5) * (t < 0.002 ? t / 0.002 : 1);
    add(s + i, Math.sin(ph) * env * gain + (i < 90 ? rnd() * 0.25 * (1 - i / 90) : 0));
  }
  for (let i = 0; i < SR * 0.3; i++) {
    const k = s + i;
    if (k < N) duck[k] = Math.min(duck[k], 1 - 0.65 * Math.exp(-(i / SR) * 12));
  }
}

function hat(t0, gain = 0.12, len = 0.05, pan = 0.15) {
  const s = Math.floor(t0 * SR);
  let prev = 0;
  for (let i = 0; i < SR * len; i++) {
    const x = rnd(), hp = x - prev; prev = x;
    const v = hp * Math.exp((-i / SR) * (4 / len)) * gain;
    add(s + i, v * (1 - pan), v * (1 + pan));
  }
}

function clap(t0, gain = 0.32) {
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

function pluck(t0, f, gain = 0.07, pan = 0) {
  const s = Math.floor(t0 * SR), a = lpA(2600);
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

function whoosh(tc, gain = 0.22) {
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
for (let t = 0; t < 46; t += BEAT) {
  const b = Math.round(t / BEAT) % 4;
  if (full(t) || breakdown(t)) hat(t + BEAT / 2, breakdown(t) ? 0.08 : 0.13);
  if (full(t)) { hat(t + BEAT / 4, 0.05, 0.03, -0.3); hat(t + (3 * BEAT) / 4, 0.05, 0.03, -0.3); }
  if (full(t) && t >= 4 && (b === 1 || b === 3)) clap(t);
  if (halfTime(t) && b === 2) clap(t, 0.4);
}
// sixteenth-note arpeggio over the chord, from the product scenes on
for (let t = 0; t < 46; t += BEAT / 4) {
  if (!(t >= 14 && t < 37) && !breakdown(t) && !(t >= 41)) continue;
  const i = Math.round(t / (BEAT / 4)), c = chordAt(t).pad;
  const f = c[[0, 1, 2, 1, 2, 0, 1, 2][i % 8]] * 2;
  pluck(t, f, breakdown(t) ? 0.06 : 0.05, i % 2 ? 0.35 : -0.35);
}
CUTS.forEach((c) => whoosh(c));
riser(8.0, 9.95, 0.24);
riser(39.0, 40.95, 0.22);
impact(10.0);
impact(41.0, 0.8);
kick(10.0, 1.0);
kick(41.0, 1.0);

// pad and sub bass, ducked under the kick
{
  const aP = lpA(1400), aB = lpA(260);
  const phP = new Float64Array(6); let phB = 0, yPL = 0, yPR = 0, yB = 0;
  for (let i = 0; i < N; i++) {
    const t = i / SR, c = chordAt(t);
    const fadeIn = Math.min(1, t / 1.2), fadeOut = t > 45 ? Math.max(0, 1 - (t - 45) / 3) : 1;
    const gap = t >= 9.9 && t < 10 ? 0 : 1;
    let l = 0, r = 0;
    c.pad.forEach((f, j) => {
      phP[j] = (phP[j] + (f * 1.003) / SR) % 1; phP[j + 3] = (phP[j + 3] + (f * 0.997) / SR) % 1;
      l += 2 * phP[j] - 1; r += 2 * phP[j + 3] - 1;
    });
    yPL += aP * (l - yPL); yPR += aP * (r - yPR);
    const padG = (halfTime(t) || breakdown(t) ? 0.075 : 0.05) * fadeIn * fadeOut * gap;
    const dk = duck[i];
    L[i] += yPL * padG * dk; R[i] += yPR * padG * dk;

    if (t < 46 && gap) {
      // eighth-note bass pulse
      const e = (t % (BEAT / 2)) / (BEAT / 2);
      const env = Math.exp(-e * 3.5) * (breakdown(t) ? 0.4 : 1);
      phB = (phB + c.bass / SR) % 1;
      yB += aB * (2 * phB - 1 - yB);
      const sub = Math.sin(2 * Math.PI * phB);
      const v = (yB * 0.5 + sub * 0.6) * env * 0.32 * dk * fadeOut;
      L[i] += v; R[i] += v;
    }
  }
}

// ---------- master: soft clip, normalise, write ----------
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
const here = path.dirname(fileURLToPath(import.meta.url));
mkdirSync(path.join(here, "out"), { recursive: true });
writeFileSync(path.join(here, "out/music.wav"), buf);
console.log("out/music.wav");
