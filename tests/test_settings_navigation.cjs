'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { spawn } = require('node:child_process');

const root = path.resolve(process.env.ALGOARCHIVE_QA_ROOT || path.join(__dirname, '..'));
const { chromium } = require(path.join(root, '.qa-deps', 'node_modules', 'playwright'));
const { buildDemo } = require(path.join(root, 'scripts', 'build-demo.cjs'));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function startApp(temp) {
  const child = spawn(process.env.ALGOARCHIVE_TEST_PYTHON || 'python', [
    '-X', 'utf8', path.join(root, 'app.py'), '--port', '0', '--data-dir', path.join(temp, 'data'),
    '--config-path', path.join(temp, 'config.json'), '--no-browser',
  ], { cwd: root, windowsHide: true, stdio: 'pipe' });
  let output = '';
  child.stdout.on('data', chunk => { output += chunk; });
  child.stderr.on('data', chunk => { output += chunk; });
  for (let attempt = 0; attempt < 150 && child.exitCode === null; attempt++) {
    const base = output.match(/(http:\/\/127\.0\.0\.1:\d+)\r?\n/)?.[1];
    if (base) return { child, base, output: () => output };
    await pause(100);
  }
  child.kill();
  throw new Error(`Local service did not report a listening address:\n${output}`);
}

function startDemoServer(directory) {
  const hits = { api: 0 };
  const mime = { '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.png': 'image/png', '.ico': 'image/x-icon', '.txt': 'text/plain' };
  const server = http.createServer((request, response) => {
    const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    if (pathname.includes('/api/')) { hits.api++; response.writeHead(404); response.end(); return; }
    const relative = pathname.startsWith('/AlgoArchive/') ? pathname.slice('/AlgoArchive/'.length) : '';
    let file = path.resolve(directory, relative || 'index.html');
    if (file !== directory && !file.startsWith(directory + path.sep)) { response.writeHead(403); response.end(); return; }
    try {
      if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      const body = fs.readFileSync(file);
      response.writeHead(200, { 'content-type': `${mime[path.extname(file).toLowerCase()] || 'application/octet-stream'}; charset=utf-8` });
      response.end(body);
    } catch (_) { response.writeHead(404); response.end(); }
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve({ server, hits, base: `http://127.0.0.1:${server.address().port}/AlgoArchive/` })));
}

