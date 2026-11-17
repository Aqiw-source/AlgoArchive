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
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-platform-art-"));
  const output = process.env.ALGOARCHIVE_QA_OUTPUT || temp;
  fs.mkdirSync(output, { recursive: true });
  let base = process.env.ALGOARCHIVE_QA_BASE_URL, child, browser, logs = "";
  if (!base) {
    const listener = http.createServer();
    await new Promise(resolve => listener.listen(0, "127.0.0.1", resolve));
    const port = listener.address().port;
    await new Promise(resolve => listener.close(resolve));
    base = `http://127.0.0.1:${port}/`;
    const executable = process.env.ALGOARCHIVE_QA_EXECUTABLE;
    child = spawn(executable || process.env.ALGOARCHIVE_TEST_PYTHON || "python", [...(executable ? [] : ["-X", "utf8", path.join(root, "app.py")]), "--port", String(port), "--data-dir", path.join(temp, "中文 题库"), "--config-path", path.join(temp, "配置.json"), "--no-browser"], { cwd: root, windowsHide: true, stdio: "pipe" });
    child.stdout.on("data", b => { logs += b; }); child.stderr.on("data", b => { logs += b; });
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(base)).ok) break; } catch (_) {}
      await delay(100);
    }
  }
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : { channel: "msedge" }) });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error" && !/503/.test(m.text())) errors.push(m.text()); });
    page.on("dialog", d => d.accept());
    await page.goto(base + "#home");
    await page.locator("#main h1").waitFor();
    assert.match(await page.title(), /算法档案|AlgoArchive/);
    assert.equal(await page.locator('.workspace-nav a[href^="#platform/"]').count(), 5);
    assert.equal(await page.locator('.workspace-nav a[href="#platform/leetcode"], .workspace-nav a[href="#platform/poj"]').count(), 0);
    assert.equal(await page.locator("[data-sidebar-art-step]").count(), 2, "two manual artwork arrows");
    const linked = await page.evaluate(async () => {
      const token = document.querySelector('meta[name="csrf-token"]').content;
      const send = async (route,body) => {
        const response = await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});
        if(!response.ok)throw new Error(await response.text());
        return response.json();
      };
      const {contest} = await send('/api/contests',{platform:'Codeforces',title:'Platform identity regression',url:'https://example.com/platform229'});
      const {problem} = await send('/api/problems',{platform:'Codeforces',name:'Keep contest association',url:'https://example.com/platform229/a',contest_id:contest.id,language:'cpp',code:'int main(){}\n'});
      return {contest,problem};
    });
    await page.goto(base+'#problem/'+linked.problem.id);
    await page.locator('#editor-platform').click();
    await page.locator('[data-platform-value="Codeforces"]').click();
    assert.equal(await page.locator('#editor-contest').inputValue(),linked.contest.id,"choosing the current platform must preserve its contest association");
    assert.equal(await page.locator('#save-state').evaluate(el=>el.classList.contains('saved')),true);
    await page.goto(base+'#home');
    await page.locator('#main h1').waitFor();
    if(child){
      let releasePut,releaseSettings,capturedSettings;
      const putGate=new Promise(resolve=>{releasePut=resolve;});
      const settingsGate=new Promise(resolve=>{releaseSettings=resolve;});
      const settingsCaptured=new Promise(resolve=>{capturedSettings=resolve;});
      await page.route('**/api/settings/sidebar-art',async route=>{await putGate;await route.continue();});
      await page.route('**/api/settings',async route=>{
        const response=await route.fetch();capturedSettings();await settingsGate;await route.fulfill({response});
      });
      try{
        await page.locator('[data-sidebar-art-step="1"]').click();
        await page.waitForFunction(()=>document.querySelector('[data-sidebar-art-step]').disabled);
        await page.locator('#open-profile-settings').click();
        let timer;
        try{await Promise.race([settingsCaptured,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Settings response was not captured')),5000);})]);}
        finally{clearTimeout(timer);}
        releasePut();
        await page.waitForFunction(()=>document.querySelector('.sidebar-art img').dataset.artImage==='debug'&&!document.querySelector('[data-sidebar-art-step]').disabled);
        releaseSettings();
        await page.locator('[data-settings-tab="art"]').click();
        assert.equal(await page.locator('.sidebar-art img').getAttribute('data-art-image'),'debug','an older settings GET must not overwrite a completed artwork save');
        assert.equal(await page.locator('#sidebar-art-settings input[value="debug"]').isChecked(),true);
        await page.locator('[data-reset-sidebar-art]').click();
        await page.waitForFunction(()=>document.querySelector('.sidebar-art img').dataset.artImage==='celebration');
        await page.locator('[data-close-modal]').click();
      }finally{
        releasePut();releaseSettings();
        await page.unroute('**/api/settings/sidebar-art');await page.unroute('**/api/settings');
      }
    }

    const artwork = page.locator(".sidebar-art img");
    const checkImage = async image => {
      await page.waitForFunction(() => [...document.querySelectorAll(".sidebar-art img")].every(el => el.complete && el.naturalWidth > 0));
      assert.equal(await artwork.getAttribute("data-art-image"), image);
      assert.equal(await artwork.evaluate(el => el.naturalWidth > 0), true);
    };
    await checkImage("celebration");
    for (const image of ["debug", "thinking", "celebration"]) {
      await page.locator('[data-sidebar-art-step="1"]').click();
      await page.waitForFunction(image => document.querySelector(".sidebar-art img").dataset.artImage === image, image);
      await checkImage(image);
    }
    await page.locator('[data-sidebar-art-step="-1"]').click();
    await page.waitForFunction(() => document.querySelector(".sidebar-art img").dataset.artImage === "thinking");
    await page.locator("[data-open-sidebar-art]").click();
    await page.locator(".sidebar-art-preview img").waitFor();
    assert.match(await page.locator(".sidebar-art-preview img").getAttribute("src"), /sidebar-art-thinking\.png/);
    await page.locator("[data-close-modal]").click();
    await page.locator("#open-profile-settings").click();
    await page.locator('[data-settings-tab="art"]').click();
    assert.equal(await page.locator('#sidebar-art-settings input[type="file"]').count(), 0);
    assert.equal(await page.locator('#sidebar-art-settings input[name="image"]').count(), 3);
    if(child){
      await page.route("**/api/settings/sidebar-art", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({error:"Injected artwork save failure"}) }));
      await page.locator('#sidebar-art-settings input[name="image"][value="debug"]').click();
      await page.getByText("Injected artwork save failure", {exact:true}).waitFor();
      assert.equal(await page.locator('#sidebar-art-settings input[name="image"][value="thinking"]').isChecked(), true);
      assert.equal(await artwork.getAttribute("data-art-image"), "thinking");
      await page.unroute("**/api/settings/sidebar-art");
    }
    await page.locator('#sidebar-art-settings input[name="image"][value="debug"]').check();
    await page.waitForFunction(() => document.querySelector(".sidebar-art img").dataset.artImage === "debug");
    await page.locator("#sidebar-art-hidden").check();
    await page.waitForFunction(() => document.querySelector("#sidebar-art-shell").hidden);
    assert.equal(await page.locator("#sidebar-art-shell").evaluate(el => el.getBoundingClientRect().height), 0);
    await page.screenshot({ path: path.join(output, "settings-hidden-desktop.png") });
    await page.locator("[data-close-modal]").click();

    await page.setViewportSize({width:390,height:844});
    if(!await page.locator('#open-profile-settings').isVisible()){
      console.log(JSON.stringify(await page.locator('#open-profile-settings').evaluate(el=>{
        const result=[];for(let node=el;node;node=node.parentElement){const r=node.getBoundingClientRect(),s=getComputedStyle(node);result.push({tag:node.tagName,class:node.className,rect:{x:r.x,y:r.y,width:r.width,height:r.height},display:s.display,visibility:s.visibility,flex:s.flex,overflow:s.overflow});}return result;
      })));
      await page.screenshot({path:path.join(output,'hidden-mobile-diagnostic.png')});
    }
    await page.locator("#open-profile-settings").click();
    await page.locator('[data-settings-tab="art"]').click();
    await page.screenshot({path:path.join(output,"art-settings-mobile.png")});
    assert.equal(await page.evaluate(() => document.querySelector('#sidebar-art-settings').scrollWidth > document.querySelector('#sidebar-art-settings').clientWidth), false);
    await page.locator("[data-close-modal]").click();
    if (child) {
      await page.reload();
      await page.locator("#main h1").waitFor();
      assert.equal(await page.locator("#sidebar-art-shell").isHidden(), true, "hide persists after reload");
    }
    await page.locator("#open-profile-settings").click();
    await page.locator('[data-settings-tab="art"]').click();
    await page.locator("[data-reset-sidebar-art]").click();
    await page.waitForFunction(() => !document.querySelector("#sidebar-art-shell").hidden && document.querySelector(".sidebar-art img").dataset.artImage === "celebration");
    await page.locator("[data-close-modal]").click();

    for (const [kind, width, height] of [["problem", 1440, 1000], ["contest", 1440, 1000], ["problem", 390, 844], ["contest", 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.goto(base + (kind === "problem" ? "#new-problem" : "#contests"));
      if (kind === "contest") await page.locator("[data-new-contest]").first().click();
      const input = page.locator(kind === "problem" ? "#editor-platform" : "#contest-form-platform");
      await input.waitFor();
      await input.click();
      assert.equal(await input.getAttribute("role"), "combobox");
      const picker = page.locator('.platform-picker').filter({has:input});
      assert.equal(await picker.locator('[role="option"]').count(), 10);
      await page.waitForFunction(() => [...document.querySelectorAll('.platform-picker [role="option"] img')].every(el => el.complete && el.naturalWidth > 0));
      assert.equal(await picker.locator('.platform-mark').first().evaluate(el=>getComputedStyle(el).boxShadow), "none", "official icons must not receive the old green inset fill");
      await input.fill("leet");
      assert.equal(await picker.locator('[role="option"]:visible').count(), 1);
      await input.press("ArrowDown");
      await input.press("Enter");
      assert.equal(await input.inputValue(), "力扣");
      assert.equal(await input.getAttribute("aria-expanded"), "false");
      await picker.locator("[data-toggle-platforms]").click();
      await picker.locator('[role="option"][data-platform-value="POJ"]').click();
      assert.equal(await input.inputValue(), "POJ");
      await input.fill("自定义练习平台");
      await input.press("Tab");
      assert.equal(await input.inputValue(), "自定义练习平台");
      await input.click();
      await input.fill("力扣");
      await page.screenshot({ path: path.join(output, `platform-${kind}-${width}.png`) });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (kind === "contest") await page.locator("[data-close-modal]").first().click();
    }
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, url: base, viewports: ["1440x1000", "390x844"], output, browser: { version: browser.version(), executable: process.env.PLAYWRIGHT_EXECUTABLE_PATH || "msedge" } }));
  } finally {
    await browser?.close();
    if(child){
      try{
        const health=await fetch(base+'api/health',{signal:AbortSignal.timeout(3000)}).then(response=>response.json());
        if(path.resolve(health.data_dir)===path.join(temp,'中文 题库')){
          const html=await fetch(base,{signal:AbortSignal.timeout(3000)}).then(response=>response.text());
          const token=html.match(/name="csrf-token" content="([^"]+)"/)?.[1];
          if(token)await fetch(base+'api/shutdown',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token,Origin:new URL(base).origin},body:'{}',signal:AbortSignal.timeout(3000)});
          for(let i=0;i<40;i++){
            try{await fetch(base+'api/health',{signal:AbortSignal.timeout(500)});}
            catch(_){break;}
            await delay(100);
          }
        }
      }catch(_){ }
    }
    if (child && child.exitCode === null) {
      child.kill();
      await new Promise(resolve => child.once("exit", resolve));
    }
  }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
