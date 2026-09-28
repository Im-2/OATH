// Scroll-driven "How it works": pinning, step/bar sync, both directions, boundaries, unpin, clicks.
import { chromium } from "playwright";
const N = 5;
const browser = await chromium.launch({ channel: "chrome" });
const results = [];

async function state(page) {
  return page.evaluate(() => {
    const sec = document.querySelector("#how-it-works");
    const inner = sec.firstElementChild;
    const tabs = [...sec.querySelectorAll('[role="tab"]')];
    const bars = tabs.map((t) => {
      const fill = t.querySelector("span > span");
      const m = getComputedStyle(fill).transform; // matrix(a, b, c, d, e, f) -> a = scaleX
      return m === "none" ? 1 : Number(m.slice(7).split(",")[0]);
    });
    return {
      pinnedTop: Math.round(inner.getBoundingClientRect().top),
      active: tabs.findIndex((t) => t.getAttribute("aria-selected") === "true") + 1,
      title: sec.querySelector("h3")?.textContent,
      bars: bars.map((b) => Math.round(b * 100) / 100),
    };
  });
}

for (const [w, h, rm] of [[1440, 900, "no-preference"], [390, 844, "no-preference"], [1440, 900, "reduce"]]) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, reducedMotion: rm });
  await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  const geo = await page.evaluate(() => {
    const el = document.querySelector("#how-it-works");
    return { top: el.getBoundingClientRect().top + window.scrollY, scrollable: el.offsetHeight - window.innerHeight };
  });
  const at = async (y, settle = 900) => {
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), y);
    await page.waitForTimeout(settle);
    return state(page);
  };
  const tag = rm === "reduce" ? `${w}-rm` : `${w}`;
  const log = { size: tag, down: [], up: [], boundaries: [], after: null, reentry: null, clicks: [] };
  // down: middle of each step
  for (let i = 0; i < N; i++) {
    const s = await at(geo.top + (geo.scrollable * (i + 0.5)) / N, rm === "reduce" ? 120 : 1100);
    log.down.push({ i: i + 1, ...s });
    await page.screenshot({ path: `how-scroll-${tag}-down-step${i + 1}.png` });
  }
  // past the end: section unpins, page continues
  log.after = await at(geo.top + geo.scrollable + h * 0.6);
  // back up: re-pins at step 5, then runs backwards
  log.reentry = await at(geo.top + geo.scrollable - 2);
  for (let i = N - 1; i >= 0; i--) {
    const s = await at(geo.top + (geo.scrollable * (i + 0.5)) / N, 700);
    log.up.push({ i: i + 1, ...s });
    if (w === 390 || i % 2 === 0) await page.screenshot({ path: `how-scroll-${tag}-up-step${i + 1}.png` });
  }
  // exact boundaries: 1px before / after each step edge
  for (let k = 1; k < N; k++) {
    const edge = geo.top + (geo.scrollable * k) / N;
    const before = await at(edge - 1, 250);
    const after = await at(edge + 1, 250);
    log.boundaries.push({ edge: k, before: { active: before.active, bars: before.bars }, after: { active: after.active, bars: after.bars } });
  }
  // clicking a label scrolls to that step (desktop labels; phone bars are the same buttons)
  await at(geo.top + 5, 400);
  for (const i of [3, 1, 4]) {
    await page.locator('#how-it-works [role="tab"]').nth(i).click();
    await page.waitForTimeout(1600);
    log.clicks.push({ clicked: i + 1, ...(await state(page)) });
  }
  if (rm === "reduce") {
    // instant swap: 60ms after crossing into step 3 the new card is already fully opaque
    await at(geo.top + (geo.scrollable * 1.5) / N, 400);
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), geo.top + (geo.scrollable * 2.5) / N);
    await page.waitForTimeout(60);
    log.instantSwap = await page.evaluate(() => {
      const stage = document.querySelectorAll("#how-it-works .absolute.inset-0.flex.items-center.justify-center");
      return [...stage].map((e) => getComputedStyle(e).opacity);
    });
  }
  results.push(log);
  await page.close();
}
await browser.close();
console.log(JSON.stringify(results, null, 1));
