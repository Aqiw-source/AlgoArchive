'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const root=path.resolve(process.env.ALGOARCHIVE_QA_ROOT||path.join(__dirname,'..')),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-modal-scroll-'));
 const listener=http.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8',path.join(root,'app.py'),'--port',String(port),'--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
 let browser,logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
 try{
  let token;for(let i=0;i<100;i++){try{token=(await fetch(base).then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch{}await delay(100);}assert.ok(token,logs);
  for(let i=0;i<35;i++){const response=await fetch(base+'/api/problems',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify({platform:'Codeforces',name:'Scroll test '+i,url:'https://example.com/'+i,language:'cpp',code:''})});assert.ok(response.ok);}
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
  const results=[];
  for(const [width,height] of [[1100,600],[390,844]]){
   const page=await browser.newPage({viewport:{width,height}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.goto(base+'/#problems');await page.locator('#problem-table tbody tr').nth(34).waitFor();
   if(width>720){await page.mouse.move(width-30,height-30);await page.mouse.wheel(0,450);await delay(150);}
   await page.locator('#open-profile-settings').click();await page.locator('#modal[open]').waitFor();
   const before=await page.evaluate(()=>({y:scrollY,x:scrollX,nav:document.querySelector('.workspace-nav').scrollTop,sidebar:document.querySelector('.workspace-sidebar').scrollTop}));
   await page.mouse.move(width-2,height-3);await page.mouse.wheel(0,650);await delay(150);
   assert.equal(await page.evaluate(()=>scrollY),before.y,`${width}: backdrop wheel must not move page`);
   await page.mouse.move(2,height/2);await page.mouse.wheel(0,650);await delay(150);
   assert.deepEqual(await page.evaluate(()=>({y:scrollY,x:scrollX,nav:document.querySelector('.workspace-nav').scrollTop,sidebar:document.querySelector('.workspace-sidebar').scrollTop})),before,`${width}: sidebar remains frozen`);
   await page.locator('[data-settings-tab="about"]').click();
   const content=page.locator('#settings-content');const box=await content.boundingBox();
   await page.mouse.move(box.x+box.width/2,box.y+Math.min(box.height/2,100));await page.mouse.wheel(0,700);await delay(150);
   const inside=await page.evaluate(()=>['#modal','#settings-content','.settings-shell'].map(selector=>{const e=document.querySelector(selector);return {selector,top:e.scrollTop,height:e.clientHeight,full:e.scrollHeight,bounds:e.getBoundingClientRect().toJSON()};}));
   if(!inside.some(e=>e.top>0)){await page.screenshot({path:path.join(temp,`failed-${width}.png`)});console.log(JSON.stringify({width,inside,artifacts:temp}));}
   assert.ok(inside.some(e=>e.top>0),'modal content should scroll');
   for(let i=0;i<3;i++)await page.mouse.wheel(0,1200);await delay(150);assert.equal(await page.evaluate(()=>scrollY),before.y,'modal bottom must not chain to page');
   await page.screenshot({path:path.join(temp,`modal-${width}.png`)});
   await page.locator('[data-close-modal]').first().click();await page.locator('#modal').waitFor({state:'hidden'});assert.equal(await page.evaluate(()=>scrollY),before.y,'close restores page position');
   await page.mouse.move(width-30,height-30);await page.mouse.wheel(0,450);await delay(150);assert.ok(await page.evaluate(()=>scrollY)>before.y,'page scroll works after close');
   assert.deepEqual(errors,[]);results.push({viewport:[width,height],backgroundPosition:before.y,passed:true});await page.close();
  }
  console.log(JSON.stringify({passed:true,results,artifacts:temp},null,2));
 }finally{await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);}
})().catch(error=>{console.error(error);process.exitCode=1;});
