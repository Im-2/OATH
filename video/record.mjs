// Render video/src/index.html frame by frame (deterministic, 30 fps) and encode with ffmpeg.
//   node video/record.mjs                   -> video/out/oath-demo.mp4 (+ thumbnail)
//   node video/record.mjs --stills 3,15,33  -> video/out/stills/t03.00.png ... (review frames)
import { spawn } from "node:child_process";
import { mkdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "../web-reference/shots/node_modules/playwright/index.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "out");
const PAGE = pathToFileURL(join(here, "src", "index.html")).href;
const FPS = 30;
const THUMB_T = 33; // scene 5 (28-36 s), 5 s in: hash computed, card sealed, "Committed" stamp shown
mkdirSync(join(OUT, "stills"), { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
page.on("pageerror", (e) => { console.error("page error:", e.message); process.exitCode = 1; });
await page.goto(PAGE, { waitUntil: "networkidle" });
await page.evaluate(async () => {
  await document.fonts.ready;
  for (const f of ['600 80px "Space Grotesk"', '500 30px "JetBrains Mono"']) await document.fonts.load(f);
  if (!document.fonts.check('600 80px "Space Grotesk"') || !document.fonts.check('500 30px "JetBrains Mono"')) throw new Error("fonts not loaded");
});
const total = await page.evaluate(() => window.TOTAL_FRAMES);
const frame = async (n) => { await page.evaluate((i) => window.renderFrame(i), n); return page.screenshot({ type: "png" }); };

const stillsArg = process.argv.indexOf("--stills");
if (stillsArg > 0) {
  for (const s of process.argv[stillsArg + 1].split(",").map(Number)) {
    const n = Math.min(total - 1, Math.round(s * FPS));
    await page.evaluate((i) => window.renderFrame(i), n);
    await page.screenshot({ path: join(OUT, "stills", `t${s.toFixed(2).padStart(5, "0")}.png`) });
  }
  console.log("stills written to", join(OUT, "stills"));
  await browser.close();
  process.exit();
}

// thumbnail
await page.evaluate((i) => window.renderFrame(i), THUMB_T * FPS);
await page.screenshot({ path: join(OUT, "oath-demo-thumbnail.png") });

const mp4 = join(OUT, "oath-demo.mp4");
const ff = spawn("ffmpeg", [
  "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
  "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-tune", "animation", "-pix_fmt", "yuv420p",
  "-profile:v", "high", "-level", "4.1", "-r", String(FPS), "-movflags", "+faststart", mp4,
], { stdio: ["pipe", "inherit", "inherit"] });
const t0 = Date.now();
for (let n = 0; n < total; n++) {
  const png = await frame(n);
  if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once("drain", r));
  if (n % 150 === 0) console.log(`frame ${n}/${total}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
ff.stdin.end();
await new Promise((r, j) => ff.on("close", (c) => (c === 0 ? r() : j(new Error(`ffmpeg exited ${c}`)))));
await browser.close();
console.log(`wrote ${mp4}: ${(statSync(mp4).size / 1e6).toFixed(2)} MB in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
