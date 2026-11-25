"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const root = path.resolve(__dirname, ".."), temp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-home-performance-"));
  const child = spawn(process.env.ALGOARCHIVE_TEST_PYTHON || "python", ["-X", "utf8", "app.py", "--port", "0", "--data-dir", path.join(temp, "data"), "--config-path", path.join(temp, "config.json"), "--no-browser"], { cwd: root, windowsHide: true, stdio: "pipe" });
  let output = "", logs = "", browser;
  child.stdout.on("data", chunk => { output += chunk; logs += chunk; });
  child.stderr.on("data", chunk => { logs += chunk; });
  try {
    let base, token;
    for (let i = 0; i < 200 && child.exitCode === null; i++) {
      base = output.match(/(http:\/\/127\.0\.0\.1:\d+)\r?\n/)?.[1];
      if (base) {
        token = (await fetch(base).then(response => response.text()).catch(() => "")).match(/name="csrf-token" content="([^"]+)"/)?.[1];
        if (token) break;
      }
      await delay(100);
    }
    assert.ok(base && token, logs);
    const api = async (route, payload) => {
      const response = await fetch(base + route, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token, Origin: base }, body: JSON.stringify(payload) });
      const body = await response.json();
      assert.ok(response.ok, route + ": " + response.status + " " + JSON.stringify(body));
      return body;
    };
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: "msedge" }) });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.goto(base + "/#home");
    await page.locator(".stats-grid").waitFor();
    assert.equal(await page.locator(".home-intro").count(), 1, "an empty library keeps the onboarding card");

    const contest = (await api("/api/contests", { title: "Home count regression", platform: "Codeforces", url: "https://example.com/contest" })).contest;
    for (const [name, platform] of [["CF A", "Codeforces"], ["CF B", "codeforces"], ["AC A", "AtCoder"]]) {
      await api("/api/problems", { name, platform, contest_id: platform.toLowerCase().includes("codeforces") ? contest.id : null, url: "https://example.com/" + encodeURIComponent(name), language: "cpp", code: "int main() {}" });
    }

    await page.reload();
    await page.locator(".stats-grid").waitFor();
    assert.equal(await page.locator(".home-intro").count(), 0, "a populated library removes the duplicate introduction card");
    const readCards = () => page.locator(".stats-grid .stat-card").evaluateAll(cards => Object.fromEntries(cards.map(card => [card.querySelector(".stat-label")?.textContent.trim(), card.querySelector(".stat-value")?.textContent.trim()])));
    let cards = await readCards();
    assert.equal(cards.Codeforces, "2");
    assert.equal(cards.AtCoder, "1");
    assert.equal(await page.locator(".contest-home-section .contest-card-bottom > span").innerText(), "2 道题目");

    const fallbackPage = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await fallbackPage.route("**/api/state", async route => {
      const response = await route.fetch();
      const body = await response.json();
      delete body.stats;
      await route.fulfill({ response, body: JSON.stringify(body) });
    });
    await fallbackPage.goto(base + "/#home");
    await fallbackPage.locator(".stats-grid").waitFor();
    cards = await fallbackPage.locator(".stats-grid .stat-card").evaluateAll(items => Object.fromEntries(items.map(card => [card.querySelector(".stat-label")?.textContent.trim(), card.querySelector(".stat-value")?.textContent.trim()])));
    assert.equal(cards.Codeforces, "2", "demo-style state without stats uses a single-pass fallback");
    assert.equal(cards.AtCoder, "1");
    console.log(JSON.stringify({ passed: true, emptyLibraryIntro: true, populatedLibraryIntro: false, platformCounts: { Codeforces: cards.Codeforces, AtCoder: cards.AtCoder }, contestCount: 2, browser: browser.version() }, null, 2));
  } finally {
    await browser?.close();
    child.kill();
    try { fs.rmSync(temp, { recursive: true, force: true }); } catch (_) {}
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
