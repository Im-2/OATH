// "How it works" captures: every step at 1440 and 390, a mid-transition frame, and reduced motion.
import { chromium } from "playwright";
const browser = await chromium.launch({ channel: "chrome", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  page.on("pageerror", (e) => console.log(`[${w}] page error:`, e.message.slice(0, 200)));
  await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  const sec = page.locator("#how-it-works");
  await sec.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  const tabs = sec.getByRole("tab");
  for (let i = 0; i < 5; i++) {
    await tabs.nth(i).click();
    await page.waitForTimeout(2300);
    await sec.screenshot({ path: `how-${w}-step${i + 1}.png` });
  }
  if (w === 1440) {
    await tabs.nth(1).click();
    await page.waitForTimeout(260);
    await sec.screenshot({ path: `how-1440-transition.png` });
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(w, "horizontal overflow px:", overflow);
  await page.close();
}
// reduced motion: must not auto-advance
const rm = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
await rm.goto("http://localhost:3000", { waitUntil: "networkidle" });
await rm.locator("#how-it-works").scrollIntoViewIfNeeded();
await rm.waitForTimeout(9000);
const sel = await rm.locator('#how-it-works [role="tab"][aria-selected="true"]').innerText();
console.log("reduced motion, after 9s the selected tab is:", JSON.stringify(sel));
await browser.close();
