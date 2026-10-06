const path = require('path');
const { pathToFileURL } = require('url');
const { loadPlaywright } = require('../browser.cjs');

(async () => {
  const [input, pdf, png] = process.argv.slice(2);
  if (!input || !pdf || !png) throw new Error('用法：node render.cjs 输入.html 输出.pdf 输出.png');
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || chromium.executablePath(),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 794, height: 1123 }, deviceScaleFactor: 3.125 });
    const missing = [];
    page.on('requestfailed', request => missing.push(request.url()));
    await page.goto(pathToFileURL(path.resolve(input)).href, { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    const failed = await page.evaluate(() => [...document.fonts]
      .filter(font => font.status === 'error').map(font => font.family));
    if (missing.length || failed.length) {
      throw new Error('封面资源缺失：' + [...missing, ...failed].join('；'));
    }
    await page.pdf({ path: pdf, preferCSSPageSize: true, printBackground: true });
    await page.locator('.page').screenshot({ path: png });
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
