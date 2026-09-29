// Buy $OATH button, token section, footer: links, copy, mobile menu, overflow.
import { chromium } from "playwright";
const BASE = process.argv[2] || "http://localhost:3000";
const MINT = "9p6ZaMhABhGdgEmFpFBTRVwWcgMkWkiqD6hzAyoYKTvf";
const BUY = `https://clawpump.tech/tokens/${MINT}`;
const out = {};
const ok = (n, c, x = "") => { out[n] = !!c; console.log(`${c ? "PASS" : "FAIL"}  ${n} ${x}`); };
const browser = await chromium.launch({ channel: "chrome" });

for (const [w, h] of [[1440, 900], [390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, permissions: ["clipboard-read", "clipboard-write"] });
  const p = await ctx.newPage();
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  const pill = p.locator("header a", { hasText: "Buy $OATH" }).first();
  ok(`${w} nav pill`, (await pill.getAttribute("href")) === BUY && (await pill.getAttribute("target")) === "_blank" && (await pill.getAttribute("rel")) === "noopener noreferrer");
  ok(`${w} no "Verify it yourself" pill`, (await p.locator("header", { hasText: "Verify it yourself" }).count()) === 0);
  if (w >= 768) ok(`${w} Verify still in nav links`, await p.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Verify" }).isVisible());

  const sec = p.locator("#token");
  await sec.scrollIntoViewIfNeeded();
  await p.waitForTimeout(400);
  ok(`${w} token section shows full address`, (await sec.innerText()).includes(MINT));
  await sec.getByRole("button", { name: /Copy \$OATH contract address/ }).click();
  ok(`${w} copy puts the address on the clipboard`, (await p.evaluate(() => navigator.clipboard.readText())) === MINT);
  ok(`${w} section buy link`, (await sec.getByRole("link", { name: /Buy \$OATH on ClawPump/ }).getAttribute("href")) === BUY);
  await sec.screenshot({ path: `token-${w}.png` });

  const foot = p.locator("footer");
  await foot.scrollIntoViewIfNeeded();
  ok(`${w} footer address + buy link`, (await foot.innerText()).includes(MINT) && (await foot.getByRole("link", { name: /Buy \$OATH/ }).getAttribute("target")) === "_blank");
  await foot.screenshot({ path: `footer-${w}.png` });
  ok(`${w} no overflow on /`, (await p.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);

  await p.goto(BASE + "/live", { waitUntil: "networkidle" });
  ok(`${w} footer on /live`, (await p.locator("footer").innerText()).includes(MINT));
  ok(`${w} no overflow on /live`, (await p.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 0);

  if (w < 768) {
    await p.getByRole("button", { name: "Open menu" }).click();
    const dlg = p.getByRole("dialog", { name: "Menu" });
    await dlg.waitFor();
    await p.waitForTimeout(450);
    const cta = dlg.getByRole("link", { name: /Buy \$OATH/ });
    ok("menu CTA is Buy $OATH in new tab", (await cta.getAttribute("href")) === BUY && (await cta.getAttribute("target")) === "_blank");
    ok("menu still lists Verify", await dlg.getByRole("navigation").getByRole("link", { name: "Verify" }).isVisible());
    await p.screenshot({ path: "menu-390-buy.png" });
  }
  ok(`${w} no page errors`, errs.length === 0, errs.join("|"));
  await ctx.close();
}
await browser.close();
const f = Object.entries(out).filter(([, v]) => !v);
console.log(f.length ? `\n${f.length} FAILED` : "\nALL PASS");
