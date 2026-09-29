// /verify + /try: behaviour against the real notary wallet, the real API (8788) and the real sandbox model.
import { chromium } from "playwright";
const BASE = "http://localhost:3000";
const out = {};
const ok = (name, cond, extra = "") => { out[name] = !!cond; console.log(`${cond ? "PASS" : "FAIL"}  ${name} ${extra}`); };
const browser = await chromium.launch({ channel: "chrome" });
const ASK = process.argv.includes("--ask");

async function page(w, h) {
  const p = await browser.newPage({ viewport: { width: w, height: h } });
  p.errs = [];
  p.on("pageerror", (e) => p.errs.push(e.message));
  p.on("console", (m) => m.type() === "error" && !/hmr|404|429|Failed to load resource/i.test(m.text()) && p.errs.push(m.text().slice(0, 200)));
  return p;
}
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - innerWidth);

// ---------- /verify: in-browser verification from the chain (no OATH API) ----------
{
  const p = await page(1440, 900);
  const apiCalls = [];
  const rpcCalls = [];
  p.on("request", (r) => {
    if (r.url().includes("127.0.0.1:8788")) apiCalls.push(r.url());
    if (r.url().includes("solana.com")) rpcCalls.push(r.url());
  });
  await p.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  const body = await p.innerText("main");
  ok("verdict: all checks pass", body.includes("All checks pass"));
  ok("five check rows", (await p.locator("main ul li").filter({ hasText: /contiguous|match|in order|overdue/ }).count()) >= 5);
  ok("table lists seq 1 and 2", body.includes("#1") && body.includes("#2"));
  const apiBefore = apiCalls.length;
  await p.getByRole("button", { name: "Run verification in my browser" }).click();
  await p.waitForSelector("text=/Independently verified|problem\\(s\\) found|stopped:/", { timeout: 180_000 });
  const term = await p.locator("[aria-live=polite]").first().innerText();
  const result = (await p.innerText("main")).match(/Independently verified \d+\/\d+ oaths|\d+ problem\(s\) found by your browser/)?.[0];
  ok("chain run result", result === "Independently verified 2/2 oaths", `${result} · ${rpcCalls.length} RPC requests`);
  ok("chain run used no OATH API", apiCalls.slice(apiBefore).filter((u) => !u.includes("/v1/verify")).length === 0);
  ok("log shows digest matches", (term.match(/matches the commit/g) || []).length === 2);
  ok("log shows slot ordering", /commit slot 451,088,313 < swap slot 451,088,333/.test(term));
  console.log(term.split("\n").slice(0, 40).join("\n"));
  ok("verify no overflow 1440", (await overflow(p)) <= 0);
  await p.screenshot({ path: "verify-1440.png", fullPage: true });
  // row click
  await p.getByRole("link", { name: "Open Oath #2" }).first().click();
  await p.waitForURL(/\/oath\/2$/);
  ok("table row opens /oath/2", true);
  ok("verify page errors", p.errs.length === 0, p.errs.join(" | "));
  await p.close();
}

{
  const p = await page(390, 844);
  await p.goto(`${BASE}/verify`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1500);
  ok("verify no overflow 390", (await overflow(p)) <= 0);
  ok("verify mobile shows cards", await p.locator("table").isHidden());
  await p.getByRole("button", { name: "Run verification in my browser" }).click();
  await p.waitForSelector("text=/Independently verified|problem\\(s\\) found|stopped:/", { timeout: 180_000 });
  await p.screenshot({ path: "verify-390.png", fullPage: true });
  await p.close();
}

// ---------- /try: Break it ----------
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const p = await page(w, h);
  await p.goto(`${BASE}/try`, { waitUntil: "networkidle" });
  await p.waitForSelector("text=Matches what OATH committed on-chain", { timeout: 10_000 });
  ok(`${w} try untouched = ✅`, true);
  if (w === 1440) await p.screenshot({ path: "try-1440-untouched.png", fullPage: true });
  const stop = p.getByLabel("Stop (USDC per SOL)");
  const orig = await stop.inputValue();
  await stop.fill(orig.slice(0, -1) + (orig.endsWith("9") ? "8" : "9"));
  await p.waitForSelector("text=Tampered: this is not what OATH committed", { timeout: 5000 });
  ok(`${w} one-digit tamper = ❌`, (await p.innerText("main")).includes("changed"));
  // encoding-equivalent edit is still the same oath ("119.545962" -> "119.5459620")
  await stop.fill(orig + "0");
  await p.waitForSelector("text=Matches what OATH committed on-chain", { timeout: 5000 });
  ok(`${w} trailing zero encodes identically = ✅`, true);
  await p.getByRole("button", { name: "Try to fake a win" }).click();
  await p.waitForSelector("text=Tampered: this is not what OATH committed", { timeout: 5000 });
  ok(`${w} fake a win = ❌`, true);
  if (w === 1440) await p.screenshot({ path: "try-1440-tampered.png", fullPage: true });
  await p.getByRole("button", { name: "Reset" }).click();
  await p.waitForSelector("text=Matches what OATH committed on-chain", { timeout: 5000 });
  ok(`${w} reset = ✅`, true);
  await stop.fill("100");
  await p.waitForSelector("text=Tampered", { timeout: 5000 });
  ok(`${w} try no overflow`, (await overflow(p)) <= 0);
  if (w === 390) await p.screenshot({ path: "try-390-tampered.png", fullPage: true });
  ok(`${w} try page errors`, p.errs.length === 0, p.errs.join(" | "));
  await p.close();
}

// ---------- /try: Ask OATH (one real question, only with --ask) ----------
if (ASK) {
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const p = await page(w, h);
    await p.goto(`${BASE}/try`, { waitUntil: "networkidle" });
    await p.getByRole("tab", { name: /Ask OATH/ }).click();
    if (w === 1440) {
      await p.getByRole("button", { name: "Is SOL a buy right now?" }).click();
      await p.waitForSelector("text=/Stands aside|Would open a SOL\\/USDC long|OATH is resting/", { timeout: 150_000 });
      const b = await p.innerText("main");
      ok("sandbox answered", /Stands aside|Would open/.test(b), b.match(/(Stands aside|Would open a SOL\/USDC long)[\s\S]{0,300}/)?.[0]?.replace(/\n/g, " | "));
      await p.screenshot({ path: "try-1440-ask.png", fullPage: true });
    } else {
      // resting state, without spending a real question: the API is made unreachable for this page only
      await p.route("**/v1/sandbox", (r) => r.abort());
      await p.getByRole("button", { name: "Long JUP?" }).click();
      await p.waitForSelector("text=OATH is resting", { timeout: 20_000 });
      ok("resting state when API unreachable", true);
      ok("ask no overflow 390", (await overflow(p)) <= 0);
      await p.screenshot({ path: "try-390-ask-resting.png", fullPage: true });
    }
    await p.close();
  }
}

await browser.close();
const failed = Object.entries(out).filter(([, v]) => !v);
console.log(failed.length ? `\n${failed.length} FAILED` : "\nALL PASS");
