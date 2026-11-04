import puppeteer from 'puppeteer';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outDir = path.resolve(__dirname, '..', 'docs', 'assets', 'screenshots');

if (!fs.existsSync(outDir)) {
  fs.mkdirSync(outDir, { recursive: true });
}

async function capture() {
  console.log('[screenshot-capture] Launching headless browser...');
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

    const targetUrl = 'http://127.0.0.1:8000/';
    console.log(`[screenshot-capture] Navigating to ${targetUrl}...`);
    await page.goto(targetUrl, { waitUntil: 'networkidle0', timeout: 15000 });

    // Wait for metrics overview to render
    await page.waitForSelector('.metrics-overview', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 1500));

    // 1. Dashboard Overview
    const overviewPath = path.join(outDir, 'dashboard-overview.png');
    await page.screenshot({ path: overviewPath, fullPage: false });
    console.log(`[screenshot-capture] Saved: ${overviewPath}`);

    // 2. Submission Console
    const consolePath = path.join(outDir, 'submission-console.png');
    await page.screenshot({ path: consolePath, fullPage: false });
    console.log(`[screenshot-capture] Saved: ${consolePath}`);

    // 3. Execution Explorer
    console.log('[screenshot-capture] Navigating to Execution Explorer tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.nav-btn'));
      const exp = btns.find((b) => b.textContent && b.textContent.includes('Explorer'));
      if (exp) exp.click();
    });

    await page.waitForSelector('.executions-table', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 1500));

    const explorerPath = path.join(outDir, 'execution-explorer.png');
    await page.screenshot({ path: explorerPath, fullPage: false });
    console.log(`[screenshot-capture] Saved: ${explorerPath}`);

    // 4. Execution Details Modal
    console.log('[screenshot-capture] Opening Execution Detail modal...');
    await page.click('tr.table-row');
    await page.waitForSelector('.modal-backdrop', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 1500));

    const detailsPath = path.join(outDir, 'execution-details.png');
    await page.screenshot({ path: detailsPath, fullPage: false });
    console.log(`[screenshot-capture] Saved: ${detailsPath}`);

    // Close modal
    await page.click('.modal-close-btn');
    await new Promise((r) => setTimeout(r, 800));

    // 5. System Health / Telemetry Panel
    console.log('[screenshot-capture] Navigating to Cluster Telemetry tab...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.nav-btn'));
      const sys = btns.find((b) => b.textContent && b.textContent.includes('Telemetry'));
      if (sys) sys.click();
    });

    await page.waitForSelector('.system-health-panel', { timeout: 10000 });
    await new Promise((r) => setTimeout(r, 1500));

    const healthPath = path.join(outDir, 'system-health.png');
    await page.screenshot({ path: healthPath, fullPage: false });
    console.log(`[screenshot-capture] Saved: ${healthPath}`);

    console.log('[screenshot-capture] All 5 screenshots captured successfully.');
  } finally {
    await browser.close();
  }
}

capture().catch((err) => {
  console.error('[screenshot-capture] Fatal error:', err);
  process.exit(1);
});
