// Render index.html to an MP4: step the timeline frame by frame in headless
// Chromium, pipe each screenshot into ffmpeg, and lay the soundtrack under it.
//
//   node render.mjs                       -> out/faida-promo.mp4 (1080p, 60 fps)
//   node render.mjs --fps 15 --out out/preview.mp4
//   node render.mjs --stills 2,7.5,12     -> out/frames/still-*.png, no video
//   node render.mjs --page cartoon/index.html --audio cartoon/build/mix.wav --fps 30 --out out/faida-cartoon.mp4
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdirSync, existsSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
};
const fps = Number(arg("fps", 60));
const out = path.resolve(here, arg("out", "out/faida-promo.mp4"));
const stills = arg("stills", null);
const music = path.resolve(here, arg("audio", "out/music.wav"));
const pageFile = path.resolve(here, arg("page", "index.html"));

mkdirSync(path.join(here, "out/frames"), { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(pathToFileURL(pageFile).href);
await page.evaluate(() => window.ready);
const duration = await page.evaluate(() => window.DURATION);

const shot = async (t) => {
  await page.evaluate((t) => window.renderFrame(t), t);
  return page.screenshot({ type: "png" });
};

if (stills) {
  for (const t of stills.split(",").map(Number)) {
    const file = path.join(here, `out/frames/still-${t.toFixed(2)}.png`);
    await page.evaluate((t) => window.renderFrame(t), t);
    await page.screenshot({ path: file });
    console.log(file);
  }
  await browser.close();
  process.exit(0);
}

const hasMusic = existsSync(music);
const ff = spawn("ffmpeg", [
  "-y", "-loglevel", "error",
  "-f", "image2pipe", "-framerate", String(fps), "-i", "-",
  ...(hasMusic ? ["-i", music] : []),
  "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
  "-profile:v", "high", "-tune", "animation",
  ...(hasMusic ? ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest"] : []),
  "-movflags", "+faststart", out,
], { stdio: ["pipe", "inherit", "inherit"] });
const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));

const frames = Math.round(duration * fps);
const started = Date.now();
for (let f = 0; f < frames; f++) {
  const buf = await shot(f / fps);
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
  if (f % fps === 0) process.stdout.write(`\r${(f / fps).toFixed(0)}s / ${duration}s  (${((Date.now() - started) / 1000).toFixed(0)}s elapsed)`);
}
ff.stdin.end();
await done;
await browser.close();
console.log(`\n${out}${hasMusic ? "" : "  (no soundtrack: run node music.mjs first)"}`);
