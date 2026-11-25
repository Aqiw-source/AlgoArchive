'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{chromium}=require('playwright');
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

async function main(){
  const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'algo-problem-navigation-'));
  const child=spawn(process.env.ALGOARCHIVE_TEST_PYTHON||'python',['-X','utf8','app.py','--port','0','--data-dir',path.join(temp,'data'),'--config-path',path.join(temp,'config.json'),'--no-browser'],{cwd:root,windowsHide:true,stdio:'pipe'});
  let logs='',out='',browser;
  child.stdout.on('data',chunk=>{out+=chunk;logs+=chunk;});child.stderr.on('data',chunk=>logs+=chunk);
  try{
    let base,token;
    for(let i=0;i<200&&child.exitCode===null;i++){
      base=out.match(/(http:\/\/127\.0\.0\.1:\d+)\r?\n/)?.[1];
      if(base){token=(await fetch(base).then(response=>response.text()).catch(()=>'' )).match(/name="csrf-token" content="([^"]+)"/)?.[1];if(token)break;}
      await delay(100);
    }
    assert.ok(base&&token,logs);
    const send=async(route,data)=>{
      const response=await fetch(base+route,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token},body:JSON.stringify(data)});
      const body=await response.json();assert.ok(response.ok,route+': '+JSON.stringify(body));return body;
    };
    const algorithm=(await send('/api/algorithms',{name:'Navigation test algorithm'})).algorithm;
    const contest=(await send('/api/contests',{title:'Navigation test contest',platform:'Codeforces',url:'https://example.org/contest'})).contest;
    const problems=[];
    for(let i=0;i<20;i++)problems.push((await send('/api/problems',{platform:'Codeforces',number:String(i),name:`nav-return ${String(i).padStart(2,'0')}`,url:`https://example.org/problem/${i}`,language:'cpp',code:'int main() {}',contest_id:contest.id,algorithm_ids:[algorithm.id],study_status:'todo'})).problem);

    browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_EXECUTABLE_PATH?{executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH}:{channel:'msedge'})});
    const page=await browser.newPage({viewport:{width:1440,height:850}});page.setDefaultTimeout(10000);
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const dialogs=[];page.on('dialog',async dialog=>{dialogs.push(dialog.message());await dialog.dismiss();});
    let routeVersion=0;
    const go=async route=>{
      await page.goto(`${base}/?navigation-test=${++routeVersion}#${route}`);
      await page.locator('#main h1').waitFor();
    };
    const changeRoute=async route=>{
      await page.evaluate(value=>{location.hash='#'+value;},route);
      await page.waitForFunction(value=>location.hash==='#'+value&&!!document.querySelector('#main h1'),route);
    };
    const rows=()=>page.locator('#problem-table tbody tr.problem-row-preview');
    const visibleRow=async()=>{
      const id=await page.evaluate(()=>[...document.querySelectorAll('#problem-table tbody tr.problem-row-preview')].find(row=>{
        const rect=row.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight&&row.querySelector('[data-open-problem]');
      })?.dataset.problemPreview||'');
      assert.ok(id,'a filtered problem row should be visible at the preserved scroll position');
      return id;
    };
    const waitForReturn=async(route)=>{
      await page.waitForFunction(value=>location.hash==='#'+value,route);
      if(route==='home')await page.locator('#study-queue-items').waitFor();
      else await page.waitForFunction(()=>document.querySelector('#filter-query')?.value==='nav-return');
    };
    const checkListRoundTrip=async(route,returnByBrowser=false)=>{
      await go(route);
      await page.locator('#filter-query').fill('nav-return');
      await page.locator('#filter-language').selectOption('cpp');
      await page.locator('#filter-status').selectOption('todo');
      assert.equal(await rows().count(),problems.length,`${route}: source list is filtered`);
      await page.evaluate(()=>window.scrollTo(0,420));
      const id=await visibleRow(),scrollBefore=await page.evaluate(()=>scrollY);
      const edit=page.locator(`tr[data-problem-preview="${id}"] [data-open-problem]`);
      await edit.click();await page.locator('#problem-form').waitFor();
      assert.equal(await page.locator('a.back-link[data-return-problem-list]').count(),1,'the explicit return destination appears once');
      assert.equal(await page.locator('.page-header [data-return-problem-list]').count(),0,'the redundant header return action is omitted');
      if(returnByBrowser){await page.goBack();await waitForReturn(route);}
      else {await page.locator('a.back-link[data-return-problem-list]').click();await waitForReturn(route);}
      assert.equal(await page.locator('#filter-query').inputValue(),'nav-return',`${route}: keyword restored`);
      assert.equal(await page.locator('#filter-language').inputValue(),'cpp',`${route}: language restored`);
      assert.equal(await page.locator('#filter-status').inputValue(),'todo',`${route}: status restored`);
      assert.equal(await rows().count(),problems.length,`${route}: matching rows restored`);
      await page.waitForFunction(value=>Math.abs(scrollY-value)<2,scrollBefore);
      assert.equal(await page.evaluate(()=>document.activeElement?.dataset?.openProblem||''),id,`${route}: edited row action regains focus`);
    };

    await go('problems');
    const first=await rows().first().getAttribute('data-problem-preview');
    const title=page.locator(`tr[data-problem-preview="${first}"] .problem-title a`);
    assert.equal(await title.getAttribute('target'),'_blank','the title remains an external link');
    assert.match(await title.getAttribute('href'),/^https:\/\/example\.org\/problem\//);
    assert.match(await title.getAttribute('rel'),/noopener/);
    const preview=page.locator(`tr[data-problem-preview="${first}"] [data-preview-problem]`);
    await preview.click();await page.locator('#modal[open] [data-problem-preview-dialog]').waitFor();
    await page.keyboard.press('Escape');await page.locator('#modal[open]').waitFor({state:'detached'});
    assert.equal(await page.evaluate(()=>document.activeElement?.dataset?.previewProblem||''),first,'Escape restores focus to the explicit preview action');

    await checkListRoundTrip('problems',true);
    await checkListRoundTrip('platform/codeforces');
    await checkListRoundTrip(`contest/${contest.id}`);
    await checkListRoundTrip(`algorithm/${algorithm.id}`);

    // Complete an interior item. Neighbour selection must use THIS filtered list's order.
    for(const route of ['problems','platform/codeforces','contest/'+contest.id,'algorithm/'+algorithm.id]){
      await go(route);await page.locator('#filter-query').fill('nav-return');await page.locator('#filter-status').selectOption('todo');
      const ids=await rows().evaluateAll(items=>items.map(item=>item.dataset.problemPreview));
      const current=ids[3],next=ids[4];await rows().nth(3).locator('[data-open-problem]').click();
      await page.locator('#editor-study-status').selectOption('done');await page.locator('#save-problem').click();
      await page.getByText('题目、代码与测试用例已保存。',{exact:true}).waitFor();
      await page.locator('#save-problem:not([disabled])').waitFor();
      if(route==='problems')await page.goBack();
      else await page.locator('a.back-link[data-return-problem-list]').click();
      assert.deepEqual(dialogs,[],'no false discard warning on a saved edit');
      await waitForReturn(route);await page.waitForFunction(id=>document.activeElement?.dataset.openProblem===id,next);
      assert.equal(await page.locator('[data-open-problem="'+current+'"]').count(),0,'completed row leaves the filtered table');
      assert.equal(await rows().count(),ids.length-1);
    }

    // A direct link in the same tab must not inherit the previous editor's origin.
    await changeRoute('problem/'+problems[0].id);await page.locator('#problem-form').waitFor();
    assert.equal(await page.locator('a[data-return-problem-list]').getAttribute('href'),'#contest/'+contest.id);

    await go('home');
    await page.locator('#study-contest').selectOption(contest.id);
    const queue=page.locator('#study-queue-items [data-open-problem]');
    const queuedIds=await queue.evaluateAll(elements=>elements.map(element=>element.dataset.openProblem));
    assert.ok(queuedIds.length>=2,'the filtered home queue contains multiple pending problems');
    await queue.first().click();await page.locator('#problem-form').waitFor();
    const completedId=queuedIds[0],nextId=queuedIds[1];
    await page.locator('#editor-study-status').selectOption('done');
    const saved=page.waitForResponse(response=>response.url().includes(`/api/problems/${completedId}`)&&response.request().method()==='PUT');
    await page.locator('#save-problem').click();assert.ok((await saved).ok());
    await page.locator('#save-problem:not([disabled])').waitFor();
    await page.locator('a.back-link[data-return-problem-list]').click();
    assert.deepEqual(dialogs,[],'a successfully saved editor must not prompt to discard changes');
    await waitForReturn('home');
    assert.equal(await page.locator('#study-contest').inputValue(),contest.id,'home queue filter is restored');
    await page.waitForFunction(id=>document.activeElement?.dataset?.openProblem===id,nextId);
    assert.equal(await page.locator('#study-queue-items [data-open-problem]').first().getAttribute('data-open-problem'),nextId,'completion advances focus to the next matching pending problem');
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,checks:['explicit preview and Escape focus restoration','external title link retained','filter, scroll and row focus restored on all-problems/platform/contest/algorithm routes','browser back restores list state and advances to the next pending row on completion','save-and-return focus advances through filtered problems, platform, contest and algorithm tables','completed home-queue item advances focus to the next matching pending problem','direct problem routes do not inherit an unrelated origin'],browser:await browser.version()},null,2));
  }finally{
    await browser?.close();child.kill();fs.writeFileSync(path.join(temp,'server.log'),logs);try{fs.rmSync(temp,{recursive:true,force:true});}catch(_){}
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
