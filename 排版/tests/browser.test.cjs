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
test('封面及两期内页均使用共用启动入口，并用 pathToFileURL 打开文件', () => {
  for (const folder of ['第一期', '第二期', '封面']) {
    const source = fs.readFileSync(path.join(__dirname, '..', folder, 'render.cjs'), 'utf8');
    assert.match(source, /await launchChromium\(\)/);
    assert.doesNotMatch(source, /chromium\.launch\(/);
    // 'file://' 直接拼路径时，路径里的 #、?、% 会被当成锚点或查询串
    assert.match(source, /pathToFileURL\(/);
    assert.doesNotMatch(source, /'file:\/\/' \+/);
  }
});
test('Playwright 版本与锁文件比较，不受 package.json 里的版本范围写法影响', () => {
  const { loadPlaywright } = require('../browser.cjs');
  assert.equal(typeof loadPlaywright().chromium.launch, 'function');
});
