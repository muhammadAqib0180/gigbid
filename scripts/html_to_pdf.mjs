// Print report/REPORT.html to PDF with the Chromium that the web app's Playwright already installed.
//   node scripts/html_to_pdf.mjs report/REPORT.html report/GigBid_RD_Report.pdf
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import path from "node:path";

const require = createRequire(path.resolve("apps/web/package.json"));
const { chromium } = require("playwright");
const [src, out] = process.argv.slice(2);
// Prefer the installed Edge/Chrome (no download); fall back to Playwright's own Chromium.
let browser;
for (const opts of [{ channel: "msedge" }, { channel: "chrome" }, {}]) {
  try { browser = await chromium.launch(opts); break; } catch { /* try the next */ }
}
if (!browser) throw new Error("no Chromium-based browser found (install Edge or run: cd apps/web && npx playwright install chromium)");
const page = await browser.newPage();
await page.goto(pathToFileURL(path.resolve(src)).href, { waitUntil: "load" });
await page.pdf({
  path: out, format: "A4", printBackground: true,
  margin: { top: "14mm", bottom: "16mm", left: "15mm", right: "15mm" },
  displayHeaderFooter: true, headerTemplate: "<span></span>",
  footerTemplate: '<div style="font-size:7.5px;width:100%;text-align:center;color:#666;font-family:Helvetica,Arial,sans-serif">GigBid - AI-4016 R&amp;D report - page <span class="pageNumber"></span> of <span class="totalPages"></span></div>',
});
await browser.close();
console.log("wrote", out);
