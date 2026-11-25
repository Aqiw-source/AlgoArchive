(() => {
  'use strict';
  if(window.__DEMO_VERSION__||window.problemDraftRecovery)return;
  const prefix='algoarchive.problem-recovery.v1:';
  let current=null,projectRequest=null,inventoryRevision=0;
  const uid=()=>crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  const project=()=>projectRequest||(projectRequest=fetch('/api/health',{cache:'no-store'}).then(async response=>{
    if(!response.ok)throw Error('health unavailable');
    const data=await response.json();
    if(data.app!=='AlgoArchive'||!data.project_id)throw Error('project identity unavailable');
    return data.project_id;
  }).catch(error=>{projectRequest=null;throw error;}));
  const projectPrefix=(projectId,id)=>prefix+encodeURIComponent(projectId)+':'+encodeURIComponent(id)+':';
  const keyFor=s=>projectPrefix(s.projectId,s.id)+s.windowId;
  const dataOf=obj=>({code:obj?.code||'',note:obj?.note??obj?.mistake_note??'',tests:(obj?.tests?.length?obj.tests:[{input:'',output:''}]).map(test=>({input:test.input||'',output:test.output||''}))});
  const same=(a,b)=>a.code===b.code&&a.note===b.note&&JSON.stringify(a.tests)===JSON.stringify(b.tests);
  const active=s=>current===s&&s.form.isConnected&&!s.deleted;
  const node=(tag,text)=>Object.assign(document.createElement(tag),{textContent:text||''});
  function keys(start){const result=[];for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key?.startsWith(start))result.push(key);}return result;}
  function rows(s){return keys(projectPrefix(s.projectId,s.id)).flatMap(key=>{try{const raw=localStorage.getItem(key),value=JSON.parse(raw);if(value?.problemId!==s.id||value.projectId!==s.projectId||!Array.isArray(value.tests)||!Number.isFinite(Date.parse(value.updatedAt)))return[];return[{key,raw,value}];}catch(_){return[];}}).sort((a,b)=>b.value.updatedAt.localeCompare(a.value.updatedAt));}
  function warn(s,error){s.status.textContent=error?.name==='QuotaExceededError'?'浏览器存储空间不足，最新修改未能写入恢复草稿。请及时保存题目。':'无法写入本机恢复草稿。请及时保存题目。';s.status.hidden=false;}
  function removeRow(row){if(row&&localStorage.getItem(row.key)===row.raw)localStorage.removeItem(row.key);}
  function rotate(s){s.windowId=uid();s.key=keyFor(s);s.last=null;}
  function store(s,value){
    if(!s.projectId){s.pending=value;return;}
    if(same(value,s.disk)||(s.source&&same(value,s.source.value))){if(s.key)localStorage.removeItem(s.key);s.last=value;s.pending=null;s.status.hidden=true;return;}
    const record={projectId:s.projectId,problemId:s.id,windowId:s.windowId,baseVersion:s.version,updatedAt:new Date().toISOString(),...value};
    localStorage.setItem(s.key||keyFor(s),JSON.stringify(record));s.key=s.key||keyFor(s);s.last=value;s.pending=null;s.status.hidden=true;
  }
  function flush(s=current,force=false){
    if(!s)return;
    if(s.timer){clearTimeout(s.timer);s.timer=null;}
    let value=s.pending;
    if(active(s)){try{value=dataOf(s.hooks.capture());}catch(error){warn(s,error);return;}}
    if(!value)return;s.pending=value;
    if(!force&&s.last&&same(value,s.last))return;
    try{store(s,value);}catch(error){s.pending=value;warn(s,error);}
  }
  function queue(s=current){
    if(!s||!active(s))return;
    try{s.pending=dataOf(s.hooks.capture());}catch(error){warn(s,error);return;}
    if(s.timer)clearTimeout(s.timer);s.timer=setTimeout(()=>flush(s),250);
  }
  function addButton(parent,label,attr,action){const button=node('button',label);button.type='button';button.className='btn small';button.setAttribute(attr,'');button.addEventListener('click',action);parent.append(button);return button;}
  function showOffer(s){
    let available;
    try{available=rows(s);for(const row of available.filter(item=>same(item.value,s.disk)))removeRow(row);available=available.filter(item=>!same(item.value,s.disk)&&!(s.source&&item.key===s.source.key&&(!s.source.raw||item.raw===s.source.raw)));}
    catch(error){warn(s,error);return;}
    if(!available.length){s.panel.hidden=true;return;}
    s.panel.hidden=false;s.panel.dataset.mode='offer';s.panel.replaceChildren(node('strong','有可恢复的本机草稿'));
    for(const row of available){
      const item=node('div');item.className='recovery-row';
      item.append(node('span','草稿时间：'+new Date(row.value.updatedAt).toLocaleString('zh-CN',{hour12:false})));
      addButton(item,row.value.baseVersion===s.version?'恢复草稿':'对照版本','data-recovery-restore',()=>{
        if(!active(s))return;
        let local;try{local=dataOf(s.hooks.capture());}catch(error){warn(s,error);return;}
        if(row.value.baseVersion!==s.version||!same(local,s.disk))compare(s,row,s.problem);
        else choose(s,row,s.problem,'restore');
      });
      addButton(item,'删除这份草稿','data-recovery-discard',()=>{try{removeRow(row);showOffer(s);}catch(error){warn(s,error);}});
      s.panel.append(item);
    }
    addButton(s.panel,'继续使用题库版本','data-recovery-skip',()=>{s.panel.hidden=true;});
  }
  function column(title,data,attr){
    const section=node('section');section.append(node('h4',title));
    for(const pair of [['源码',data.code],['错因笔记',data.note],['测试用例',JSON.stringify(data.tests,null,2)]]){
      section.append(node('strong',pair[0]));const pre=node('pre',pair[1]||'（空）');if(pair[0]==='源码')pre.setAttribute(attr,'');section.append(pre);
    }
    return section;
  }
  function compare(s,row,disk){
    s.panel.hidden=false;s.panel.dataset.mode='conflict';
    s.panel.replaceChildren(node('strong','版本对照'),node('p','草稿时间：'+new Date(row.value.updatedAt).toLocaleString('zh-CN',{hour12:false})+'。两份内容会保留；采用草稿后仍需保存题目才会写入题库。'));
    const cols=node('div');cols.className='recovery-compare';
    cols.append(column('题库版本 · v'+disk.version,dataOf(disk),'data-recovery-disk-code'),column('本机草稿 · 基于 v'+row.value.baseVersion,row.value,'data-recovery-draft-code'));
    const actions=node('div');actions.className='recovery-row';
    addButton(actions,'使用题库版本，保留草稿','data-recovery-conflict-disk',()=>choose(s,row,disk,'disk'));
    addButton(actions,'采用草稿，继续编辑','data-recovery-conflict-overwrite',()=>choose(s,row,disk,'overwrite'));
    s.panel.append(cols,actions);
  }
  function choose(s,row,disk,choice){
    if(!active(s))return;
    let before;try{before=dataOf(s.hooks.capture());}catch(error){warn(s,error);return;}
    const value=choice==='disk'?dataOf(disk):row.value,own=row&&row.key===s.key;
    if(own||(!same(before,s.disk)&&!same(before,value))){
      if(!own){try{store(s,before);}catch(error){s.pending=before;warn(s,error);}}
      rotate(s);
    }
    const rebase=choice==='disk'||choice==='overwrite'?disk:null;
    try{s.hooks.restore(value,rebase);}catch(error){warn(s,error);return;}
    const target=current!==s&&current?.id===s.id&&active(current)?current:s;
    target.problem=disk;target.version=disk.version??target.version;target.disk=dataOf(disk);target.source=row||target.source||null;target.pending=null;target.last=value;
    try{store(target,value);}catch(error){target.pending=value;warn(target,error);}
    s.panel.hidden=true;target.panel.hidden=true;
  }
  function conflict({problemId,latestProblem}){
    const s=current;if(!s||!active(s)||s.id!==problemId||!latestProblem)return;
    let value,row;try{value=dataOf(s.hooks.capture());flush(s,true);row=rows(s).find(item=>same(item.value,value));}catch(error){warn(s,error);}
    row=row||{key:s.key,raw:'',value:{...value,updatedAt:new Date().toISOString(),baseVersion:s.version}};
    compare(s,row,latestProblem);s.panel.scrollIntoView({block:'start'});
  }
  function open(problem,hooks){
    if(!problem?.id||problem.standalone||window.__DEMO_VERSION__)return;
    const form=document.querySelector('#problem-form');if(!form)return;
    if(current)flush(current,true);
    const panel=node('section');panel.id='problem-recovery-panel';panel.className='recovery-panel';panel.hidden=true;panel.setAttribute('aria-label','本机恢复草稿');
    const status=node('p');status.id='problem-recovery-status';status.className='error-banner';status.setAttribute('role','status');status.hidden=true;
    form.before(panel,status);
    const s=current={id:problem.id,version:problem.version,problem,disk:dataOf(problem),hooks,form,panel,status,windowId:uid(),key:null,last:null,pending:null,timer:null,source:null,deleted:false};
    project().then(projectId=>{if(!active(s))return;s.projectId=projectId;s.key=keyFor(s);showOffer(s);if(s.pending)flush(s,true);}).catch(error=>{if(active(s))warn(s,error);});
  }
  function saved(problem){
    const s=current;if(!s||!active(s)||problem.id!==s.id)return;
    if(s.timer){clearTimeout(s.timer);s.timer=null;}
    let local;try{local=dataOf(s.hooks.capture());}catch(error){warn(s,error);return;}
    s.problem=problem;s.version=problem.version;s.disk=dataOf(problem);s.pending=null;
    try{
      if(same(local,s.disk)){if(s.key)localStorage.removeItem(s.key);if(s.source&&same(s.source.value,s.disk))removeRow(s.source);s.last=s.disk;}
      else store(s,local);
      s.source=null;showOffer(s);
    }catch(error){s.pending=local;warn(s,error);}
  }
  function reconcile(problems){
    if(!Array.isArray(problems))return;
    const ids=new Set(problems.map(problem=>problem.id)),revision=++inventoryRevision;
    project().then(projectId=>{
      if(revision!==inventoryRevision)return;
      for(const key of keys(prefix+encodeURIComponent(projectId)+':')){try{const value=JSON.parse(localStorage.getItem(key));if(value.projectId===projectId&&!ids.has(value.problemId))localStorage.removeItem(key);}catch(_){}}
      if(current&&current.projectId===projectId&&!ids.has(current.id))current.deleted=true;
    }).catch(()=>{});
  }
  document.addEventListener('input',event=>{if(event.target.matches('#code-input,#editor-mistake-note,#cph-input,#cph-expected-output'))queue();});
  document.addEventListener('click',event=>{if(event.target.closest('[data-add-cph-test],[data-remove-cph-test],[data-cph-case]'))queue();});
  document.addEventListener('change',event=>{if(event.target.id==='cph-import-file')queue();});
  window.addEventListener('pagehide',()=>flush());
  window.addEventListener('storage',event=>{
    if(!current?.projectId||!event.key?.startsWith(projectPrefix(current.projectId,current.id)))return;
    if(current.panel.dataset.mode!=='conflict')showOffer(current);
  });
  window.problemDraftRecovery={open,saved,conflict,reconcile,flush};
})();
