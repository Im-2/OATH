// Print the in-browser chain verification log from a deployed /verify page, plus any non-200 RPC replies.
import { chromium } from "playwright";
const BASE = process.argv[2] || "https://oathagent.vercel.app";
const b = await chromium.launch({ channel: "chrome" });
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
const t0 = Date.now();
p.on("response", (r) => {
  const u = r.url();
  if ((u.includes("publicnode") || u.includes("mainnet-beta")) && r.status() !== 200) console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s RPC ${r.status()} ${new URL(u).host}`);
});
p.on("requestfailed", (r) => {
  if (r.url().includes("publicnode") || r.url().includes("mainnet-beta")) console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s RPC FAILED ${r.failure()?.errorText}`);
});
await p.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
await p.getByRole("button", { name: "Run verification in my browser" }).click();
const term = p.locator("[aria-live=polite]").first();
for (let i = 0; i < 60; i++) {
  await p.waitForTimeout(5000);
  const txt = await term.innerText();
  if (/PASS: independently|FAIL: \d|stopped:/.test(txt)) break;
}
console.log((await term.innerText()).split("\n").filter((l) => !/^\s*slot \d+/.test(l)).join("\n"));
console.log("result:", (await p.innerText("main")).match(/Independently verified \d+\/\d+ oaths|\d+ problem\(s\) found by your browser/)?.[0]);
await b.close();
