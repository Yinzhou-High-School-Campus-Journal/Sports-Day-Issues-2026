// 只使用 npm ci 安装的锁定依赖；两个内页程序和封面程序共用。
const path = require('path');
function loadPlaywright() {
  const expected = require('./package.json').devDependencies.playwright;
  const packagePath = path.join(__dirname, 'node_modules/playwright/package.json');
  let actual;
  try { actual = require(packagePath).version; }
  catch (error) { throw new Error('请先在排版目录运行 npm ci，再运行 npx playwright install chromium'); }
  if (actual !== expected) {
    throw new Error('Playwright 版本应为 ' + expected + '，实际为 ' + actual + '；请运行 npm ci');
  }
  return require(path.join(__dirname, 'node_modules/playwright'));
}
module.exports = { loadPlaywright };
