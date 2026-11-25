'use strict';

const assert = require('node:assert/strict');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const root = path.resolve(__dirname, '..');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'algo-table-width-'));
  const probe = http.createServer();
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  const base = 'http://127.0.0.1:' + port;
  const child = spawn(process.env.ALGOARCHIVE_TEST_PYTHON || 'python', [
    '-X', 'utf8', path.join(root, 'app.py'), '--port', String(port),
    '--data-dir', path.join(temp, 'data'), '--config-path', path.join(temp, 'config.json'),
    '--no-browser',
  ], { cwd: root, windowsHide: true, stdio: 'pipe' });
  let browser;
  let logs = '';
  child.stdout.on('data', chunk => { logs += chunk; });
  child.stderr.on('data', chunk => { logs += chunk; });

  try {
    let token;
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        token = (await fetch(base).then(response => response.text()))
          .match(/name="csrf-token" content="([^"]+)"/)?.[1];
        if (token) break;
      } catch {}
      await delay(100);
    }
    assert.ok(token, logs);

    const names = ['Bomb', 'Anthem of Berland', 'Sum of Round Numbers', 'Clear And Present Dangers'];
    for (let index = 0; index < names.length; index++) {
      const response = await fetch(base + '/api/problems', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify({
          platform: 'Codeforces',
          name: names[index],
          url: 'https://codeforces.com/problemset/problem/1/' + (index + 1),
          code: 'int main() {}',
          language: 'cpp',
        }),
      });
      assert.ok(response.ok, await response.text());
    }

    browser = await chromium.launch({
      headless: true,
      ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH
        ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH }
        : { channel: 'msedge' }),
    });

    const results = [];
    for (const [width, height] of [[1953, 862], [1440, 900], [1100, 600], [390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      await page.goto(base + '/#platform/codeforces');
      await page.locator('#problem-table .table-actions').first().waitFor();
      assert.equal(await page.locator('#problem-table [data-preview-problem]').count(), 0, 'the separate preview action is absent');
      const layout = await page.locator('.table-wrap').evaluate(element => ({
        viewport: innerWidth,
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        actionsWrap: getComputedStyle(element.querySelector('.table-actions')).flexWrap,
      }));
      assert.ok(
        layout.scrollWidth <= layout.clientWidth + 1,
        width + 'x' + height + ': problem table overflows horizontally: ' + JSON.stringify(layout),
      );
      let screenshot;
      if (width === 1953) {
        screenshot = path.join(os.tmpdir(), 'algo-table-after-1953.png');
        await page.screenshot({ path: screenshot });
      }
      results.push({ width, height, ...layout, ...(screenshot ? { screenshot } : {}) });
      await page.close();
    }
    console.log(JSON.stringify({ passed: true, results, browser: await browser.version() }, null, 2));
  } finally {
    await browser?.close();
    child.kill();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
