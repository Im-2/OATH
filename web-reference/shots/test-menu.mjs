// Mobile menu: open/close, Escape, link click, scroll lock, focus, desktop hidden.
import { chromium } from "playwright";
const BASE = "http://localhost:3000";
const out = {};
const ok = (n, c, x = "") => { out[n] = !!c; console.log(`${c ? "PASS" : "FAIL"}  ${n} ${x}`); };
const browser = await chromium.launch({ channel: "chrome" });

for (const path of ["/", "/live"]) {
  const p = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  await p.goto(BASE + path, { waitUntil: "networkidle" });
  await p.waitForTimeout(800);
  const burger = p.getByRole("button", { name: "Open menu" });
  ok(`${path} hamburger visible at 390`, await burger.isVisible());
  await p.evaluate(() => window.scrollTo(0, 300));
  // click in place (a real tap would need the nav on screen; this proves the lock keeps any position)
  await p.evaluate(() => document.querySelector('[aria-label="Open menu"]').click());
  const dlg = p.getByRole("dialog", { name: "Menu" });
  await dlg.waitFor();
  await p.waitForTimeout(450);
  const names = await dlg.getByRole("navigation").getByRole("link").allInnerTexts();
  ok(`${path} menu lists all links`, ["Live", "Try", "Verify", "Performance", "Build"].every((n) => names.some((x) => x.trim() === n)), names.join(","));
  ok(`${path} CTA present`, await dlg.getByRole("link", { name: /Verify it yourself/ }).isVisible());
  ok(`${path} scroll locked`, (await p.evaluate(() => [document.body.style.position, document.body.style.top].join())) === "fixed,-300px");
  await p.mouse.wheel(0, 600);
  await p.waitForTimeout(200);
  ok(`${path} wheel can't scroll the page`, (await p.evaluate(() => document.body.getBoundingClientRect().top)) === -300);
  const box = await dlg.boundingBox();
  ok(`${path} overlay is full screen`, box && box.width >= 389 && box.height >= 843, JSON.stringify(box));
  ok(`${path} focus moved into menu`, await p.evaluate(() => document.activeElement?.getAttribute("aria-label") === "Close menu"));
  if (path === "/live") await p.screenshot({ path: "menu-390-open.png" });
  await p.keyboard.press("Escape");
  await dlg.waitFor({ state: "detached" });
  ok(`${path} Escape closes`, true);
  ok(`${path} scroll unlocked + position kept`, (await p.evaluate(() => [document.body.style.position || "static", scrollY])).join() === "static,300",
     String(await p.evaluate(() => [document.body.style.position, scrollY])));
  ok(`${path} focus back on hamburger`, await p.evaluate(() => document.activeElement?.getAttribute("aria-label") === "Open menu"));
  // link click navigates and closes
  await burger.click();
  await dlg.waitFor();
  await dlg.getByRole("navigation").getByRole("link", { name: "Try" }).click();
  await p.waitForURL(/\/try$/);
  await p.waitForTimeout(500);
  ok(`${path} link click navigates + closes`, (await p.getByRole("dialog").count()) === 0);
  ok(`${path} unlocked after navigation, new page at top`, (await p.evaluate(() => [document.body.style.position || "static", scrollY])).join() === "static,0");
  // close button
  await p.getByRole("button", { name: "Open menu" }).click();
  await p.getByRole("button", { name: "Close menu" }).click();
  await p.getByRole("dialog").waitFor({ state: "detached" });
  ok(`${path} close button closes`, true);
  ok(`${path} no errors`, errs.length === 0, errs.join("|"));
  await p.close();
}

{
  const p = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await p.goto(BASE + "/live", { waitUntil: "networkidle" });
  ok("1440 hamburger hidden", !(await p.getByRole("button", { name: "Open menu" }).isVisible()));
  ok("1440 desktop links visible", await p.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Try" }).isVisible());
  await p.close();
}
{
  // opened at phone width, then the window grows past 768 -> menu closes
  const p = await browser.newPage({ viewport: { width: 500, height: 800 } });
  await p.goto(BASE + "/verify", { waitUntil: "networkidle" });
  await p.getByRole("button", { name: "Open menu" }).click();
  await p.getByRole("dialog").waitFor();
  await p.setViewportSize({ width: 1024, height: 800 });
  await p.getByRole("dialog").waitFor({ state: "detached", timeout: 3000 });
  ok("resize past 768 closes + unlocks", (await p.evaluate(() => document.body.style.position || "static")) === "static");
  await p.close();
}
{
  const p = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
  await p.goto(BASE + "/live", { waitUntil: "networkidle" });
  await p.getByRole("button", { name: "Open menu" }).click();
  await p.waitForTimeout(60);
  const op = await p.getByRole("dialog").evaluate((el) => getComputedStyle(el).opacity);
  ok("reduced motion opens instantly", Number(op) > 0.95, `opacity ${op} after 60ms`);
  await p.close();
}
await browser.close();
const f = Object.entries(out).filter(([, v]) => !v);
console.log(f.length ? `\n${f.length} FAILED` : "\nALL PASS");
