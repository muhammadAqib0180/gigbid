// Draw a Mermaid file to PNG in a headless Edge/Chromium (Playwright from apps/web; Mermaid from the jsDelivr CDN).
//   node scripts/mermaid_png.mjs docs/images/bid_graph.mmd docs/images/bid_graph.png
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const require = createRequire(path.resolve("apps/web/package.json"));
const { chromium } = require("playwright");
const [src, out] = process.argv.slice(2);
const code = fs.readFileSync(src, "utf8");

let browser;
for (const opts of [{ channel: "msedge" }, { channel: "chrome" }, {}]) {
  try { browser = await chromium.launch(opts); break; } catch { /* next */ }
}
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
await page.setContent(`<!doctype html><html><body style="margin:0;background:#fff">
  <div id="g" style="display:inline-block;padding:16px"></div>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script></body></html>`, { waitUntil: "networkidle" });
await page.evaluate(async (c) => {
  window.mermaid.initialize({ startOnLoad: false, theme: "neutral", flowchart: { curve: "linear" } });
  const { svg } = await window.mermaid.render("graph", c);
  document.getElementById("g").innerHTML = svg;
}, code);
await page.locator("#g").screenshot({ path: out });
await browser.close();
console.log("wrote", out);
