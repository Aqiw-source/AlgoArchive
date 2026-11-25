"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const http=require("node:http");
const {spawn}=require("node:child_process");
const {chromium}=require("playwright");
const {buildDemo}=require("../scripts/build-demo.cjs");
const root=path.resolve(process.env.ALGOARCHIVE_QA_ROOT||path.join(__dirname,".."));
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),"algo-colors-qa-"));
  const output=process.env.ALGOARCHIVE_QA_ARTIFACTS||path.join(temp,"screenshots");
  fs.mkdirSync(output,{recursive:true});
  const listener=http.createServer();
  await new Promise(resolve=>listener.listen(0,"127.0.0.1",resolve));
  const port=listener.address().port;
  await new Promise(resolve=>listener.close(resolve));
  const local=`http://127.0.0.1:${port}`;
  const executable=process.env.ALGOARCHIVE_QA_EXECUTABLE;
  const child=spawn(executable||process.env.ALGOARCHIVE_TEST_PYTHON||"python",[
    ...(executable?[]:["-X","utf8",path.join(root,"app.py")]),"--port",String(port),
    "--data-dir",path.join(temp,"中文 题库"),"--config-path",path.join(temp,"配置.json"),"--no-browser"
  ],{cwd:root,windowsHide:true,stdio:"pipe"});
  let token,logs="",browser,server;
  child.stdout.on("data",b=>{logs+=b;});child.stderr.on("data",b=>{logs+=b;});
  try{
    for(let i=0;i<150;i++){
      try{token=(await fetch(local+"/").then(r=>r.text())).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}catch(_){}
      await delay(100);
    }
    assert.ok(token,logs);
    const site=path.join(temp,"site");buildDemo(site);
    const types={".html":"text/html",".js":"text/javascript",".css":"text/css",".png":"image/png",".webp":"image/webp",".ico":"image/x-icon"};
    server=http.createServer((req,res)=>{
      const pathname=decodeURIComponent(new URL(req.url,"http://localhost").pathname);
      const file=path.resolve(site,pathname.replace(/^\/AlgoArchive\//,"")||"index.html");
      if(!pathname.startsWith("/AlgoArchive/")||!file.startsWith(site+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404).end();return;}
      res.writeHead(200,{"Content-Type":types[path.extname(file)]||"application/octet-stream"});fs.createReadStream(file).pipe(res);
    });
    await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
    const demo=`http://127.0.0.1:${server.address().port}/AlgoArchive/`;
    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:"msedge"})});
    const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],checks=[];
    page.on("pageerror",e=>errors.push(e.message));page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
    const state=()=>page.evaluate(()=>fetch("/api/state").then(r=>r.json()));
    const styles=async kind=>{
      await page.mouse.move(0,0);
      return page.locator(`.${kind}-card`).evaluateAll(items=>Object.fromEntries(items.map(el=>[el.dataset.orderId,{
      background:getComputedStyle(el).backgroundImage,accent:getComputedStyle(el).getPropertyValue("--tone").trim(),
      decoration:getComputedStyle(el,"::after").backgroundImage,border:getComputedStyle(el).getPropertyValue("--tone-line").trim()
      }])));
    };
    for(const [mode,base] of [["local",local+"/"],["demo",demo]]){
      for(const [collection,kind,field] of [["algorithms","algorithm","name"],["contests","contest","title"]]){
        await page.goto(base+"#"+collection);
        await page.locator("h1").waitFor();
        const existing=(await state())[collection];
        const records=[];
        for(let i=0;i<8;i++){
          const payload=kind==="contest"
            ?{title:`Color QA ${i}`,platform:"HDU",url:`https://example.com/${mode}/${i}`}
            :{name:`Color QA ${i}`,category:"Color QA",description:"",links:[]};
          const result=await page.evaluate(async ({collection,payload})=>{
            const csrf=document.querySelector('meta[name="csrf-token"]')?.content||"";
            const response=await fetch(`/api/${collection}`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(payload)});
            return {status:response.status,body:await response.json()};
          },{collection,payload});
          assert.ok([200,201].includes(result.status),`${mode}/${kind}: seed card through the API (${result.status})`);
          records.push(result.body[kind]);
        }
        await page.evaluate(()=>{location.hash="#home";});await page.locator(".stats-grid").waitFor();
        await page.evaluate(()=>{location.hash="#algorithms";});await page.locator(".algorithm-card").first().waitFor();
        await page.evaluate(({collection})=>{location.hash="#"+collection;},{collection});
        await page.locator(`.${kind}-card`).first().waitFor();
        if(mode==="local"&&collection==="algorithms"){
          await page.locator(".header-actions [data-new-algorithm]").click();
          const form=page.locator("#algorithm-form");await form.locator('[name="name"]').fill("Color QA real form");
          await form.locator('[type="submit"]').click();await page.waitForURL(/#algorithm\//);
          const created=(await state()).algorithms.find(item=>item.name==="Color QA real form");
          assert.equal(created.card_color,["blue","cyan","green","amber","rose","violet"][(existing.length+8)%6]);
          await page.goto(base+"#algorithms");await page.locator(".algorithm-card").first().waitFor();
        }
        let before=await styles(kind);
        const colors=records.map(item=>before[item.id].background);
        assert.equal(new Set(colors.slice(0,6)).size,6,`${mode}/${kind}: six newly created cards must have distinct rendered backgrounds`);
        assert.equal(colors[6],colors[0]);assert.equal(colors[7],colors[1]);
        assert.equal(new Set(records.slice(0,6).map(item=>before[item.id].accent)).size,6);
        assert.equal(new Set(records.slice(0,6).map(item=>before[item.id].decoration)).size,6);
        const expected=["blue","cyan","green","amber","rose","violet"];
        assert.deepEqual(records.map((item,i)=>item.card_color),records.map((_,i)=>expected[(existing.length+i)%6]));
        const search=page.locator(".cards-toolbar input");
        await search.fill("Color QA 3");
        assert.deepEqual(await styles(kind),{[records[3].id]:before[records[3].id]});
        await search.fill("");
        const first=await page.locator(`.${kind}-card`).first().getAttribute("data-order-id");
        const handle=await page.locator(`[data-drag-order="${kind}"]`).first().boundingBox();
        const target=await page.locator(`.${kind}-card`).nth(1).boundingBox();
        await page.mouse.move(handle.x+handle.width/2,handle.y+handle.height/2);
        await page.mouse.down();
        await page.mouse.move(handle.x+handle.width/2+10,handle.y+handle.height/2+4,{steps:4});
        await page.mouse.move(target.x+target.width*.8,target.y+target.height*.5,{steps:12});
        await page.mouse.up();
        await page.waitForFunction(({kind,id})=>document.querySelectorAll(`.${kind}-card`)[1]?.dataset.orderId===id,{kind,id:first});
        assert.deepEqual(await styles(kind),before);
        await page.locator(`[data-order-id="${records[0].id}"].${kind}-card .title-link`).click();
        await page.locator(`[data-edit-${kind}]`).click();
        await page.locator(`#${kind}-form [name="${field}"]`).fill("Renamed search DFS");
        await page.locator(`#${kind}-form [type="submit"]`).click();
        await page.locator(`#${kind}-form`).waitFor({state:"detached"});
        await page.goto(base+"#"+collection);await page.locator(`.${kind}-card`).first().waitFor();
        assert.deepEqual(await styles(kind),before);
        if(mode==="local"){
          await page.reload();await page.locator(`.${kind}-card`).first().waitFor();
          assert.deepEqual(await styles(kind),before);
        }
        for(const width of [1440,390]){
          await page.setViewportSize({width,height:width===1440?1000:844});
          await page.waitForFunction(()=>Array.from(document.images).every(i=>i.complete&&i.naturalWidth));
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
          await page.screenshot({path:path.join(output,`${mode}-${collection}-${width}.png`),fullPage:true});
        }
        await page.setViewportSize({width:1440,height:1000});
        checks.push(`${mode}/${kind}: eight seeded cards render six tones, wraparound, filter, mouse drag, rename, desktop/mobile${mode==="local"&&collection==="algorithms"?"; one real create form":""}`);
      }
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({outcome:"PASS",checks,output,temp},null,2));
  }finally{
    if(browser)await browser.close();
    if(server)await new Promise(resolve=>server.close(resolve));
    if(token)await fetch(local+"/api/shutdown",{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":token,Origin:local},body:"{}",signal:AbortSignal.timeout(5000)}).catch(()=>{});
    for(let i=0;i<40&&child.exitCode===null;i++)await delay(100);
    if(child.exitCode===null)child.kill();
  }
}
main().catch(e=>{console.error(e);process.exitCode=1;});
