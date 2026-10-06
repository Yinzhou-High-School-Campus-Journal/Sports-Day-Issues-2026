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
// 使用锁定的 headless shell；Linux 默认 full hinting 会改变省略号的前进宽度。
// 显式指定其他浏览器时仍保留相同参数，但不承诺与归档基线完全一致。
function browserLaunchOptions(executablePath = process.env.CHROMIUM_EXECUTABLE) {
  const options = { headless: true, args: ['--font-render-hinting=none'] };
  if (executablePath) options.executablePath = executablePath;
  return options;
}
async function launchChromium() {
  return loadPlaywright().chromium.launch(browserLaunchOptions());
}
module.exports = { loadPlaywright, browserLaunchOptions, launchChromium };