(async () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'algo-settings-navigation-'));
  const app = await startApp(temp);
  const demoDir = path.join(temp, 'demo');
  buildDemo(demoDir, '/AlgoArchive/');
  const demo = await startDemoServer(demoDir);
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: 'msedge' }) });

    const page = await browser.newPage({ viewport: { width: 1120, height: 760 } });
    const errors = [];
    let shortcutPosts = 0, compilerPosts = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/settings/desktop-shortcut', async route => {
      shortcutPosts++;
      await pause(160);
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ message: 'QA mock: shortcut created' }) });
    });
    await page.route('**/api/settings/compiler/test', async route => {
      compilerPosts++;
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ diagnostic: { ok: false, standard: 'gnu++14', checks: { __int128: false, multiset: false, unordered_map: false }, result: { status: 'compile_error', compile: { stderr: 'compiler executable could not run' } } } }) });
    });

    // Initial route, reload, selected tab, anchor focus, inner scroll and reduced motion.
    await page.goto(`${app.base}/#settings/about?focus=shortcuts`);
    await page.locator('#modal[open]').waitFor();
    assert.equal(new URL(page.url()).hash, '#settings/about?focus=shortcuts');
    assert.equal(await page.locator('[data-settings-tab="about"]').getAttribute('class').then(value => value.includes('active')), true);
    await page.locator('[data-settings-anchor="shortcuts"]').waitFor();
    await pause(150);
    const focusedElement = await page.evaluate(() => ({ tag: document.activeElement?.tagName, id: document.activeElement?.id, anchor: document.activeElement?.getAttribute('data-settings-anchor'), modal: document.querySelector('#modal').open }));
    assert.equal(focusedElement.anchor, 'shortcuts', `shortcut section receives keyboard focus: ${JSON.stringify(focusedElement)}`);
    assert.equal(await page.locator('[data-settings-anchor="shortcuts"]').evaluate(element => element.classList.contains('settings-focus-highlight')), true, 'the destination is visibly highlighted');
    const settingsContent = await page.locator('#settings-content').boundingBox();
    await page.mouse.move(settingsContent.x + settingsContent.width / 2, settingsContent.y + settingsContent.height / 2);
    await page.mouse.wheel(0, 500);
    await page.waitForFunction(() => ['#settings-content', '.settings-shell', '#modal'].some(selector => document.querySelector(selector)?.scrollTop > 0), null, { timeout: 2500 });
    const scrollers = await page.evaluate(() => ['#settings-content', '.settings-shell', '#modal'].map(selector => ({ selector, top: document.querySelector(selector)?.scrollTop || 0, height: document.querySelector(selector)?.clientHeight || 0, full: document.querySelector(selector)?.scrollHeight || 0 })));
    assert.ok(scrollers.some(item => item.top > 0), `settings content scrolls within the modal: ${JSON.stringify(scrollers)}`);
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement?.id), 'create-desktop-shortcut', 'Tab advances from the focused section to its explicit action');
    assert.equal(shortcutPosts, 0, 'opening the shortcut section does not issue a create request');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${app.base}/#settings/about?focus=shortcuts`);
    await page.locator('[data-settings-anchor="shortcuts"]').waitFor();
    assert.equal(await page.locator('[data-settings-anchor="shortcuts"]').evaluate(element => getComputedStyle(element).animationName), 'none', 'highlight animation respects reduced motion');
    await page.reload();
    await page.locator('#modal[open]').waitFor();
    assert.equal(new URL(page.url()).hash, '#settings/about?focus=shortcuts', 'refresh restores the deep-linked tab and focus target');
    await page.goBack();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).hash, '#home', 'Back from a direct settings deep link returns to the app');
    await page.goForward();
    await page.locator('#modal[open]').waitFor();
    assert.equal(new URL(page.url()).hash, '#settings/about?focus=shortcuts', 'Forward reopens the deep-linked settings section');

    // Every requested manual entry point resolves to the local app's actual settings screen.
    const manualCases = [
      ['manual.html', '#settings/about?focus=shortcuts', 'about'],
      ['shortcuts.html', '#settings/about?focus=shortcuts', 'about'],
      ['guide/backup.html', '#settings/about?focus=shortcuts', 'about'],
      ['guide/test.html', '#settings/compiler', 'compiler'],
    ];
    for (const [documentPath, hash, tab] of manualCases) {
      await page.goto(`${app.base}/${documentPath}`);
      await page.locator('[data-settings-link]').first().waitFor();
      const targetHash = await page.locator('[data-settings-link]').first().evaluate(element => new URL(element.href).hash);
      assert.equal(targetHash, hash, `${documentPath} points at the expected settings route`);
      await page.locator('[data-settings-link]').first().click();
      await page.locator('#modal[open]').waitFor();
      assert.equal(new URL(page.url()).hash, hash, `${documentPath} opens the linked settings route`);
      assert.ok(await page.locator(`[data-settings-tab="${tab}"]`).getAttribute('class').then(value => value.includes('active')));
      assert.equal(shortcutPosts, 0, 'manual deep links do not create shortcuts');
    }

    // If a locally served handbook outlives its app process, explain the fallback instead of guessing a port.
    await page.goto(`${app.base}/manual.html`);
    await page.route('**/api/health', route => route.fulfill({ status: 503, body: 'service stopped' }));
    await page.locator('[data-settings-link]').first().click();
    await page.locator('.settings-link-fallback').waitFor({ state: 'visible' });
    assert.match(await page.locator('.settings-link-fallback').innerText(), /--create-shortcut/);
    assert.equal(new URL(page.url()).pathname, '/manual.html', 'an unavailable local service leaves the handbook readable');
    assert.equal(shortcutPosts, 0, 'fallback navigation never calls shortcut creation');
    await page.unroute('**/api/health');

    // Invalid settings paths degrade to the profile tab; close is safe and leaves a valid app route.
    await page.goto(`${app.base}/#settings/no-such-tab?focus=unknown`);
    await page.locator('#modal[open]').waitFor();
    assert.equal(await page.locator('[data-settings-tab="profile"]').getAttribute('class').then(value => value.includes('active')), true);
    await page.locator('[data-close-modal]').first().click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).hash, '#home');

    // Back/forward closes and reopens the settings overlay; settings tabs themselves are history entries.
    await page.goto(`${app.base}/#home`);
    await page.locator('#open-profile-settings').click();
    await page.locator('#modal[open]').waitFor();
    assert.equal(new URL(page.url()).hash, '#settings/profile');
    await page.goBack();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).hash, '#home');
    await page.goForward();
    await page.locator('#modal[open]').waitFor();
    await page.locator('[data-settings-tab="about"]').click();
    await page.waitForFunction(() => location.hash === '#settings/about');
    await page.goBack();
    await page.waitForFunction(() => location.hash === '#settings/profile');
    assert.equal(await page.locator('[data-settings-tab="profile"]').getAttribute('class').then(value => value.includes('active')), true);
    await page.goForward();
    await page.waitForFunction(() => location.hash === '#settings/about');
    assert.equal(await page.locator('[data-settings-tab="about"]').getAttribute('class').then(value => value.includes('active')), true);
    await page.locator('[data-close-modal]').first().click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).hash, '#home', 'close collapses settings navigation back to its app route');

    // Opening settings over a dirty in-place editor does not discard the editor or prompt to leave.
    await page.goto(`${app.base}/#new-problem`);
    await page.locator('#problem-form').waitFor();
    await page.locator('#problem-form input[name="name"]').fill('Unsaved navigation sentinel');
    await page.locator('#problem-form input[name="url"]').fill('https://example.test/unsaved');
    await page.evaluate(() => {
      const link = document.createElement('a'); link.href = '#settings/compiler'; link.textContent = 'Open compiler settings';
      link.dataset.settingsLink = ''; document.querySelector('main').prepend(link);
    });
    await page.locator('[data-settings-link]').first().click();
    await page.locator('#modal[open]').waitFor();
    assert.equal(new URL(page.url()).hash, '#settings/compiler');
    assert.equal(await page.locator('#problem-form input[name="name"]').inputValue(), 'Unsaved navigation sentinel');
    await page.locator('[data-close-modal]').first().click();
    await page.locator('#modal').waitFor({ state: 'hidden' });
    assert.equal(new URL(page.url()).hash, '#new-problem');
    assert.equal(await page.locator('#problem-form input[name="name"]').inputValue(), 'Unsaved navigation sentinel');
    assert.equal(await page.locator('#problem-form input[name="url"]').inputValue(), 'https://example.test/unsaved');

    // Repeated same-frame action clicks produce one explicit shortcut/compiler probe request.
    await page.goto(`${app.base}/#settings/about?focus=shortcuts`);
    await page.locator('#create-desktop-shortcut').waitFor();
    await page.evaluate(() => { const button = document.querySelector('#create-desktop-shortcut'); button.click(); button.click(); });
    await page.locator('#shortcut-settings-status').getByText('QA mock: shortcut created').waitFor();
    assert.equal(shortcutPosts, 1, 'one intentional action produces exactly one POST');
    await page.goto(`${app.base}/#settings/compiler`);
    await page.locator('#compiler-test').click();
    await page.locator('#compiler-diagnostic pre').waitFor();
    assert.match(await page.locator('#compiler-diagnostic').innerText(), /compiler executable could not run/);
    assert.equal(compilerPosts, 1, 'the capability probe is also an explicit, single POST');

    // A slow settings request superseded by a route change must not reopen a stale modal.
    await page.goto(`${app.base}/#home`);
    let delayedSettingsGets = 0;
    await page.route('**/api/settings', async route => { delayedSettingsGets++; await pause(400); await route.continue(); });
    await page.evaluate(() => { location.hash = '#settings/compiler'; });
    await pause(50);
    await page.evaluate(() => { location.hash = '#home'; });
    await pause(600);
    assert.equal(await page.locator('#modal').evaluate(element => element.open), false, 'late settings responses do not reopen a dismissed modal');
    await page.evaluate(() => { location.hash = '#settings/compiler'; });
    await pause(50);
    await page.evaluate(() => { location.hash = '#settings/about?focus=shortcuts'; });
    await page.locator('#modal[open]').waitFor();
    await page.waitForFunction(() => document.querySelector('[data-settings-tab="about"]')?.classList.contains('active'));
    await page.waitForFunction(() => document.activeElement?.matches('[data-settings-anchor="shortcuts"]'));
    assert.equal(new URL(page.url()).hash, '#settings/about?focus=shortcuts', 'a second deep link wins while settings data is still loading');
    assert.equal(delayedSettingsGets, 2, 'changing target during one pending open reuses the in-flight settings request');
    assert.deepEqual(errors, [], 'no browser runtime errors');

    // Built demo pages resolve the same public routes; its in-memory API never reaches the local OS/server.
    const demoPage = await browser.newPage({ viewport: { width: 1120, height: 760 } });
    for (const [file, hash, tab] of manualCases) {
      await demoPage.goto(demo.base + file);
      await demoPage.locator('[data-settings-link]').first().click();
      await demoPage.locator(`#modal[open] [data-settings-tab="${tab}"].active`).waitFor();
      assert.equal(new URL(demoPage.url()).hash, hash);
      assert.equal(demo.hits.api, 0, file + ' must not probe a local service');
    }
    await demoPage.goto(`${demo.base}manual.html`);
    await demoPage.locator('[data-settings-link]').first().click();
    await demoPage.locator('#modal[open]').waitFor();
    assert.equal(new URL(demoPage.url()).hash, '#settings/about?focus=shortcuts');
    await demoPage.getByText('桌面和开始菜单快捷方式只能由 Windows 本地版创建。', { exact: false }).waitFor();
    assert.equal(await demoPage.locator('#create-desktop-shortcut').count(), 0, 'the demo does not render a local system action');
    const demoDownload = demoPage.locator('[data-settings-anchor="shortcuts"] a[href*="/releases/latest"]');
    assert.equal(await demoDownload.count(), 1, 'the demo offers the Windows release download');
    assert.equal(await demoDownload.getAttribute('target'), '_blank');
    assert.equal(await demoDownload.getAttribute('rel'), 'noopener noreferrer');
    assert.equal(demo.hits.api, 0, 'demo settings navigation makes no network/local-service request');

    // A file URL stays offline and exposes a keyboard-accessible command fallback.
    const offlinePage = await browser.newPage();
    await offlinePage.goto(pathToFileURL(path.join(root, 'web', 'guide', 'test.html')).href);
    assert.equal(new URL(offlinePage.url()).protocol, 'file:');
    assert.equal(await offlinePage.locator('body').innerText().then(text => text.includes('需先启动本地程序') || text.includes('本地版')), true);
    const offlineUrl = offlinePage.url();
    await offlinePage.locator('[data-settings-link]').click();
    assert.equal(offlinePage.url(), offlineUrl, 'file:// help does not guess a local service address');
    const offlineFallback = offlinePage.locator('.settings-link-fallback');
    await offlineFallback.waitFor({ state: 'visible' });
    assert.equal(await offlineFallback.evaluate(element => element === document.activeElement), true, 'offline fallback receives keyboard focus');
    assert.ok((await offlineFallback.innerText()).includes('.\\start.bat'));
    await offlinePage.close();

    console.log(JSON.stringify({ passed: true, app: app.base, manualEntryPoints: manualCases.map(([file]) => file), shortcutPosts, compilerPosts, demoApiNetworkRequests: demo.hits.api, browser: browser.version() }, null, 2));
  } finally {
    await browser?.close();
    app.child.kill();
    await new Promise(resolve => demo.server.close(resolve));
    await pause(300);
    try { fs.rmSync(temp, { recursive: true, force: true, maxRetries: 4, retryDelay: 250 }); } catch (_) { /* A Windows antivirus may briefly hold a QA fixture. */ }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
