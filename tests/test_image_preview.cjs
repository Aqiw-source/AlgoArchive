'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const root=path.resolve(process.env.ALGOARCHIVE_QA_ROOT||path.join(__dirname,'..')),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-image-preview-'));
 const server=http.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r));const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8',path.join(root,'app.py'),'--port',String(port),'--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
 let browser,logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
 try{
  let token;for(let i=0;i<100;i++){try{token=(await fetch(base).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch{}await delay(100);}assert.ok(token,logs);
  const get=()=>fetch(base+'/api/state').then(r=>r.json());
  const put=async(route,body)=>{const r=await fetch(base+route,{method:'PUT',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(body)});assert.ok(r.ok,await r.clone().text());return r.json();};
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],writes=[];page.setDefaultTimeout(8000);page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(['POST','PUT','DELETE'].includes(r.method()))writes.push(r.url());});
  await page.goto(base+'/#algorithms');await page.locator('#main h1').waitFor();
  await page.locator('[data-open-avatar]').click();await page.locator('.avatar-preview-placeholder').waitFor();assert.match(page.url(),/#algorithms$/);await page.keyboard.press('Escape');await page.locator('#modal').waitFor({state:'hidden'});
  const avatar=fs.readFileSync(path.join(root,'web','platform-icons','codeforces.png'));
  await put('/api/profile',{name:'Preview test',avatar:'data:image/png;base64,'+avatar.toString('base64')});
  await put('/api/settings/sidebar-art',{image:'thinking',hidden:false});await page.reload();await page.locator('#profile-avatar.has-image').waitFor();
  const before=await get();
  for(const [width,height] of [[1440,1000],[1100,600],[390,844]]){
   await page.setViewportSize({width,height});await page.locator('[data-open-avatar]').click();await page.locator('.image-preview img').waitFor();
   await page.waitForFunction(()=>document.querySelector('.image-preview img').naturalWidth>0);
   assert.equal(await page.locator('.image-preview img').getAttribute('src'),before.profile.avatar);
   assert.deepEqual(Buffer.from(await fetch(base+before.profile.avatar).then(r=>r.arrayBuffer())),avatar,'avatar uses original bytes');
   assert.equal(await page.locator('.image-preview img').evaluate(e=>getComputedStyle(e).objectFit),'contain');
   await page.screenshot({path:path.join(temp,`avatar-${width}.png`)});await page.keyboard.press('Escape');
   await page.locator('[data-open-sidebar-art]').click();await page.locator('.sidebar-art-preview img').waitFor();
   const img=page.locator('.sidebar-art-preview img'),next=page.locator('[data-image-preview-step="1"]'),prev=page.locator('[data-image-preview-step="-1"]');
   assert.match(await img.getAttribute('src'),/sidebar-art-thinking\.png/);
   await next.click();assert.match(await img.getAttribute('src'),/sidebar-art\.png/);
   await next.click();assert.match(await img.getAttribute('src'),/sidebar-art-debug\.png/);
   await prev.click();assert.match(await img.getAttribute('src'),/sidebar-art\.png/);
   await page.keyboard.press('ArrowLeft');assert.match(await img.getAttribute('src'),/sidebar-art-thinking\.png/);
   const stage=page.locator('.image-preview-stage');
   await stage.dispatchEvent('pointerdown',{pointerId:1,pointerType:'touch',clientX:250,clientY:150});await stage.dispatchEvent('pointerup',{pointerId:1,pointerType:'touch',clientX:100,clientY:155});assert.match(await img.getAttribute('src'),/sidebar-art\.png/);
   await stage.dispatchEvent('pointerdown',{pointerId:2,pointerType:'touch',clientX:150,clientY:100});await stage.dispatchEvent('pointerup',{pointerId:2,pointerType:'touch',clientX:155,clientY:250});assert.match(await img.getAttribute('src'),/sidebar-art\.png/,'vertical gesture does not switch');
   const box=await stage.boundingBox();await page.mouse.move(box.x+box.width*.7,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width*.3,box.y+box.height/2,{steps:6});await page.mouse.up();assert.match(await img.getAttribute('src'),/sidebar-art-debug\.png/,'mouse swipe switches preview');
   await page.waitForFunction(()=>document.querySelector('.sidebar-art-preview img').naturalWidth>0);
   const fit=await page.locator('#modal').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1&&r.left>=0&&r.right<=innerWidth+1&&e.scrollWidth<=e.clientWidth;});assert.ok(fit,'viewer fits viewport');
   await page.screenshot({path:path.join(temp,`art-${width}.png`)});
   assert.equal(await page.locator('.sidebar-art img').getAttribute('data-art-image'),'thinking');assert.deepEqual((await get()).sidebar_art,before.sidebar_art);
   await page.keyboard.press('Escape');await page.locator('#modal').waitFor({state:'hidden'});
   await page.locator('[data-open-sidebar-art]').click();assert.match(await img.getAttribute('src'),/sidebar-art-thinking\.png/,'reopening starts from saved sidebar selection');await page.locator('[data-close-modal]').click();
  }
  assert.deepEqual(writes,[],'preview must not write settings or profile');assert.deepEqual(errors,[]);
  await page.locator('.identity-copy[data-nav="home"]').click();await page.waitForURL(/#home$/);
  console.log(JSON.stringify({passed:true,viewports:['1440x1000','1100x600','390x844'],writes:0,artifacts:temp},null,2));
 }finally{await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});
