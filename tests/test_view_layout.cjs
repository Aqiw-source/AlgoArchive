'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const root=path.resolve(process.env.ALGOARCHIVE_QA_ROOT||path.join(__dirname,'..')),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-view-layout-'));
 const server=http.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8',path.join(root,'app.py'),'--port',String(port),'--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
 let browser,logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
 try{
  let token;for(let i=0;i<100;i++){try{token=(await fetch(base).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch{}await delay(100);}assert.ok(token,logs);
  const send=async(route,body)=>{const r=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});assert.ok(r.ok,await r.clone().text());return r.json();};
  const {contest}=await send('/api/contests',{platform:'Codeforces',title:'Layout regression contest',url:'https://example.com/contest'});
  const {algorithm}=await send('/api/algorithms',{name:'Layout regression algorithm',category:'Data structures',description:'Responsive layout check'});
  const {problem}=await send('/api/problems',{platform:'Codeforces',name:'Layout regression problem',url:'https://example.com/problem',contest_id:contest.id,algorithm_id:algorithm.id,language:'cpp',code:'int main() { return 0; }\n'});
  const {contest:longContest}=await send('/api/contests',{platform:'CustomPlatform'.repeat(6),title:'LongContestTitle'.repeat(16),url:'https://example.com/'+('path'.repeat(40))});
  const {algorithm:longAlgorithm}=await send('/api/algorithms',{name:'LongAlgorithmName'.repeat(11),category:'LongCategory'.repeat(7),description:'LongDescription'.repeat(35)});
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
  const results=[],failures=[];
  for(const [width,height] of [[1440,1000],[1100,600],[880,480],[733,400],[390,844]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];page.setDefaultTimeout(8000);page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});page.on('dialog',d=>d.accept());
   let navigation=0;
   const go=async route=>{await page.goto(base+'/?qa='+(++navigation)+'#'+route);await page.locator('#main h1').waitFor();};
   const checkPage=async label=>{const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(geometry.scroll<=geometry.width+1,`${label}: page horizontal overflow ${JSON.stringify(geometry)}`);for(const field of await page.locator('.search-field').all()){const offset=await field.evaluate(e=>{const i=e.querySelector('input').getBoundingClientRect(),s=e.querySelector('span').getBoundingClientRect();return Math.abs((i.top+i.bottom-s.top-s.bottom)/2);});assert.ok(offset<=0.75,`${label}: search icon is not centered (${offset}px)`);}};
   const checkMenu=async(label,selector)=>{
    const input=page.locator(selector);await input.click();await page.locator('.platform-options:not([hidden])').waitFor();
    const geometry=await page.locator('.platform-options:not([hidden])').evaluate(list=>{
     const rect=list.getBoundingClientRect();let top=0,bottom=innerHeight,left=0,right=innerWidth;
     for(let e=list.parentElement;e&&e!==document.body;e=e.parentElement){const s=getComputedStyle(e),r=e.getBoundingClientRect();if(/auto|scroll|hidden|clip/.test(s.overflowY)){top=Math.max(top,r.top+e.clientTop);bottom=Math.min(bottom,r.top+e.clientTop+e.clientHeight);}if(/auto|scroll|hidden|clip/.test(s.overflowX)){left=Math.max(left,r.left+e.clientLeft);right=Math.min(right,r.left+e.clientLeft+e.clientWidth);}}
     return {rect:rect.toJSON(),top,bottom,left,right,modalScroll:document.querySelector('#modal').scrollTop};
    });
    await page.screenshot({path:path.join(temp,`${label}-${width}.png`)});
    assert.ok(geometry.rect.top>=geometry.top-1&&geometry.rect.bottom<=geometry.bottom+1,`${label}: platform options clipped ${JSON.stringify(geometry)}`);
    assert.ok(geometry.rect.left>=geometry.left-1&&geometry.rect.right<=geometry.right+1,`${label}: platform options clipped horizontally`);
    assert.ok(geometry.rect.height>=40,`${label}: no usable menu height`);
    const nextField=await page.locator('input[name="url"]').evaluate(e=>e.closest('.field').getBoundingClientRect().toJSON());
    assert.ok(geometry.rect.bottom<=nextField.top+1,`${label}: expanded menu must push the next field down`);
    const hint=await page.locator('.platform-help').evaluate(e=>({rect:e.getBoundingClientRect().toJSON(),color:getComputedStyle(e).color,visibility:getComputedStyle(e).visibility}));
    assert.equal(await page.locator('.platform-help').textContent(),'可选择当前内置的平台，也可自行输入其他平台。');
    assert.ok(hint.rect.bottom<=(await input.boundingBox()).y+1,'short platform hint stays beside the label and above the input');assert.equal(hint.visibility,'visible');assert.equal(hint.color,'rgb(180, 35, 53)');
    if(height>=600)assert.ok(Math.abs(geometry.rect.height-146)<=1,'normal viewport shows four platform rows');
    if(label.startsWith('contest')&&width>720){const title=await page.locator('#contest-form input[name="title"]').boundingBox();assert.ok(Math.abs(title.y-(await input.boundingBox()).y)<=1,'contest inputs remain aligned with the short side hint');}
    const list=page.locator('.platform-options:not([hidden])'),box=await list.boundingBox();
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.wheel(0,900);await delay(100);
    const wheel=await list.evaluate(e=>({top:e.scrollTop,full:e.scrollHeight,height:e.clientHeight,modal:document.querySelector('#modal').scrollTop}));
    assert.ok(wheel.top>0||wheel.full<=wheel.height,'options can scroll');assert.equal(wheel.modal,geometry.modalScroll,'menu wheel does not move dialog');
    await input.press('Escape');await input.click();assert.equal(await list.evaluate(e=>e.scrollTop),0,'reopening starts at first option');
    for(let i=0;i<10;i++)await input.press('ArrowDown');
    const last=page.locator('[data-platform-value="POJ"]');
    assert.equal(await last.evaluate(e=>{const r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return r.top>=p.top&&r.bottom<=p.bottom;}),true,'last option visible after keyboard navigation');
    await input.press('Enter');assert.equal(await input.inputValue(),'POJ');assert.equal(await input.getAttribute('aria-expanded'),'false');
    await input.click();await input.press('Escape');assert.equal(await input.getAttribute('aria-expanded'),'false');
    await input.click();
   };
   try{
    await go('contests');await page.locator('[data-new-contest]').first().click();await checkMenu('contest-create','#contest-form-platform');await page.locator('[data-close-modal]').first().click();
    await go('contest/'+contest.id);await page.locator('[data-edit-contest]').click();await checkMenu('contest-edit','#contest-form-platform');await page.locator('[data-close-modal]').first().click();
    await go('new-problem');await checkMenu('problem-create','#editor-platform');
    for(const route of ['home','platform/codeforces','platform/atcoder','platform/acwing','platform/luogu','platform/niuke','problems','contests','contest/'+contest.id,'algorithms','algorithm/'+algorithm.id,'problem/'+problem.id,'new-problem','compiler','new-snippet?algorithm='+algorithm.id,'contest/'+longContest.id,'algorithm/'+longAlgorithm.id]){await go(route);await checkPage(route);await page.screenshot({path:path.join(temp,`view-${route.replace(/[^a-z0-9-]/gi,'_')}-${width}.png`)});}
    await go('home');await page.locator('#open-profile-settings').click();
    await page.locator('#profile-name-input').waitFor();assert.equal(await page.locator('#profile-name-input').evaluate(e=>document.activeElement!==e&&e.selectionStart===e.selectionEnd),true,'settings must not select the username on open');
    for(const tab of ['profile','art','browser','compiler','data','about']){await page.locator(`[data-settings-tab="${tab}"]`).click();await page.locator(`[data-settings-tab="${tab}"].active`).waitFor();await page.locator('#settings-content > :first-child').waitFor();await checkPage('settings/'+tab);const fit=await page.locator('#settings-content').evaluate(e=>({client:e.clientWidth,scroll:e.scrollWidth}));assert.ok(fit.scroll<=fit.client+1,`settings/${tab}: content overflow ${JSON.stringify(fit)}`);await page.screenshot({path:path.join(temp,`settings-${tab}-${width}.png`)});}
    await page.locator('[data-close-modal]').first().click();
    await go('problems');await page.locator('[data-import-problems]').click();await page.locator('#modal[open]').waitFor();await checkPage('problem import');await page.locator('[data-close-modal]').first().click();
    await page.locator('[data-problem-preview]').first().press('Enter');await page.locator('.preview-code').waitFor();await checkPage('code preview');await page.locator('[data-close-modal]').first().click();
    await go('algorithms');await page.locator('[data-new-algorithm]').first().click();await page.locator('#algorithm-form').waitFor();await checkPage('algorithm form');await page.locator('#algorithm-form button[type=submit]').scrollIntoViewIfNeeded();assert.ok(await page.locator('#algorithm-form button[type=submit]').isVisible());await page.locator('[data-close-modal]').first().click();
    for(const route of ['new-problem','new-snippet?algorithm='+algorithm.id,'compiler']){
     await go(route);const code=page.locator('#code-input');await code.waitFor();
     assert.ok((await page.locator('.code-editor').boundingBox()).height<=height-130,'code editor leaves room for toolbar and status');
     await code.fill(Array.from({length:80},(_,i)=>'// line '+i).join('\n')+'\n// END_MARKER');await code.press('Control+End');await code.pressSequentially(' typing');
     await page.locator('.editor-toolbar').evaluate(e=>e.scrollIntoView({block:'start'}));await delay(100);
     const view=await page.evaluate(()=>{const a=document.querySelector('#code-input'),last=document.querySelector('#highlight-code').lastElementChild,r=a.getBoundingClientRect(),l=last.getBoundingClientRect(),status=document.querySelector('.editor-status').getBoundingClientRect();return {last:l.toJSON(),area:r.toJSON(),client:a.clientHeight,status:status.toJSON(),viewport:innerHeight};});
     assert.ok(view.last.top>=view.area.top&&view.last.bottom<=view.area.top+view.client+1,'typed last line is fully visible');assert.ok(view.status.top>=view.area.bottom-1&&view.status.bottom<=view.viewport+1,'editor status remains visible without covering code');
     await page.screenshot({path:path.join(temp,`editor-${route.split('?')[0]}-${width}.png`)});
    }
    assert.deepEqual(errors,[]);results.push({viewport:[width,height],pages:17,settingsTabs:6,passed:true});
   }catch(error){failures.push({viewport:[width,height],message:error.message});await page.screenshot({path:path.join(temp,`failure-${width}.png`)});}
   await page.close();
  }
  console.log(JSON.stringify({results,failures,artifacts:temp},null,2));assert.deepEqual(failures,[]);
 }finally{await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});
