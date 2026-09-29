// Smoke test of the deployed site (desktop 1440 + phone 390), real API through the tunnel.
import { chromium, devices } from "playwright";
const BASE = process.argv[2] || "https://oathagent.vercel.app";
const out = {};
const ok = (n, c, x = "") => { out[n] = !!c; console.log(`${c ? "PASS" : "FAIL"}  ${n} ${x}`); };
const browser = await chromium.launch({ channel: "chrome" });

async function run(label, ctxOpts) {
  const ctx = await browser.newContext(ctxOpts);
  const p = await ctx.newPage();
  const errs = [];
  const apiHosts = new Set();
  p.on("pageerror", (e) => errs.push(e.message));
  p.on("console", (m) => m.type() === "error" && !/Failed to load resource|favicon/i.test(m.text()) && errs.push(m.text().slice(0, 160)));
  p.on("request", (r) => r.url().includes("/v1/") && apiHosts.add(new URL(r.url()).host));
  const overflow = () => p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  const w = ctxOpts.viewport.width;

  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  await p.waitForTimeout(3000);
  const home = await p.innerText("body");
  ok(`${label} / hero stats`, /Oaths kept/i.test(home) && home.includes("100%"));
  ok(`${label} / no overflow`, (await overflow()) <= 0);
  await p.screenshot({ path: `prod-${w}-home.png` });

  await p.goto(BASE + "/live", { waitUntil: "networkidle" });
  await p.waitForFunction(() => !document.body.innerText.includes("Connecting…"), null, { timeout: 20000 });
  const live = await p.innerText("body");
  ok(`${label} /live API online (not snapshot)`, /API online|Monitor online/.test(live) && !live.includes("showing last snapshot"),
     live.match(/(API online[^\n]*|Monitor online|Offline[^\n]*)/)?.[0]);
  ok(`${label} /live tape`, live.includes("Revealed · Oath #2") && live.includes("backfilled"));
  ok(`${label} /live no overflow`, (await overflow()) <= 0);
  await p.screenshot({ path: `prod-${w}-live.png`, fullPage: true });

  if (w < 768) {
    await p.getByRole("button", { name: "Open menu" }).click();
    await p.getByRole("dialog", { name: "Menu" }).waitFor();
    await p.waitForTimeout(500);
    await p.screenshot({ path: `prod-${w}-menu.png` });
    await p.getByRole("dialog").getByRole("navigation").getByRole("link", { name: "Verify" }).click();
    await p.waitForURL(/\/verify$/);
    ok(`${label} menu → /verify`, true);
  } else {
    await p.goto(BASE + "/verify", { waitUntil: "networkidle" });
  }
  await p.waitForTimeout(1500);
  ok(`${label} /verify verdict`, (await p.innerText("main")).includes("All checks pass"));
  await p.getByRole("button", { name: "Run verification in my browser" }).click();
  await p.waitForSelector("text=/Independently verified|problem\\(s\\) found|stopped:/", { timeout: 180000 });
  const res = (await p.innerText("main")).match(/Independently verified \d+\/\d+ oaths( within reach)?|\d+ problem\(s\)[^\n]*|stopped:[^\n]*/)?.[0];
  ok(`${label} in-browser chain verify`, /^Independently verified (\d+)\/\1 oaths/.test(res ?? ""), res);
  ok(`${label} /verify no overflow`, (await overflow()) <= 0);
  await p.screenshot({ path: `prod-${w}-verify.png`, fullPage: true });

  await p.goto(BASE + "/try", { waitUntil: "networkidle" });
  await p.waitForSelector("text=Matches what OATH committed on-chain", { timeout: 20000 });
  const stop = p.getByLabel("Stop (USDC per SOL)");
  const v = await stop.inputValue();
  await stop.fill(v.slice(0, -1) + (v.endsWith("9") ? "8" : "9"));  // change the last real digit
  await p.waitForSelector("text=Tampered: this is not what OATH committed", { timeout: 5000 });
  ok(`${label} /try tamper → ❌`, true);
  await p.getByRole("button", { name: "Reset" }).click();
  await p.waitForSelector("text=Matches what OATH committed on-chain");
  ok(`${label} /try reset → ✅`, true);
  if (w >= 768) {
    await p.getByRole("tab", { name: /Ask OATH/ }).click();
    await p.getByRole("button", { name: "Is SOL a buy right now?" }).click();
    await p.waitForSelector("text=/Stands aside|Would open a SOL\\/USDC long|OATH is resting|questions per 10 minutes/", { timeout: 150000 });
    const t = await p.innerText("main");
    ok(`${label} Ask OATH answered via tunnel`, /Stands aside|Would open/.test(t), t.match(/(Stands aside|Would open a SOL\/USDC long)[^\n]*/)?.[0]);
    await p.screenshot({ path: `prod-${w}-ask.png`, fullPage: true });
  }

  await p.goto(BASE + "/oath/2", { waitUntil: "networkidle" });
  await p.waitForFunction(() => document.body.innerText.includes("Live from the OATH API"), null, { timeout: 20000 });
  await p.getByRole("button", { name: "Verify in your browser" }).click();
  await p.waitForSelector("text=Matches the on-chain commit", { timeout: 10000 });
  ok(`${label} /oath/2 verify ✅`, true);
  ok(`${label} /oath/2 no overflow`, (await overflow()) <= 0);

  ok(`${label} reads go through the site's proxy`, [...apiHosts].includes(new URL(BASE).host), [...apiHosts].join(","));
  ok(`${label} no page errors`, errs.length === 0, errs.join(" | "));
  await ctx.close();
}

await run("desktop", { viewport: { width: 1440, height: 900 } });
await run("phone", { ...devices["Pixel 7"], viewport: { width: 390, height: 844 } });
await browser.close();
const f = Object.entries(out).filter(([, v]) => !v);
console.log(f.length ? `\n${f.length} FAILED` : "\nALL PASS");
