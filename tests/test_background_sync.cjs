'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve:()=>resolve()};};
const bounded=promise=>{let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Response gate timed out')),8000);})]).finally(()=>clearTimeout(timer));};
async function main(){
  const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-background-'));
  const listener=http.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));
  const port=listener.address().port;await new Promise(r=>listener.close(r));const base=`http://127.0.0.1:${port}`;
  const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8','app.py','--port',String(port),'--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
  let browser,logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
  try{
    let token;for(let i=0;i<100;i++){try{token=(await fetch(base).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch{}await delay(100);}assert.ok(token,logs);
    const send=async(url,data)=>{const response=await fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(data)});assert.ok(response.ok,await response.clone().text());return response.json();};
    for(let i=0;i<26;i++)await send('/api/problems',{platform:'Codeforces',name:(i<25?'keep ':'other ')+i,url:'https://example.com/'+i,language:'cpp',code:''});
    for(const [title,platform] of [['keep contest','Codeforces'],['keep elsewhere','AtCoder'],['other contest','Codeforces']])await send('/api/contests',{title,platform,url:'https://example.com/'+encodeURIComponent(title)});
    for(const [name,category] of [['keep algorithm','graph'],['keep elsewhere','dp'],['other algorithm','graph']])await send('/api/algorithms',{name,category,description:''});
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
    const context=await browser.newContext({viewport:{width:1440,height:800}}),page=await context.newPage(),second=await context.newPage();
    page.setDefaultTimeout(8000);second.setDefaultTimeout(8000);const errors=[];
    for(const p of [page,second])p.on('pageerror',e=>errors.push(e.message));
    let nav=0;const go=async route=>{await page.goto(base+'/?test='+(++nav)+'#'+route);await page.locator('#main h1').waitFor();};
    await go('platform/codeforces');await second.goto(base+'/#home');await second.locator('#main h1').waitFor();
    await page.locator('#filter-query').fill('keep');await page.locator('#filter-query').evaluate(e=>{e.focus();e.setSelectionRange(1,3);window.scrollTo(0,420);});
    const scrollBefore=await page.evaluate(()=>scrollY);assert.ok(scrollBefore>0);assert.equal(await page.locator('[data-drag-algorithm-problem]').count(),0);
    const switchArt=async()=>{const before=await second.locator('.sidebar-art img').getAttribute('data-art-image');await second.locator('[data-sidebar-art-step="1"]').click();await second.waitForFunction(id=>document.querySelector('.sidebar-art img').dataset.artImage!==id,before);const selected=await second.locator('.sidebar-art img').getAttribute('data-art-image');await page.waitForFunction(id=>document.querySelector('.sidebar-art img').dataset.artImage===id,selected);};
    await switchArt();
    assert.equal(await page.locator('#filter-query').inputValue(),'keep');assert.equal(await page.locator('[data-drag-algorithm-problem]').count(),0);
    assert.equal(await page.locator('#problem-table tbody tr').count(),25);assert.equal(await page.evaluate(()=>scrollY),scrollBefore);
    assert.deepEqual(await page.locator('#filter-query').evaluate(e=>[document.activeElement===e,e.selectionStart,e.selectionEnd]),[true,1,3]);
    await second.locator('[data-new-problem]').first().click();await second.locator('[name=name]').fill('keep newly saved');await second.locator('[name=url]').fill('https://example.com/new');await second.locator('#save-problem').click();await second.waitForURL(/#problem\//);
    await page.waitForFunction(()=>document.querySelector('#nav-problems').textContent==='27');
    assert.equal(await page.locator('#filter-query').inputValue(),'keep');assert.equal(await page.locator('#problem-table tbody tr').count(),26);assert.equal(await page.locator('[data-drag-algorithm-problem]').count(),0);assert.equal(await page.evaluate(()=>scrollY),scrollBefore);
    // Editing filters during a delayed background read must preserve the latest input.
    let captured=deferred(),release=deferred(),hold=true;
    await page.route('**/api/state',async route=>{const response=await route.fetch();if(hold){hold=false;captured.resolve();await release.promise;}await route.fulfill({response});});
    const changingArt=switchArt();await bounded(captured.promise);await page.locator('#filter-query').fill('keep 1');release.resolve();await changingArt;
    assert.equal(await page.locator('#filter-query').inputValue(),'keep 1');assert.equal(await page.locator('#problem-table tbody tr').count(),11);await page.unroute('**/api/state');
    // A later navigation must not inherit an older route's query snapshot.
    captured=deferred();release=deferred();hold=true;
    await page.route('**/api/state',async route=>{const response=await route.fetch();if(hold){hold=false;captured.resolve();await release.promise;}await route.fulfill({response});});
    await second.locator('[data-sidebar-art-step="1"]').click();await bounded(captured.promise);
    await page.locator('[data-nav="contests"]').first().click();await page.locator('#contest-search').fill('keep');await page.locator('#contest-platform').selectOption('codeforces');release.resolve();await delay(150);await page.unroute('**/api/state');
    assert.match(page.url(),/#contests$/);assert.equal(await page.locator('#contest-search').inputValue(),'keep');assert.equal(await page.locator('#contest-platform').inputValue(),'codeforces');
    await switchArt();assert.equal(await page.locator('#contest-search').inputValue(),'keep');assert.equal(await page.locator('#contest-platform').inputValue(),'codeforces');assert.equal(await page.locator('#contest-list .contest-card').count(),1);
    await go('algorithms');await page.locator('#algorithm-search').fill('keep');await page.locator('#algorithm-category').selectOption('graph');await switchArt();assert.equal(await page.locator('#algorithm-search').inputValue(),'keep');assert.equal(await page.locator('#algorithm-category').inputValue(),'graph');assert.equal(await page.locator('#algorithm-list .algorithm-card').count(),1);
    await go('new-problem');await page.locator('[name=name]').fill('unsaved foreground draft');await switchArt();assert.equal(await page.locator('[name=name]').inputValue(),'unsaved foreground draft');
    assert.deepEqual(errors,[]);await page.screenshot({path:path.join(temp,'preserved-draft.png')});
    await page.locator('#open-profile-settings').click();await page.locator('[data-settings-tab="about"]').click();
    const about=await page.locator('#settings-content').innerText();
    for(const text of ['MIT','DISCLAIMER.md','平台官方出品','独立实现','不属于 CPH 官方产品','本地测试通过不等同于在线评测 Accepted'])assert.ok(about.includes(text),text);
    await page.screenshot({path:path.join(temp,'about-disclaimer.png')});
    console.log(JSON.stringify({passed:true,browser:await browser.version(),checks:['platform query, matching rows, sorting disabled, focus/selection/scroll survive artwork and problem save','latest filter typed during delayed read retained','route change rejects old filter restoration','contest search/platform and algorithm search/category retained','editor draft retained'],artifacts:temp},null,2));
  }finally{await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
