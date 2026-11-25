"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
  const root = path.resolve(__dirname, ".."), temp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-editor-performance-"));
  const child = spawn(process.env.ALGOARCHIVE_TEST_PYTHON || "python", ["-X", "utf8", "app.py", "--port", "0", "--data-dir", path.join(temp, "data"), "--config-path", path.join(temp, "config.json"), "--no-browser"], { cwd: root, windowsHide: true, stdio: "pipe" });
  let output = "", logs = "", browser;
  child.stdout.on("data", chunk => { output += chunk; logs += chunk; });
  child.stderr.on("data", chunk => { logs += chunk; });
  try {
    let base;
    for (let i = 0; i < 200 && child.exitCode === null; i++) {
      base = output.match(/(http:\/\/127\.0\.0\.1:\d+)\r?\n/)?.[1];
      if (base) break;
      await delay(100);
    }
    assert.ok(base, logs);
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: "msedge" }) });
    const page = await browser.newPage();
    await page.addInitScript(() => {
      const textContent = Object.getOwnPropertyDescriptor(Node.prototype, "textContent");
      Object.defineProperty(Node.prototype, "textContent", {
        configurable: true,
        get() { return textContent.get.call(this); },
        set(value) {
          if (this.nodeType === 1 && this.id === "line-numbers") window.__lineNumberWrites = (window.__lineNumberWrites || 0) + 1;
          return textContent.set.call(this, value);
        },
      });
      const getClientRects = Range.prototype.getClientRects;
      Range.prototype.getClientRects = function (...args) {
        if (window.__selectionMeasureTracking) window.__selectionMeasureCalls = (window.__selectionMeasureCalls || 0) + 1;
        return getClientRects.apply(this, args);
      };
    });
    await page.goto(base + "/#new-problem");
    const code = page.locator("#code-input");
    await code.waitFor();
    await code.fill("int main() {\n  return 0;\n}\n");
    await page.evaluate(() => { window.__lineNumberWrites = 0; });
    await code.pressSequentially("abc");
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.evaluate(() => window.__lineNumberWrites), 0, "typing on existing lines must not rewrite line numbers");
    await code.press("Enter");
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.locator("#line-numbers").innerText(), "1\n2\n3\n4\n5");
    assert.equal(await page.evaluate(() => window.__lineNumberWrites), 1, "adding a line rewrites line numbers once");

    await page.evaluate(() => {
      const area = document.querySelector("#code-input");
      area.setSelectionRange(0, 4);
      window.__selectionMeasureCalls = 0;
      window.__selectionMeasureTracking = true;
      area.dispatchEvent(new Event("input", { bubbles: true }));
      area.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true, key: "x" }));
    });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const rectReads = await page.evaluate(() => { window.__selectionMeasureTracking = false; return window.__selectionMeasureCalls; });
    assert.ok(rectReads <= 2, `one frame should measure the active selection once; range reads: ${rectReads}`);
    console.log(JSON.stringify({ passed: true, unchangedLineNumberWrites: 0, newLineNumberWrites: 1, selectionRangeReads: rectReads, browser: browser.version() }, null, 2));
  } finally {
    await browser?.close();
    child.kill();
    try { fs.rmSync(temp, { recursive: true, force: true }); } catch (_) {}
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
