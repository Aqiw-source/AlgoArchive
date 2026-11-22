'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const {buildDemo}=require('../scripts/build-demo.cjs');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function checkOldDemo(browser,temp,base){
  const demoDir=path.join(temp,'pages'),prefix='/AlgoArchive/';buildDemo(demoDir,prefix);
  const demo=await browser.newPage(),errors=[];
  demo.on('pageerror',e=>errors.push(e.message));
  await demo.route('**/api/**',r=>r.abort()); // The demo store must answer without a local backend.
  await demo.route('**/AlgoArchive/**',r=>{
    const name=new URL(r.request().url()).pathname.slice(prefix.length)||'index.html';
    return r.fulfill({path:path.join(demoDir,name)});
  });
  try{
    await demo.goto(base+prefix+'#home');await demo.locator('.recent-section').waitFor();
    assert.equal(await demo.locator('#study-queue-title').count(),0);
    await demo.locator('[data-new-problem]').first().click();await demo.locator('#problem-form').waitFor();
    assert.equal(await demo.locator('#editor-study-status,#editor-mistake-note,#editor-algorithm-tags').count(),0);
    const select=demo.locator('select[name=algorithm_id]');await select.selectOption({index:1});const id=await select.inputValue();
    await demo.locator('[name=name]').fill('Demo single algorithm');await demo.locator('[name=url]').fill('https://example.org/demo-single');
    await demo.locator('#save-problem').click();await demo.waitForURL(/#problem\//);
    assert.equal(await select.inputValue(),id);await demo.locator('nav [data-nav="problems"]').click();
    await demo.locator('#filter-query').fill('Demo single algorithm');
    assert.equal(await demo.locator('[data-problem-preview]').count(),1);assert.equal(await demo.locator('#filter-status').count(),0);
    assert.deepEqual(errors,[]);
  }finally{await demo.close();}
}
async function main(){
  const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-study-ui-'));
  const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8','app.py','--port','0','--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
  let logs='',out='',browser,startError;
  child.on('error',e=>{startError=e;});child.stdout.on('data',b=>{out+=b;logs+=b;});child.stderr.on('data',b=>logs+=b);
  try{
    let base;
    for(let i=0;i<200&&!startError&&child.exitCode===null;i++){base=out.match(/(http:\/\/127\.0\.0\.1:\d+)\r?\n/)?.[1];if(base)break;await delay(100);}
    assert.ok(base,String(startError||logs));const csrf=(await fetch(base,{signal:AbortSignal.timeout(5000)}).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];assert.ok(csrf,logs);
    const get=route=>fetch(base+route).then(r=>r.json());
    const send=async(route,body)=>{const r=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});assert.ok(r.ok,await r.clone().text());return r.json();};
    const a=(await send('/api/algorithms',{name:'数据结构'})).algorithm.id,b=(await send('/api/algorithms',{name:'图论'})).algorithm.id;
    const contest=(await send('/api/contests',{title:'春季赛',platform:'Codeforces',url:'https://example.org/contest'})).contest.id;
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
    const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];page.setDefaultTimeout(10000);
    page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('dialog',d=>d.accept());
    let n=0;const go=async hash=>{await page.goto(base+'/?study-qa='+(++n)+'#'+hash);await page.locator('#main h1').waitFor();};
    const rows=()=>page.locator('#problem-table tr[data-problem-preview]').evaluateAll(es=>es.map(e=>e.dataset.problemPreview));
    const save=async()=>{const result=page.waitForResponse(r=>/\/api\/problems(?:\/[^/]+)?$/.test(r.url())&&['POST','PUT'].includes(r.request().method()));await page.locator('#save-problem').click();const response=await result;assert.ok(response.ok(),await response.text());const record=(await response.json()).problem;await page.waitForFunction(()=>document.querySelector('#save-problem')?.textContent.includes('保存修改')&&!document.querySelector('#save-problem').disabled);return record;};
    const sites={codeforces:'https://codeforces.com/',atcoder:'https://atcoder.jp/',acwing:'https://www.acwing.com/',luogu:'https://www.luogu.com.cn/',niuke:'https://ac.nowcoder.com/'};
    await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin:base});
    for(const [key,url] of Object.entries(sites)){
      await go('platform/'+key);
      const link=page.locator('.platform-heading a');
      // Inspect actual new-tab navigation without relying on third-party network availability.
      await page.context().route(url,r=>r.fulfill({contentType:'text/plain',body:'Official destination'}));
      const popup=page.waitForEvent('popup');await link.click();const official=await popup;await official.waitForLoadState();assert.equal(official.url(),url);await official.close();
      await page.locator('[data-copy-platform-site]').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),url);
    }
    const manualPage=page.waitForEvent('popup');await page.getByRole('link',{name:'使用手册'}).click();
    const manual=await manualPage;await manual.getByRole('heading',{name:'使用手册',exact:true}).waitFor();
    assert.equal(new URL(manual.url()).origin,base);await manual.setViewportSize({width:390,height:844});
    await manual.locator('nav a[href="#import"]').click();assert.equal(new URL(manual.url()).hash,'#import');
    assert.ok(await manual.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await manual.close();
    await go('new-problem?algorithm='+a);assert.equal(await page.locator('#editor-study-status').inputValue(),'unseen');
    assert.equal(await page.locator('#editor-algorithm').inputValue(),a);await page.locator('#editor-algorithm').selectOption(b);
    assert.equal(await page.locator('#editor-algorithm-tags button').count(),2);
    await page.locator('[name=name]').fill('共享题');await page.locator('[name=url]').fill('https://example.org/shared');
    await page.locator('#editor-contest').selectOption(contest);await page.locator('#editor-study-status').selectOption('todo');
    const note='\n遗漏边界\n下次先检查 <n> & 空图';await page.locator('#editor-mistake-note').fill(note);
    const first=await save();assert.deepEqual([first.algorithm_ids,first.algorithm_id,first.study_status,first.mistake_note,first.code],[[a,b],a,'todo',note,'']);
    const second=(await send('/api/problems',{name:'对照题',platform:'Codeforces',url:'https://example.org/second',language:'cpp',code:'',algorithm_ids:[b,a],study_status:'done'})).problem;
    await send('/api/problems',{name:'单独待补',platform:'Codeforces',url:'https://example.org/solo',language:'cpp',code:'',study_status:'todo'});
    await go('home');assert.equal(await page.title(),'算法档案');assert.equal(await page.locator('#study-queue-items li').count(),2);
    await page.locator('#study-contest').selectOption(contest);assert.match(await page.locator('#study-queue-items').innerText(),/共享题/);assert.equal(await page.locator('#study-queue-items li').count(),1);
    await page.locator('#study-contest').selectOption('none');assert.match(await page.locator('#study-queue-items').innerText(),/单独待补/);
    await page.locator('#study-contest').selectOption('');await page.locator('#study-queue-items').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(temp,'home.png')});
    await go('problems');await page.locator('#filter-status').selectOption('done');assert.deepEqual(await rows(),[second.id]);
    await page.locator('#filter-status').selectOption('todo');await page.locator('#filter-query').fill('图论');assert.deepEqual(await rows(),[first.id]);
    await page.locator('[data-problem-preview]').press('Enter');assert.equal(await page.locator('.study-preview-note p').textContent(),note);assert.match(await page.locator('#modal').innerText(),/暂无代码/);await page.locator('[data-close-modal]').first().click();
    await go('algorithm/'+a);assert.deepEqual(await rows(),[first.id,second.id]);
    await page.locator('[data-drag-algorithm-problem]').first().press('Alt+ArrowDown');
    await page.waitForFunction(id=>document.querySelector('#problem-table tr[data-problem-preview]')?.dataset.problemPreview===id,second.id);
    await go('algorithm/'+b);assert.deepEqual(await rows(),[first.id,second.id]);
    await go('problem/'+first.id);await page.setViewportSize({width:390,height:844});await page.locator('#editor-mistake-note').scrollIntoViewIfNeeded();assert.equal(await page.locator('#editor-mistake-note').inputValue(),note);
    const viewportFits=()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1);assert.ok(await viewportFits(),'mobile editor has horizontal overflow');
    await page.screenshot({path:path.join(temp,'editor-mobile.png')});
    await page.locator('[data-remove-algorithm-tag="'+a+'"]').click();await page.locator('#editor-study-status').selectOption('done');
    assert.match(await page.locator('#save-state').innerText(),/未保存/);
    const changed=await save();assert.deepEqual([changed.algorithm_ids,changed.algorithm_id,changed.mistake_note],[[b],b,note]);
    await go('home');assert.equal(await page.locator('#study-queue-items li').count(),1);assert.ok(await viewportFits(),'mobile home has horizontal overflow');
    await go('algorithm/'+b);await page.locator('[data-delete-algorithm]').click();assert.match(await page.locator('#delete-algorithm-form').innerText(),/2 道题目/);
    await page.locator('#delete-algorithm-form [type=submit]').click();await page.locator('#algorithm-list').waitFor();
    const after=(await get('/api/problems/'+first.id)).problem;assert.deepEqual([after.algorithm_ids,after.study_status,after.mistake_note],[[],'done',note]);
    await go('algorithm/'+a);assert.deepEqual(await rows(),[second.id]);assert.deepEqual(errors,[]);
    await checkOldDemo(browser,temp,base);
    console.log(JSON.stringify({passed:true,browser:await browser.version(),artifacts:temp,viewports:['1440x900','390x844'],demo:'single-algorithm editing remains usable offline'}));
  }finally{await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
