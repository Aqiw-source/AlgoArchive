"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

const root = path.resolve(process.env.ALGOARCHIVE_QA_ROOT || path.join(__dirname, ".."));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const prefix = "algoarchive.problem-recovery.v1:";

async function main() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-problem-recovery-"));
  const listener = http.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const base = "http://127.0.0.1:" + port;
  const executable = process.env.ALGOARCHIVE_QA_EXECUTABLE;
  const python = executable ? [] : ["-X", "utf8", path.join(root, "app.py")];
  const child = spawn(
    executable || process.env.ALGOARCHIVE_TEST_PYTHON || "python",
    [...python, "--port", String(port), "--data-dir", path.join(temp, "isolated data"), "--config-path", path.join(temp, "config.json"), "--no-browser"],
    { cwd: root, windowsHide: true, stdio: "pipe" },
  );
  let logs = "";
  let browser;
  let context;
  let token;
  const errors = [];
  child.stdout.on("data", chunk => { logs += chunk; });
  child.stderr.on("data", chunk => { logs += chunk; });

  async function api(route, method = "GET", body) {
    const response = await fetch(base + route, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": token,
        Origin: base,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json();
    assert.ok(response.ok, route + ": " + response.status + " " + JSON.stringify(data));
    return data;
  }

  async function openProblem(page, id, options = {}) {
    page.setDefaultTimeout(10000);
    page.on("pageerror", error => errors.push(error.message));
    await page.addInitScript(fs.readFileSync(path.join(root, "web", "recovery-drafts.js"), "utf8"));
    if (options.demo) {
      // A truthy demo flag disables recovery-draft wiring in this fixture; it is not the app release version.
      await page.addInitScript(() => { window.__DEMO_VERSION__ = "test-fixture"; });
    }
    if (options.projectId) {
      await page.route("**/api/health", route => route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ app: "AlgoArchive", project_id: options.projectId }),
      }));
    }
    await page.goto(base + "/#problem/" + encodeURIComponent(id));
    await page.addStyleTag({ path: path.join(root, "web", "recovery-drafts.css") });
    await page.locator("#code-input").waitFor();
    if (!options.demo) await page.locator("#problem-recovery-panel").waitFor({state:"attached"});
    if (!options.demo) await page.locator("#editor-mistake-note").waitFor();
  }

  async function records(page) {
    return page.evaluate(keyPrefix => {
      const values = [];
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (key && key.startsWith(keyPrefix)) {
          try {
            values.push({ key, value: JSON.parse(localStorage.getItem(key)) });
          } catch (_) {}
        }
      }
      return values;
    }, prefix);
  }

  async function waitForRecordCount(page, count, projectId) {
    await page.waitForFunction(({ keyPrefix, expected, project }) => {
      const values = [];
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (!key || !key.startsWith(keyPrefix)) continue;
        try {
          const value = JSON.parse(localStorage.getItem(key));
          if (!project || value.projectId === project) values.push(value);
        } catch (_) {}
      }
      return values.length >= expected;
    }, { keyPrefix: prefix, expected: count, project: projectId });
  }

  async function waitForSave(page) {
    await page.waitForFunction(() => {
      const button = document.querySelector("#save-problem");
      return button && !button.disabled && !button.textContent.includes("正在保存");
    });
  }

  try {
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        token = (await fetch(base).then(response => response.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];
        if (token) break;
      } catch (_) {}
      await delay(100);
    }
    assert.ok(token, logs);
    assert.ok(fs.existsSync(path.join(root, "web", "recovery-drafts.js")), "the recovery module must ship with the app");

    const projectId = (await api("/api/health")).project_id;
    const created = await api("/api/problems", "POST", {
      platform: "Codeforces",
      number: "R-24",
      name: "Recovery draft regression",
      url: "https://example.com/recovery-draft",
      language: "cpp",
      code: "int main(){ return 0; }\\n",
      mistake_note: "saved note",
      tests: [{ input: "saved input", output: "saved output" }],
    });
    const problem = created.problem;
    browser = await chromium.launch({
      headless: true,
      ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: "msedge" }),
    });
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });

    const page1 = await context.newPage();
    await openProblem(page1, problem.id);
    assert.equal(await page1.locator("#problem-recovery-panel").isVisible(), false, "a clean problem opens without a recovery prompt");
    const draftA = {
      code: "// window A draft\\nint main(){ return 11; }\\n",
      input: "window A input",
      output: "window A output",
      note: "window A 错因笔记",
    };
    await page1.locator("#code-input").fill(draftA.code);
    await page1.locator("#cph-input").fill(draftA.input);
    await page1.locator("#cph-expected-output").fill(draftA.output);
    await page1.locator("#editor-mistake-note").fill(draftA.note);
    await waitForRecordCount(page1, 1, projectId);
    let projectRecords = (await records(page1)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id);
    assert.equal(projectRecords.length, 1, "one open editor owns one local snapshot");
    assert.equal(projectRecords[0].value.code, draftA.code);
    assert.equal(projectRecords[0].value.note, draftA.note);
    assert.deepEqual(projectRecords[0].value.tests, [{ input: draftA.input, output: draftA.output }]);
    assert.equal(projectRecords[0].value.baseVersion, problem.version);
    assert.ok(Number.isFinite(Date.parse(projectRecords[0].value.updatedAt)), "draft records include a usable save timestamp");
    const originalWindowId = projectRecords[0].value.windowId;

    await page1.reload();
    await page1.locator("#code-input").waitFor();
    await page1.locator("#problem-recovery-panel").waitFor({ state: "visible" });
    assert.match(await page1.locator("#problem-recovery-panel").innerText(), /草稿时间/);
    assert.equal(await page1.locator("#code-input").inputValue(), problem.code, "opening a draft never overwrites disk content before a choice");
    assert.equal(await page1.locator("#editor-mistake-note").inputValue(), "saved note");
    await page1.locator("[data-recovery-restore]").click();
    assert.equal(await page1.locator("#code-input").inputValue(), draftA.code);
    assert.equal(await page1.locator("#cph-input").inputValue(), draftA.input);
    assert.equal(await page1.locator("#cph-expected-output").inputValue(), draftA.output);
    assert.equal(await page1.locator("#editor-mistake-note").inputValue(), draftA.note);

    const otherProjectPage = await context.newPage();
    await openProblem(otherProjectPage, problem.id, { projectId: "test-project-separate" });
    assert.equal(await otherProjectPage.locator("#problem-recovery-panel").isVisible(), false, "another project identity cannot see this draft");
    await otherProjectPage.locator("#code-input").fill("// another project only\\n");
    await otherProjectPage.locator("#editor-mistake-note").fill("separate project note");
    await waitForRecordCount(otherProjectPage, 1, "test-project-separate");
    let allRecords = await records(otherProjectPage);
    const otherProjectRecord = allRecords.find(item => item.value.projectId === "test-project-separate" && item.value.problemId === problem.id);
    assert.ok(otherProjectRecord, "the project id namespaces browser storage");
    assert.notEqual(otherProjectRecord.key, projectRecords[0].key);
    assert.equal((await records(page1)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id).length, 1);

    await otherProjectPage.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key.startsWith("algoarchive.problem-recovery.v1:")) throw new DOMException("Quota exceeded", "QuotaExceededError");
        return original.call(this, key, value);
      };
    });
    await otherProjectPage.locator("#editor-mistake-note").fill("quota failure must stay visible");
    await otherProjectPage.waitForFunction(() => document.querySelector("#problem-recovery-status")?.textContent.includes("存储空间不足"));
    allRecords = await records(otherProjectPage);
    assert.equal(allRecords.find(item => item.key === otherProjectRecord.key).value.note, "separate project note", "quota failure leaves the last valid snapshot intact");

    const page2 = await context.newPage();
    await openProblem(page2, problem.id);
    const draftB = {
      code: "// window B wins disk first\\nint main(){ return 22; }\\n",
      input: "window B input",
      output: "window B output",
      note: "window B 错因笔记",
    };
    await page2.locator("#code-input").fill(draftB.code);
    await page2.locator("#cph-input").fill(draftB.input);
    await page2.locator("#cph-expected-output").fill(draftB.output);
    await page2.locator("#editor-mistake-note").fill(draftB.note);
    await waitForRecordCount(page2, 2, projectId);
    projectRecords = (await records(page2)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id);
    assert.equal(projectRecords.length, 2, "separate browser tabs never overwrite each other's recovery record");
    assert.equal(new Set(projectRecords.map(item => item.value.windowId)).size, 2);
    assert.ok(projectRecords.some(item => item.value.code === draftA.code));
    assert.ok(projectRecords.some(item => item.value.code === draftB.code));
    assert.ok(projectRecords.some(item => item.value.windowId === originalWindowId));

    await page2.locator("#save-problem").click();
    await waitForSave(page2);
    let disk = (await api("/api/problems/" + encodeURIComponent(problem.id))).problem;
    assert.equal(disk.code, draftB.code);
    assert.equal(disk.mistake_note, draftB.note);
    projectRecords = (await records(page2)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id);
    assert.equal(projectRecords.length, 1);
    assert.equal(projectRecords[0].value.code, draftA.code, "saving one window leaves the other window's draft intact");

    await page1.locator("#save-problem").click();
    await page1.waitForFunction(() => {
      const panel = document.querySelector("#problem-recovery-panel");
      return panel && panel.dataset.mode === "conflict" && !panel.hidden;
    });
    assert.equal(await page1.locator("#code-input").inputValue(), draftA.code, "a version conflict never replaces the editor automatically");
    assert.equal((await api("/api/problems/" + encodeURIComponent(problem.id))).problem.code, draftB.code, "a conflict never overwrites the server automatically");
    assert.equal(await page1.locator("[data-recovery-disk-code]").textContent(), draftB.code);
    assert.equal(await page1.locator("[data-recovery-draft-code]").textContent(), draftA.code);
    assert.equal(await page1.locator("[data-recovery-conflict-overwrite]").isVisible(), true, "overwriting requires a visible, explicit choice");
    await page1.screenshot({ path: path.join(temp, "problem-recovery-conflict.png") });
    await page1.locator("[data-recovery-conflict-overwrite]").click();
    assert.equal(await page1.locator("#problem-recovery-panel").isVisible(), false, "an explicit conflict choice dismisses the recovery prompt for the active editor");
    projectRecords = (await records(page1)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id);
    assert.equal(projectRecords.length, 1, "rebasing the editor does not duplicate the adopted recovery snapshot");
    assert.equal(projectRecords[0].value.code, draftA.code);
    assert.equal((await api("/api/problems/" + encodeURIComponent(problem.id))).problem.code, draftB.code, "choosing an editor version still does not write until Save is clicked");
    await page1.locator("#save-problem").click();
    await waitForSave(page1);
    disk = (await api("/api/problems/" + encodeURIComponent(problem.id))).problem;
    assert.equal(disk.code, draftA.code);
    assert.equal(disk.mistake_note, draftA.note);
    assert.equal((await records(page1)).filter(item => item.value.projectId === projectId && item.value.problemId === problem.id).length, 0, "successful save clears the current window's matching recovery draft");

    const demoPage = await context.newPage();
    const countBeforeDemo=(await records(page1)).length;
    await openProblem(demoPage, problem.id, { demo: true });
    assert.equal(await demoPage.locator("#editor-mistake-note").count(), 0);
    await demoPage.locator("#code-input").fill("// demo is memory-only\\n");
    await delay(700);
    assert.equal((await records(demoPage)).length, countBeforeDemo, "demo pages do not create recovery storage");

    const deleted = (await api("/api/problems", "POST", {
      platform: "Codeforces",
      name: "Deleted draft cleanup",
      url: "https://example.com/deleted-draft",
      language: "cpp",
      code: "int main(){}",
      tests: [{ input: "", output: "" }],
    })).problem;
    const deletePage = await context.newPage();
    await openProblem(deletePage, deleted.id);
    await deletePage.locator("#code-input").fill("// must be removed with its problem\\n");
    await waitForRecordCount(deletePage, 1, projectId);
    await api("/api/problems/" + encodeURIComponent(deleted.id), "DELETE", { version: deleted.version, confirmed: true });
    const cleanupPage = await context.newPage();
    await openProblem(cleanupPage, problem.id);
    await cleanupPage.waitForFunction(({ keyPrefix, deletedId }) => {
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (!key || !key.startsWith(keyPrefix)) continue;
        try {
          if (JSON.parse(localStorage.getItem(key)).problemId === deletedId) return false;
        } catch (_) {}
      }
      return true;
    }, { keyPrefix: prefix, deletedId: deleted.id });

    assert.deepEqual(errors, []);
    console.log(JSON.stringify({
      outcome: "PASS",
      checks: [
        "timestamped code, note, and tests survive reload with an explicit restore choice",
        "separate project identities use separate recovery keys",
        "storage quota failure is visible and preserves the last successful snapshot",
        "browser tabs keep independent drafts; stale-version comparison preserves both versions",
        "overwriting the server requires an explicit choice and a later Save",
        "demo mode stays memory-only",
        "deleting a problem removes its recovery snapshots",
      ],
      artifacts: temp,
    }, null, 2));
  } finally {
    if (context) await context.close();
    if (browser) await browser.close();
    if (token) {
      await fetch(base + "/api/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token, Origin: base },
        body: "{}",
        signal: AbortSignal.timeout(5000),
      }).catch(() => {});
    }
    if (child.exitCode === null) child.kill();
    for (let attempt = 0; attempt < 30 && child.exitCode === null; attempt++) await delay(100);
    fs.writeFileSync(path.join(temp, "server.log"), logs);
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
