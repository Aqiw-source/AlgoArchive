"use strict";
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { buildDemo } = require("./build-demo.cjs");
const { createFixture } = require("../demo/fixture.cjs");

async function main() {
  const site = fs.mkdtempSync(path.join(os.tmpdir(), "algo-readme-demo-"));
  buildDemo(site);
  const screenshots = path.resolve(__dirname, "..", "docs", "screenshots");
  const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png", ".webp": "image/webp", ".ico": "image/x-icon" };
  const server = http.createServer((req, res) => {
    const pathname = decodeURIComponent(new URL(req.url, "http://localhost").pathname);
    const target = path.resolve(site, pathname.replace(/^\/AlgoArchive\//, "") || "index.html");
    if (!pathname.startsWith("/AlgoArchive/") || !target.startsWith(site + path.sep) || !fs.existsSync(target) || !fs.statSync(target).isFile()) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "Content-Type": types[path.extname(target)] || "application/octet-stream" });
    fs.createReadStream(target).pipe(res);
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}/AlgoArchive/`;
  let browser;
  const errors = [], files = [], requests = [];
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe" });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ["clipboard-read", "clipboard-write"] });
    const page = await context.newPage();
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    page.on("response", r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
    page.on("request", r => requests.push(r.url()));
    await page.goto(base, { waitUntil: "networkidle" });
    // Never seed or capture a user's running local service.
    await page.locator(".demo-notice").waitFor();
    assert.equal(await page.locator('meta[name="csrf-token"]').getAttribute("content"), "isolated-online-demo");
    const fixture = createFixture();
    const feature = fixture.problems.find(p => p.number === "P3374");
    const capture = async (route, selector, filename) => {
      await page.goto(base + "#" + route);
      await page.locator(selector).first().waitFor();
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() => Array.from(document.images).every(img => img.complete && img.naturalWidth));
      await page.screenshot({ path: path.join(screenshots, filename) }); files.push(filename);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `Overflow: ${route}`);
      assert.ok(await page.evaluate(() => document.querySelector('.sidebar-identity').getBoundingClientRect().top >= document.querySelector('.demo-notice').getBoundingClientRect().bottom - 1), `Notice overlaps sidebar: ${route}`);
    };
    await capture("home", ".stats-grid", "dashboard.png");
    assert.equal(await page.locator('.workspace-nav a[data-nav^="platform/"]').count(), 5);
    assert.equal(await page.locator("#nav-problems").textContent(), String(fixture.problems.length));
    await capture("contests", ".contest-card", "contests.png");
    await capture("platform/codeforces", ".platform-page", "codeforces-workspace.png");
    await capture("contest/lanqiao-2024-national", ".problem-table", "lanqiao-contest.png");
    assert.ok((await page.locator("#main").textContent()).includes("国赛"));
    await capture("algorithm/a-fenwick", ".algorithm-info", "algorithm.png");
    await capture("algorithms", ".algorithm-card", "templates.png");
    await capture(`problem/${feature.id}`, "#code-input", "editor.png");
    const area = page.locator("#code-input");
    const original = await area.inputValue();
    const draft = original + "\n// session edit";
    await area.fill(draft);
    await page.locator("#save-problem").click();
    await page.getByText("题目、代码与测试用例已保存，所有页面已同步。", { exact: true }).waitFor();
    await page.locator("#code-lock-toggle").check();
    await page.waitForFunction(() => document.querySelector("#code-input").readOnly);
    await page.locator("[data-select-code]").click();
    assert.ok(await area.evaluate(e => e.selectionEnd === e.value.length));
    await page.locator("[data-copy-code]").click();
    assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n"), draft);
    await page.reload(); await area.waitFor();
    assert.equal(await area.inputValue(), original);
    assert.equal(await page.locator("#code-lock-toggle").isChecked(), false);
    await page.goto(base + "#problems");
    await page.locator(`[data-problem-preview="${feature.id}"]`).click({ position: { x: 10, y: 10 } });
    await page.locator(".preview-code").waitFor();
    await page.locator("[data-select-preview-code]").click();
    assert.equal(await page.evaluate(() => getSelection().toString()), original.replace(/\n$/, ""));
    await page.screenshot({ path: path.join(screenshots, "preview.png") }); files.push("preview.png");
    await page.locator("[data-close-modal]").first().click();
    await page.locator("#open-profile-settings").click();
    await page.locator('[data-settings-tab="about"]').click();
    await page.locator("#create-desktop-shortcut").click();
    await page.getByText("在线演示不执行此操作，请下载本地版使用。", { exact: true }).last().waitFor();
    await page.screenshot({ path: path.join(screenshots, "settings.png") }); files.push("settings.png");
    await page.locator("[data-close-modal]").first().click();
    await page.locator(".toast").last().waitFor({ state: "detached" });
    await page.setViewportSize({ width: 390, height: 844 });
    await capture("home", ".stats-grid", "mobile.png");
    await capture("contests", ".contest-card", "mobile-contests.png");
    await page.goto(base + `#problem/${feature.id}`); await area.waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.ok(requests.every(url => url.startsWith(base)), `Unexpected network: ${requests.filter(url => !url.startsWith(base))}`);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ base, problems: fixture.problems.length, contests: fixture.contests.length, algorithms: fixture.algorithms.length, templates: fixture.algorithms.reduce((n, a) => n + a.snippets.length, 0), files, assertions: "session edit/save/lock/copy/reset, preview selection, blocked system API, project-subpath assets, mobile overflow, no API network" }, null, 2));
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(site, { recursive: true, force: true });
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
