// Design screenshots with real timing (animations + WebGL), using the installed Chrome.
import { chromium } from "playwright";
const sizes = [[1440, 900, "oath-1440.png"], [1024, 768, "oath-1024.png"], [390, 844, "oath-390.png"]];
const browser = await chromium.launch({ channel: "chrome", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
for (const [w, h, file] of sizes) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  page.on("console", (m) => m.type() === "error" && console.log(`[${w}] console error:`, m.text().slice(0, 200)));
  await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  await page.waitForTimeout(11000);
  await page.screenshot({ path: file });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  console.log(file, "horizontal overflow px:", overflow);
  await page.close();
}
await browser.close();
