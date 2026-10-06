// 用 Chromium 把 HTML 打印成 PDF：node render.cjs 输入.html 输出.pdf
const path = require('path');

function loadPlaywright() {
  const candidates = ['playwright', 'playwright-core', '/opt/node22/lib/node_modules/playwright'];
  for (const name of candidates) {
    try { return require(name); } catch (e) { /* 试下一个 */ }
  }
  throw new Error('找不到 Playwright：请先在 ' + __dirname + ' 目录运行 npm install');
}

(async () => {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    console.error('用法：node render.cjs 输入.html 输出.pdf');
    process.exit(2);
  }
  const { chromium } = loadPlaywright();
  // Use a locally installed Chromium when Playwright's browser bundle is unavailable.
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_EXECUTABLE || chromium.executablePath(),
  });
  const page = await browser.newPage();
  const missingResources = [];
  page.on('requestfailed', (request) => {
    if (['stylesheet', 'image'].includes(request.resourceType())) {
      missingResources.push(request.url());
    }
  });
  page.on('console', (msg) => console.log('[页面]', msg.text()));
  await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  if (missingResources.length) {
    await browser.close();
    throw new Error('[资源] 样式或图片未载入：' + missingResources.join('；'));
  }
  const failed = await page.evaluate(() =>
    [...document.fonts].filter((f) => f.status === 'error').map((f) => `${f.family} ${f.weight}`));
  if (failed.length) {
    await browser.close();
    throw new Error('[字体] 未载入：' + failed.join('；'));
  }
  await page.pdf({
    path: output,
    preferCSSPageSize: true,
    printBackground: true,
    outline: true,
    tagged: true,
  });
  await browser.close();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
