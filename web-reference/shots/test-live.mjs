// /live + /oath/[seq]: screenshots at 1440/390 and behaviour checks against the real API (port 8788).
import { chromium } from "playwright";
const BASE = "http://localhost:3000";
const out = {};
const ok = (name, cond, extra = "") => { out[name] = !!cond; console.log(`${cond ? "PASS" : "FAIL"}  ${name} ${extra}`); };
const browser = await chromium.launch({ channel: "chrome" });

for (const [w, h] of [[1440, 900], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  const errs = [];
  page.on("pageerror", (e) => errs.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/hmr|404/i.test(m.text()) && errs.push(m.text().slice(0, 200)));

  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.body.innerText.includes("Connecting…"), null, { timeout: 15000 });
  await page.waitForTimeout(800);
  const body = await page.innerText("body");
  ok(`${w} live status`, /API online|Monitor online/.test(body), body.match(/(Monitor online|API online[^\n]*)/)?.[0]);
  ok(`${w} tape has seq1+seq2+stand-aside`, body.includes("Committed · Oath #1") && body.includes("Revealed · Oath #2") && body.includes("backfilled"));
  ok(`${w} no horizontal overflow`, (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
  await page.screenshot({ path: `live-${w}.png`, fullPage: true });
  await page.screenshot({ path: `live-${w}-fold.png` });

  // filters
  await page.getByRole("tab", { name: /Stood aside/ }).click();
  await page.waitForTimeout(700);
  ok(`${w} filter stood aside -> 1 row`, (await page.locator("ol > li").count()) === 1);
  await page.getByRole("tab", { name: /Blocked/ }).click();
  ok(`${w} filter blocked -> empty state`, (await page.innerText("body")).includes("Nothing here yet"));
  await page.getByRole("tab", { name: /^All/ }).click();

  // row click -> detail
  await page.getByRole("link", { name: "Open Oath #2" }).first().click();
  await page.waitForURL(/\/oath\/2$/);
  await page.waitForFunction(() => document.body.innerText.includes("Live from the OATH API"), null, { timeout: 15000 });
  ok(`${w} row click opens /oath/2`, true);
  ok(`${w} detail no overflow`, (await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);
  await page.getByRole("button", { name: "Verify in your browser" }).click();
  await page.waitForSelector("text=Matches the on-chain commit", { timeout: 5000 });
  ok(`${w} in-browser verify ✅`, true);
  await page.screenshot({ path: `oath2-${w}.png`, fullPage: true });
  ok(`${w} no page errors`, errs.length === 0, errs.join(" | "));
  await page.close();
}

// tampered thesis from the API -> ❌ (response modified in the test only)
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.route("**/v1/positions/2", async (route) => {
    const r = await route.fetch();
    const j = await r.json();
    j.canonical = j.canonical.replace('"stop":"119.545962"', '"stop":"119.545963"');
    await route.fulfill({ response: r, json: j });
  });
  await page.goto(`${BASE}/oath/2`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.body.innerText.includes("Live from the OATH API"));
  await page.getByRole("button", { name: "Verify in your browser" }).click();
  await page.waitForSelector("text=Does not match: tampered", { timeout: 5000 });
  ok("tampered thesis -> ❌", true);
  await page.close();
}

// API down -> offline + snapshot
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.route("**/api/oath/**", (r) => r.abort());
  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.body.innerText.includes("Connecting…"), null, { timeout: 15000 });
  const b = await page.innerText("body");
  ok("offline shows snapshot notice", b.includes("Offline — showing last snapshot from") && b.includes("Revealed · Oath #2"));
  await page.close();
}

// a new event arriving between polls slides in with a flash (first poll withholds the newest real item)
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let n = 0;
  await page.route("**/v1/live", async (route) => {
    const r = await route.fetch();
    const j = await r.json();
    if (n++ === 0) j.feed.items = j.feed.items.slice(1);
    await route.fulfill({ response: r, json: j });
  });
  await page.clock.install();
  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.body.innerText.includes("Connecting…"));
  const before = await page.locator("ol > li").count();
  await page.clock.runFor(10_500);
  await page.waitForFunction((b) => document.querySelectorAll("ol > li").length > b, before, { timeout: 8000 });
  const bg = await page.locator("ol > li").first().evaluate((el) => getComputedStyle(el).backgroundColor);
  ok("new row appears after one poll", true, `${before} -> ${await page.locator("ol > li").count()}, first-row bg ${bg}`);
  await page.close();
}

// polling pauses while hidden
{
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  let calls = 0;
  page.on("request", (r) => r.url().includes("/v1/live") && calls++);
  await page.clock.install();
  await page.goto(`${BASE}/live`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => !document.body.innerText.includes("Connecting…"));
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const c0 = calls;
  await page.clock.runFor(35_000);
  await page.waitForTimeout(500);
  ok("no polling while hidden", calls === c0, `${c0} -> ${calls}`);
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.waitForTimeout(1500);
  ok("refreshes when visible again", calls > c0, `${c0} -> ${calls}`);
  await page.close();
}

await browser.close();
const failed = Object.entries(out).filter(([, v]) => !v);
console.log(failed.length ? `\n${failed.length} FAILED` : "\nALL PASS");
