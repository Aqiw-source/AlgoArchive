"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");
const root = path.resolve(process.env.ALGOARCHIVE_QA_ROOT || path.join(__dirname, ".."));
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function main() {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-lock-qa-"));
  const listener = http.createServer();
  await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const base = `http://127.0.0.1:${port}`;
  const executable = process.env.ALGOARCHIVE_QA_EXECUTABLE;
  const child = spawn(executable || process.env.ALGOARCHIVE_TEST_PYTHON || "python", [...(executable ? [] : ["-X", "utf8", path.join(root, "app.py")]), "--port", String(port), "--data-dir", path.join(temp, "中文 题库"), "--config-path", path.join(temp, "配置.json"), "--no-browser"], { cwd: root, windowsHide: true, stdio: "pipe" });
  let logs = "", browser, token;
  child.stdout.on("data", b => { logs += b; }); child.stderr.on("data", b => { logs += b; });
  try {
    for (let i = 0; i < 100; i++) {
      try { token = (await fetch(base + "/").then(r => r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1]; if (token) break; } catch (_) {}
      await delay(100);
    }
    assert.ok(token, logs);
    async function api(route, method = "GET", body) {
      const r = await fetch(base + route, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": token, Origin: base }, body: body ? JSON.stringify(body) : undefined });
      const data = await r.json(); assert.ok(r.ok, `${route}: ${r.status} ${JSON.stringify(data)}`); return data;
    }
    const problem = (await api("/api/problems", "POST", { platform: "HDU", name: "Lock regression", url: "https://example.com/lock", language: "cpp", code: "int main(){return 0;}\n", tests: [{input:"", output:""}] })).problem;
    const algorithm = (await api("/api/algorithms", "POST", { name: "Lock templates" })).algorithm;
    const snippet = (await api(`/api/algorithms/${algorithm.id}/snippets`, "POST", { title: "Lock template", language: "cpp", code: "int main(){return 0;}\n" })).snippet;
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? {executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH} : {channel:"msedge"}) });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [], requests = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => {
      if(m.type()==="error" && !/Failed to load resource: the server responded with a status of (409|503)/.test(m.text())) errors.push(m.text());
    });
    page.on("dialog", d => d.accept());
    page.on("request", r => { if (r.method() === "PUT") requests.push({url:r.url(),body:r.postDataJSON()}); });
    const results = [];
    for (const [kind, entity, resource] of [["problem", problem, "problems"], ["snippet", snippet, "algorithm-snippets"]]) {
      await page.goto(`${base}/#${kind}/${entity.id}`);
      await page.locator("#code-input").waitFor();
      const code = `// unsaved ${kind}\nint main(){return 42;}\n`;
      await page.locator("#code-input").fill(code);
      if (kind === "problem") await page.locator("#cph-input").fill("draft test input");
      requests.length = 0;
      let releaseLock, lockStarted, lockWaitTimer;
      const lockGate = new Promise(resolve => {releaseLock=resolve;});
      const started = new Promise((resolve,reject) => {
        lockStarted=resolve;
        lockWaitTimer=setTimeout(()=>reject(new Error("Lock request was not sent within 15 seconds")),15000);
      });
      const lockURL = `**/api/${resource}/${entity.id}/code-lock`;
      await page.route(lockURL, async route => {lockStarted(); await lockGate; await route.continue();});
      try {
        await page.locator("#code-lock-toggle").click();
        await started;
        assert.equal(await page.locator("#editor-language").isDisabled(), true, "language must be frozen while the lock request is pending");
        assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), true);
      } finally { clearTimeout(lockWaitTimer); releaseLock(); }
      await page.waitForFunction(() => !document.querySelector("#code-lock-toggle").disabled);
      await page.unroute(lockURL);
      let saved = (await api(`/api/${resource}/${entity.id}`))[kind];
      assert.equal(saved.code, code, `${kind}: enabling the lock must persist the unsaved code first; requests=${JSON.stringify(requests)}`);
      assert.equal(saved.code_locked, true);
      if (kind === "problem") assert.equal(saved.tests[0].input, "draft test input");
      assert.equal(await page.locator("#code-input").inputValue(), code);
      assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), true);
      assert.equal(requests.length, 2, "draft save followed by lock");
      await page.locator(`#save-${kind}`).click();
      await page.waitForFunction(() => !document.querySelector("#save-problem, #save-snippet").disabled);
      assert.equal(await page.locator("#editor-error").textContent(), "");
      await page.locator("#code-lock-toggle").uncheck();
      await page.waitForFunction(() => !document.querySelector("#code-input").readOnly);
      const draft = code + "// validation failure\n";
      await page.locator("#code-input").fill(draft);
      const required = page.locator(kind === "problem" ? '#problem-form input[name="name"]' : '#snippet-form input[name="title"]');
      await required.fill("");
      requests.length = 0;
      await page.locator("#code-lock-toggle").click();
      await delay(250);
      saved = (await api(`/api/${resource}/${entity.id}`))[kind];
      assert.equal(saved.code_locked, false, "validation failure must not lock");
      assert.equal(requests.length, 0);
      assert.equal(await page.locator("#code-lock-toggle").isChecked(), false);
      assert.equal(await page.locator("#code-input").inputValue(), draft);
      assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), false);
      await required.fill(kind === "problem" ? "Lock regression" : "Lock template");
      const detailURL = `**/api/${resource}/${entity.id}`;
      await page.route(detailURL, route => route.request().method() === "PUT" ? route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({error:"Injected save failure"})}) : route.continue());
      await page.locator("#code-lock-toggle").click();
      await page.waitForFunction(() => document.querySelector("#editor-error").textContent.includes("Injected save failure"));
      assert.equal((await api(`/api/${resource}/${entity.id}`))[kind].code_locked, false);
      assert.equal(await page.locator("#code-input").inputValue(), draft);
      assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), false);
      assert.equal(await page.locator("#code-lock-toggle").isChecked(), false);
      await page.unroute(detailURL);
      const latest = (await api(`/api/${resource}/${entity.id}`))[kind];
      await api(`/api/${resource}/${entity.id}`, "PUT", {...latest, ...(kind === "problem" ? {name:"Other window"} : {title:"Other window"})});
      await page.locator("#code-lock-toggle").click();
      await page.waitForFunction(() => !document.querySelector("#code-lock-toggle").disabled);
      assert.equal((await api(`/api/${resource}/${entity.id}`))[kind].code_locked, false);
      assert.equal(await page.locator("#code-input").inputValue(), draft);
      assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), false);
      assert.ok(await page.locator("#editor-error").textContent());
      await page.reload(); await page.locator("#code-input").waitFor();
      const retryCode = code + "// lock request retry\n";
      await page.locator("#code-input").fill(retryCode);
      await page.route(`**/api/${resource}/${entity.id}/code-lock`, route => route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({error:"Injected lock failure"})}));
      await page.locator("#code-lock-toggle").click();
      await page.waitForFunction(() => !document.querySelector("#code-lock-toggle").disabled);
      saved = (await api(`/api/${resource}/${entity.id}`))[kind];
      assert.equal(saved.code, retryCode);
      assert.equal(saved.code_locked, false);
      assert.equal(await page.locator("#code-input").evaluate(el => el.readOnly), false);
      await page.unroute(`**/api/${resource}/${entity.id}/code-lock`);
      await page.locator("#code-lock-toggle").click();
      await page.waitForFunction(() => document.querySelector("#code-input").readOnly && !document.querySelector("#code-lock-toggle").disabled);
      assert.equal((await api(`/api/${resource}/${entity.id}`))[kind].code_locked, true);
      for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
        await page.setViewportSize(viewport);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        const output = process.env.ALGOARCHIVE_QA_ARTIFACTS || path.join(temp, "screenshots"); fs.mkdirSync(output,{recursive:true});
        await page.screenshot({path:path.join(output,`${kind}-${viewport.width}.png`)});
      }
      await page.setViewportSize({width:1440,height:1000});
      await page.locator("#code-lock-toggle").uncheck();
      await page.waitForFunction(() => !document.querySelector("#code-input").readOnly);
      if (kind === "problem") await page.locator("#cph-input").fill("tests-only draft");
      else await page.locator('#snippet-form input[name="title"]').fill("Metadata-only draft");
      await page.route("**/api/state", route => route.fulfill({status:503,contentType:"application/json",body:JSON.stringify({error:"Injected refresh failure"})}));
      await page.locator("#code-lock-toggle").click();
      await page.waitForFunction(() => document.querySelector("#code-input").readOnly && !document.querySelector("#code-lock-toggle").disabled);
      saved = (await api(`/api/${resource}/${entity.id}`))[kind];
      assert.equal(saved.code_locked, true);
      if (kind === "problem") assert.equal(saved.tests[0].input, "tests-only draft");
      else assert.equal(saved.title, "Metadata-only draft");
      await page.unroute("**/api/state");
      results.push(`${kind}: save-before-lock, subsequent save, unlock, validation failure, HTTP failure, version conflict, lock failure/retry, desktop/mobile`);
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({outcome:"PASS", results, temp}, null, 2));
  } finally {
    if (browser) await browser.close();
    if(token) {
      await fetch(base+"/api/shutdown",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":token,Origin:base},body:"{}",signal:AbortSignal.timeout(5000)}).catch(()=>{});
    }
    if (child.exitCode === null) child.kill();
    for (let i = 0; i < 30 && child.exitCode === null; i++) await delay(100);
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
