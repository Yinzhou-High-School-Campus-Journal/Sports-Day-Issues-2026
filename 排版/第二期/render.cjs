// 用 Chromium 把 HTML 打印成 PDF：node render.cjs 输入.html 输出.pdf
const path = require('path');

function loadPlaywright() {
  const candidates = ['playwright', 'playwright-core', '/opt/node22/lib/node_modules/playwright'];
  for (const name of candidates) {
    try { return require(name); } catch (e) { /* 试下一个 */ }
  }
  throw new Error('找不到 Playwright：请先在 排版/ 目录运行 npm install');
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
  page.on('console', (msg) => console.log('[页面]', msg.text()));
  await page.goto('file://' + path.resolve(input), { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const failed = await page.evaluate(() =>
    [...document.fonts].filter((f) => f.status === 'error').map((f) => `${f.family} ${f.weight}`));
  if (failed.length) {
    await browser.close();
    throw new Error('[字体] 未载入：' + failed.join('；'));
  }
  // 有元素横向超出版心时，Chromium 打印会把整份文档等比缩小去适应页宽，行距就对不上网格了。
  // 按版心宽（A4 减去左右边距 = 155.6 mm）在打印样式下检查。
  await page.emulateMedia({ media: 'print' });
  await page.setViewportSize({ width: Math.round(155.6 / 25.4 * 96), height: 1000 });
  // Chromium 141 的标点挤压有个毛病：行尾「。」」这类连续标点，断行时按行尾引号可压半宽计算，
  // 画的时候却不压，字就伸出栏外半个字。哪段出现这种情况，只对这一段关掉标点挤压。
  const fixed = await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll('p, li, dd, dt')) {
      const right = el.getBoundingClientRect().right;
      const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let n, over = false;
      while (!over && (n = tw.nextNode())) {
        const rg = document.createRange();
        rg.selectNodeContents(n);
        if (![...rg.getClientRects()].some((rc) => rc.right > right + 0.5)) continue;
        // 有一行伸出去了：逐字看，行尾悬挂的空格不算
        for (let i = 0; i < n.length && !over; i++) {
          if (/\s|　/.test(n.data[i])) continue;
          rg.setStart(n, i);
          rg.setEnd(n, i + 1);
          over = rg.getBoundingClientRect().right > right + 0.5;
        }
      }
      if (over) {
        el.style.textSpacingTrim = 'space-all';
        out.push((el.textContent || '').trim().slice(0, 16));
      }
    }
    return out;
  });
  if (fixed.length) console.log('[标点] 以下段落有字伸出栏外，已单独关闭标点挤压：', fixed.join('；'));
  const wide = await page.evaluate(() => {
    const W = document.documentElement.clientWidth;
    return [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > W + 0.5)
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${el.className}「${(el.textContent || '').trim().slice(0, 20)}」`);
  });
  if (wide.length) console.log('[版心] 以下元素超出版心宽度，PDF 会被整体缩小：', wide.join('；'));
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
