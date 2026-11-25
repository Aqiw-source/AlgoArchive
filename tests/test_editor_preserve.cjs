"use strict";
const assert=require("node:assert/strict"),fs=require("node:fs"),os=require("node:os"),path=require("node:path"),http=require("node:http");
const {spawn}=require("node:child_process"),{chromium}=require("playwright");
const root=path.resolve(process.env.ALGOARCHIVE_QA_ROOT||path.join(__dirname,"..")),wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),"algo-editor-preserve-"));
 const probe=http.createServer();await new Promise(resolve=>probe.listen(0,"127.0.0.1",resolve));const port=probe.address().port;await new Promise(resolve=>probe.close(resolve));
 const base="http://127.0.0.1:"+port,child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||"python",["-X","utf8",path.join(root,"app.py"),"--port",String(port),"--data-dir",path.join(temp,"data"),"--config-path",path.join(temp,"config.json"),"--no-browser"],{cwd:root,windowsHide:true,stdio:"pipe"});
 let logs="",browser;child.stdout.on("data",b=>logs+=b);child.stderr.on("data",b=>logs+=b);
 try{
  let token;for(let i=0;i<100;i++){try{token=(await fetch(base+"/").then(r=>r.text()).catch(()=>"\u0000")).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch{}await wait(100);}assert.ok(token,logs);
  const api=async(route,method,data)=>{const r=await fetch(base+route,{method,headers:{"Content-Type":"application/json","X-CSRF-Token":token,Origin:base},body:data?JSON.stringify(data):undefined});const value=await r.json();assert.ok(r.ok,route+": "+r.status+" "+JSON.stringify(value));return value;};
  const seeded=(await api("/api/problems","POST",{platform:"Codeforces",name:"Save stays in place",url:"https://example.com/save",language:"cpp",code:"#include <iostream>\nint main(){return 0;}\n",tests:[{input:"first",output:"one"},{input:"second",output:"two"},{input:"third",output:"three"}]})).problem;
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:"msedge"})});
  const page=await browser.newPage({viewport:{width:1100,height:900}});page.setDefaultTimeout(10000);const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.route("**/api/problems/"+seeded.id+"/run",route=>route.fulfill({status:200,contentType:"application/json",body:JSON.stringify({ok:true,compile:{status:"success",elapsed_ms:1,stdout:"",stderr:"",stdout_truncated:false,stderr_truncated:false},elapsed_ms:3,cancelled:false,cases:[1,2,3].map(ordinal=>({ordinal,status:"passed",input:["first","second","third"][ordinal-1],expected:["one","two","three"][ordinal-1],stdout:["one","two","three"][ordinal-1]+"\n",stderr:"",return_code:0,elapsed_ms:1,stdout_truncated:false,stderr_truncated:false}))})}));
  await page.goto(base+"/#problem/"+seeded.id);const editor=page.locator("#code-input");await editor.waitFor();const source=Array.from({length:110},(_,i)=>"// line "+(i+1)).join("\n")+"\n";
  await editor.fill(source);await page.locator('[data-cph-case="2"]').click();await page.locator("[data-run-cph-all]").click();await page.locator('.cph-case-tab[data-cph-case="2"].has-passed').waitFor();
  await page.evaluate(()=>window.__editorPreserveNode=document.querySelector("#code-input"));await editor.evaluate(el=>{el.focus();el.setSelectionRange(71,71);el.scrollTop=el.scrollHeight*.48;});
  const before=await editor.evaluate(el=>({start:el.selectionStart,end:el.selectionEnd,top:el.scrollTop,left:el.scrollLeft}));
  await editor.press("Control+S");await page.getByText("题目、代码与测试用例已保存。",{exact:true}).waitFor();
  const after=await editor.evaluate(el=>({same:el===window.__editorPreserveNode,start:el.selectionStart,end:el.selectionEnd,top:el.scrollTop,left:el.scrollLeft,active:document.activeElement===el,code:el.value}));
  assert.equal(after.same,true,"Ctrl+S must not replace the editor");assert.equal(after.start,before.start,"preserve caret");assert.equal(after.end,before.end,"preserve selection");assert.equal(after.top,before.top,"preserve code scroll");assert.equal(after.left,before.left,"preserve horizontal scroll");assert.equal(after.active,true,"keep typing focus");assert.equal(after.code,source);
  assert.equal(await page.locator(".cph-case-tab.active").getAttribute("data-cph-case"),"2","preserve test case 3");assert.equal(await page.locator('.cph-case-tab[data-cph-case="2"].has-passed').count(),1,"preserve run result");
  await editor.pressSequentially("// typed after save");assert.equal(await editor.inputValue(),source.slice(0,before.start)+"// typed after save"+source.slice(before.start),"typing resumes at the previous caret");
  await page.locator("#cph-input").fill("updated third input");assert.equal(await page.locator(".cph-case-tab.has-stale").count(),3,"test edit invalidates all previous results");
  await editor.press("End");await editor.pressSequentially(" code changed");assert.equal(await page.locator(".cph-case-tab.has-stale").count(),3,"code edit marks previous results stale");
  let releaseSave,markSaveStarted;
  const saveStarted=new Promise(resolve=>{markSaveStarted=resolve;}),saveGate=new Promise(resolve=>{releaseSave=resolve;});
  const problemPath="**/api/problems/"+seeded.id;
  await page.route(problemPath,async route=>{if(route.request().method()==="PUT"){markSaveStarted();await saveGate;}await route.continue();});
  await page.locator("#save-problem").click();await saveStarted;
  await editor.pressSequentially(" code typed during request");await page.locator("#cph-input").pressSequentially(" more");
  releaseSave();await page.getByText("题目、代码与测试用例已保存。",{exact:true}).last().waitFor();
  assert.match(await page.locator("#save-state").innerText(),/有未保存的修改/,"typing during an in-flight save remains dirty");
  assert.equal(await page.locator(".cph-case-tab.has-stale").count(),3,"saving does not make old results current");
  await page.unroute(problemPath);
  const secondSave=page.waitForResponse(response=>response.url().endsWith("/api/problems/"+seeded.id)&&response.request().method()==="PUT"&&response.ok());
  await page.locator("#save-problem").click();await secondSave;
  await page.waitForFunction(()=>document.querySelector("#save-state")?.textContent==="✓ 已保存到本地");
  assert.equal(await page.locator("#save-state").innerText(),"✓ 已保存到本地","a second save persists the newer edits");
  await page.goto(base+"/#new-problem");const fresh=page.locator("#code-input");await fresh.waitFor();
  await page.locator("#editor-platform").fill("Codeforces");await page.locator('[name="name"]').fill("First save remains editable");await page.locator('[name="url"]').fill("https://example.com/first-save");await fresh.fill("int main(){return 0;}\n");
  await page.evaluate(()=>window.__firstSaveNode=document.querySelector("#code-input"));await fresh.evaluate(el=>{el.focus();el.setSelectionRange(5,5);});
  const firstSave=page.waitForResponse(response=>response.url()===base+"/api/problems"&&response.request().method()==="POST"&&response.ok());
  await fresh.press("Control+S");await firstSave;
  await page.waitForFunction(()=>document.querySelector("#save-state")?.textContent==="✓ 已保存到本地");assert.equal(await fresh.evaluate(el=>el===window.__firstSaveNode),true,"first save must remain in the same editor");
  assert.equal(await fresh.evaluate(el=>el.selectionStart),5,"first save preserves the caret");assert.equal(await page.locator('[data-save-cph-tests]').evaluate(e=>e.disabled),false,"first save enables case saving");assert.equal(await page.locator('[data-run-cph-all]').isEnabled(),true,"first save enables CPH runs");
  assert.deepEqual(errors,[]);console.log(JSON.stringify({preservedCaret:true,preservedScroll:true,preservedCase:"3/3",preservedResult:true,postSaveTyping:true,changedInputsMarkedStale:true,passed:true},null,2));
 }finally{
  await browser?.close();
  if(child.exitCode===null){
   const closed=new Promise(resolve=>child.once("close",resolve));
   child.kill();
   let exited=await Promise.race([closed.then(()=>true),wait(5000).then(()=>false)]);
   if(!exited){child.kill("SIGKILL");exited=await Promise.race([closed.then(()=>true),wait(3000).then(()=>false)]);}
   if(!exited)throw new Error("Local test server did not stop before temporary files were removed");
  }
  fs.writeFileSync(path.join(temp,"server.log"),logs);
  fs.rmSync(temp,{recursive:true,force:true,maxRetries:8,retryDelay:250});
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
