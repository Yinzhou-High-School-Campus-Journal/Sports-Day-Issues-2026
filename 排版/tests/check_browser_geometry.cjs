// 实际加载仓库字体，防止 Linux 像素微调使全角省略号占宽增加。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { launchChromium } = require('../browser.cjs');

(async () => {
  const browser = await launchChromium();
  try {
    const page = await browser.newPage();
    const font = fs.readFileSync(path.join(__dirname, '..', 'fonts', 'YZSong-400.ttf')).toString('base64');
    await page.setContent(`<style>@font-face {font-family: AuditSong; src:url(data:font/ttf;base64,${font})}</style>`);
    const widths = await page.evaluate(async () => {
      await document.fonts.load('14px AuditSong', '……');
      const context = document.createElement('canvas').getContext('2d');
      context.font = '14px AuditSong';
      return { one: context.measureText('…').width, two: context.measureText('……').width };
    });
    assert.ok(Math.abs(widths.one - 14) < 0.1, `单个省略号应约为 14 px：${widths.one}`);
    assert.ok(Math.abs(widths.two - 28) < 0.1, `一组省略号应约为 28 px：${widths.two}`);
    console.log(JSON.stringify({ browser: browser.version(), widths }, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
