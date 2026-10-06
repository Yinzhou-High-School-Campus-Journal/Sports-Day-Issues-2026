const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const { browserLaunchOptions } = require('../browser.cjs');

test('默认使用锁定的无头浏览器并关闭字体微调', () => {
  assert.deepEqual(browserLaunchOptions(''), {
    headless: true, args: ['--font-render-hinting=none'],
  });
});
test('显式浏览器路径不丢失字体微调参数', () => {
  const options = browserLaunchOptions('/tmp/example-chromium');
  assert.equal(options.executablePath, '/tmp/example-chromium');
  assert.deepEqual(options.args, ['--font-render-hinting=none']);
});
test('封面及两期内页均使用共用启动入口', () => {
  for (const folder of ['第一期', '第二期', '封面']) {
    const source = fs.readFileSync(path.join(__dirname, '..', folder, 'render.cjs'), 'utf8');
    assert.match(source, /await launchChromium\(\)/);
    assert.doesNotMatch(source, /chromium\.launch\(/);
  }
});
