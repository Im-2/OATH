// Unpin / re-pin check. Nothing follows the section yet, so the TEST inserts a spacer after it.
import { chromium } from "playwright";
const browser = await chromium.launch({ channel: "chrome" });
for (const [w, h] of [[1440, 900], [390, 844]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  await page.evaluate(() => {
    const s = document.createElement("div");
    s.style.height = "1600px"; s.style.background = "#123"; s.id = "test-spacer";
    document.querySelector("#how-it-works").after(s);
  });
  const geo = await page.evaluate(() => {
    const el = document.querySelector("#how-it-works");
    return { top: el.getBoundingClientRect().top + window.scrollY, scrollable: el.offsetHeight - window.innerHeight };
  });
  const read = () => page.evaluate(() => {
    const sec = document.querySelector("#how-it-works");
    return { innerTop: Math.round(sec.firstElementChild.getBoundingClientRect().top),
             active: [...sec.querySelectorAll('[role="tab"]')].findIndex((t) => t.getAttribute("aria-selected") === "true") + 1,
             spacerTop: Math.round(document.querySelector("#test-spacer").getBoundingClientRect().top) };
  });
  const go = async (y) => { await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), y); await page.waitForTimeout(500); return read(); };
  const end = await go(geo.top + geo.scrollable);
  const past = await go(geo.top + geo.scrollable + 400);
  await page.screenshot({ path: `how-scroll-${w}-unpinned.png` });
  const back = await go(geo.top + geo.scrollable - 10);
  console.log(w, JSON.stringify({ atEnd: end, scrolled400PastEnd: past, backUp: back }));
  await page.close();
}
await browser.close();
