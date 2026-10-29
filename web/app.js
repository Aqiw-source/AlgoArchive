'use strict';
(() => {
  const $ = (q, root = document) => root.querySelector(q);
  const main = $('#main');
  const modal = $('#modal');
  const csrf = $('meta[name="csrf-token"]').content;
  const userName = ($('meta[name="user-name"]')?.content || '本地用户').trim();
  const platforms = {codeforces: 'Codeforces', atcoder: 'AtCoder', luogu: '洛谷', niuke: '牛客'};
  const knownPlatform = value => Object.prototype.hasOwnProperty.call(platforms, value);
  const platformKey = value => {
    const key=String(value || '').trim().toLocaleLowerCase();
    if(key==='洛谷')return 'luogu';
    if(key==='牛客'||key==='nowcoder')return 'niuke';
    return key;
  };
  const platformLabel = value => {
    const key=platformKey(value);
    return knownPlatform(key) ? platforms[key] : value || '';
  };
  const languages = {cpp: 'C++', python: 'Python', java: 'Java', other: '其他'};
  const extensions = {cpp: '.cpp', python: '.py', java: '.java', other: '.txt'};
  const PLAYGROUND_DRAFT_KEY = 'algoarchive.compiler-playground.v1';
  const PLAYGROUND_DEFAULT_CODE = '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n';
  const state = {contests: [], problems: [], algorithms: [], profile: {name: '', avatar: ''}, route: '', editor: null, filter: {q: '', platform: '', contest: '', language: ''}, context: {}, busy: false, problemOrderVersion: 1, settings: null, backups: [], cph: {active: 0, results: {}, running: false, runId: ''}};
  let navigating = false;
  let renderNumber = 0;
  let draggedAlgorithmProblemId = null;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const validAvatarData = v => typeof v === 'string' && /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(v);
  const avatarSource = v => typeof v === 'string' && (validAvatarData(v) || /^\/api\/profile\/avatar\?v=\d+$/.test(v)) ? v : '';
  function paintAvatar(el, avatar) {
    const image = avatarSource(avatar);
    el.textContent = '';
    el.classList.toggle('has-image', !!image);
    el.style.backgroundImage = image ? `url("${image}")` : '';
  }
  function renderProfile(profile=state.profile) {
    const name = String(profile?.name || userName || '本地用户').trim() || '本地用户';
    paintAvatar($('#profile-avatar'), profile?.avatar);
    $('#profile-name').textContent = name;
  }
  renderProfile({name:userName,avatar:''});
  const time = v => { if (!v) return '—'; const d = new Date(v); return Number.isNaN(d.valueOf()) ? '—' : new Intl.DateTimeFormat('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d); };
  const safeURL = v => { try { const u = new URL(v); return ['https:','http:'].includes(u.protocol) ? esc(u.href) : '#'; } catch (_) { return '#'; } };
  const badge = p => {
    const key=platformKey(p);
    return `<span class="platform-badge ${knownPlatform(key) ? esc(key) : 'custom'}">${esc(platformLabel(p))}</span>`;
  };
  const external = (url, label = '原题 ↗') => `<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  const option = (value,label,selected) => `<option value="${esc(value)}"${String(value)===String(selected)?' selected':''}>${esc(label)}</option>`;
  const problemName = p => p.name || p.number || '未命名题目';
  const problemTitleLink = p => {
    const href = safeURL(p.url);
    const unavailable = href === '#' ? ' data-problem-origin-unavailable="true"' : '';
    return `<a class="title-link" href="${href}" target="_blank" rel="noopener noreferrer" title="打开原题"${unavailable}>${esc(problemName(p))}</a>`;
  };
  const snippetName = p => p.title || '未命名模板';
  const algorithmButton = a => `<button class="title-link" data-open-algorithm="${esc(a.id)}">${esc(a.name)}</button>`;
  const sortedProblems = items => [...items].sort((a,b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const sortedAlgorithmProblems = items => [...items].sort((a,b) => (Number(a.algorithm_order) || 0) - (Number(b.algorithm_order) || 0));
  const sortedGlobalProblems = items => [...items].sort((a,b) => (Number(a.global_order) || 0) - (Number(b.global_order) || 0));
  const sortedContests = items => [...items].sort((a,b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const sortedAlgorithms = items => [...items].sort((a,b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  function problemPlatformOptions() {
    const entries = Object.entries(platforms), seen = new Set(Object.keys(platforms));
    state.problems.forEach(problem => {
      const value = String(problem.platform || '').trim();
      const key = platformKey(value);
      if (value && !seen.has(key)) { seen.add(key); entries.push([key, value]); }
    });
    return entries;
  }
  function contestPlatformOptions() {
    const entries = Object.entries(platforms), seen = new Set(Object.keys(platforms));
    state.contests.forEach(contest => {
      const value = String(contest.platform || '').trim();
      const key = platformKey(value);
      if (value && !seen.has(key)) { seen.add(key); entries.push([key, value]); }
    });
    return entries;
  }
  const editorShortcutHints = () => '<span class="editor-tab-hint">Tab 缩进</span><span class="editor-shortcut" aria-label="保存快捷键：Ctrl 或 Command 加 S"><kbd>Ctrl</kbd><span>/</span><kbd>⌘</kbd><span>+</span><kbd>S</kbd><b>保存</b></span>';

  async function api(path, method='GET', payload) {
    const config = {method, headers: {'Accept':'application/json'}, cache:'no-store'};
    if (method !== 'GET') { config.headers['X-CSRF-Token'] = csrf; config.headers['Content-Type'] = 'application/json'; config.body = JSON.stringify(payload || {}); }
    let response;
    try { response = await fetch(path, config); } catch (_) { throw new Error('无法连接本地服务。请确认启动窗口仍在运行，然后重试。'); }
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('本地服务返回了无法读取的内容，请重新打开程序。'); }
    if (!response.ok) { const e = new Error(data.error || '操作未完成，请重试。'); Object.assign(e, data); e.status = response.status; throw e; }
    return data;
  }
  async function loadState() {
    const data = await api('/api/state'); state.contests = data.contests || []; state.problems = data.problems || []; state.algorithms = data.algorithms || [];
    state.problemOrderVersion = Number(data.problem_order_version) || 1;
    state.profile = data.profile || {name:'',avatar:''}; renderProfile(state.profile);
    $('#nav-contests').textContent = state.contests.length; $('#nav-problems').textContent = state.problems.length; $('#nav-algorithms').textContent = state.algorithms.length;
  }
  function toast(message, error=false) {
    const el = document.createElement('div'); el.className = `toast${error?' error':''}`; el.textContent = message;
    $('#toast-area').append(el); setTimeout(() => el.remove(), 4300);
  }
  function readEditorForm() {
    if (!state.editor) return null;
    if (state.editor.kind === 'snippet') return readSnippetForm();
    if (state.editor.entity?.standalone) return readPlaygroundForm();
    return readProblemForm();
  }
  function cphTestsDirty() {
    return state.editor?.kind==='problem' && state.editor.initialTests!==JSON.stringify(state.editor.tests||[]);
  }
  function isDirty() {
    const current=readEditorForm();
    const timeDirty=state.editor?.entity?.standalone&&Number($('#cph-time-limit')?.value||3000)!==Number(state.editor.initialTimeLimit||3000);
    return !!state.editor&&((!!current&&state.editor.initial!==JSON.stringify(current))||cphTestsDirty()||timeDirty);
  }
  function allowLeave() { return !isDirty() || window.confirm('当前有尚未保存的代码或测试用例。确定放弃修改并离开吗？'); }
  async function go(route, {force=false}={}) {
    if (state.busy) { toast('正在保存，请稍候。'); return; }
    if (!force && route !== state.route && !allowLeave()) return;
    state.editor = null; state.route = route; navigating = true; location.hash = route;
    setTimeout(() => { navigating = false; }, 0); await renderRoute(route);
  }
  function pageHeader(title, desc, actions='', eyebrow='我的算法档案') {
    return `<header class="page-header"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div><div class="header-actions">${actions}</div></header>`;
  }
  function addProblemButton(contest='', platform='', algorithm='') { return `<button class="btn primary" data-new-problem="${esc(contest)}" data-platform="${esc(platform)}" data-new-algorithm="${esc(algorithm)}"><span class="plus">+</span> 添加题目</button>`; }
  function addContestButton(platform='') { return `<button class="btn" data-new-contest="${esc(platform)}"><span class="plus">+</span> 新建比赛</button>`; }
  function addAlgorithmButton() { return `<button class="btn" data-new-algorithm><span class="plus">+</span> 新建算法</button>`; }
  function empty(title, desc, button='', compact=false) { return `<div class="empty${compact?' compact':''}"><div class="empty-symbol">⌘</div><h3>${esc(title)}</h3><p>${esc(desc)}</p>${button}</div>`; }
  function problemTable(items, filtered=false) {
    if (!items.length) return empty(filtered?'没有找到匹配的题目':'还没有题目',filtered?'试着调整关键词或筛选条件。':'保存第一份解答，从这里开始积累。',filtered?'':addProblemButton(state.context.contest || '',state.context.platform || '',state.context.algorithm || ''));
    return `<div class="table-wrap"><table><thead><tr><th>题目名称与编号</th><th>平台</th><th>所属比赛</th><th>所属算法</th><th>语言</th><th>最近修改</th><th>操作</th></tr></thead><tbody>${items.map(p => `<tr class="problem-row-preview" data-problem-preview="${esc(p.id)}" tabindex="0" title="点击空白处查看代码" aria-label="查看「${esc(problemName(p))}」的代码"><td><div class="problem-title"><span class="number-box">${esc(p.number || '·')}</span>${problemTitleLink(p)}</div></td><td>${badge(p.platform)}</td><td class="contest-cell">${p.contest_id?`<button class="text-link" data-open-contest="${esc(p.contest_id)}">${esc(p.contest_title || '查看比赛')}</button>`:'未关联比赛'}</td><td class="contest-cell">${p.algorithm_id?`<button class="text-link" data-open-algorithm="${esc(p.algorithm_id)}">${esc(p.algorithm_name || '查看算法')}</button>`:'未关联算法'}</td><td><span class="lang-badge">${esc(languages[p.language] || p.language)}</span></td><td class="date-cell">${time(p.updated_at)}</td><td><div class="table-actions"><button class="text-link" data-open-problem="${esc(p.id)}">编辑</button>${external(p.url, '原题 ↗')}</div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function contestCards(items) {
    if (!items.length) return empty('还没有比赛','新建一场比赛，把每一道题目的思路都收好。',addContestButton(state.context.platform || ''));
    return `<div class="contest-grid">${items.map(c => `<article class="contest-card" data-open-contest="${esc(c.id)}" role="link" tabindex="0" aria-label="打开比赛：${esc(c.title)}"><div class="contest-card-top">${badge(c.platform)}<span class="muted" aria-hidden="true">▦</span></div><h3><button class="title-link" data-open-contest="${esc(c.id)}">${esc(c.title)}</button></h3><p>最近修改 ${time(c.updated_at)}</p><div class="contest-card-bottom"><span>${state.problems.filter(p=>p.contest_id===c.id).length} 道题目</span><button class="card-open" data-open-contest="${esc(c.id)}">进入比赛 <span aria-hidden="true">→</span></button></div></article>`).join('')}</div>`;
  }
  function algorithmCards(items) {
    if (!items.length) return empty('还没有算法模板','新建一个算法，在内部整理题目、代码和参考链接。',addAlgorithmButton());
    return `<div class="algorithm-grid">${items.map(a => `<article class="algorithm-card" data-open-algorithm="${esc(a.id)}" role="link" tabindex="0" aria-label="打开算法：${esc(a.name)}"><div class="algorithm-card-top"><span class="algorithm-category">${esc(a.category || '未分类')}</span><span class="muted" aria-hidden="true">{ }</span></div><h3>${algorithmButton(a)}</h3><p class="algorithm-description">${esc(a.description || '暂无说明')}</p><div class="algorithm-card-bottom"><span>${a.problem_count || 0} 道题目 · ${a.snippets.length} 份代码 · ${a.links.length} 个链接</span><button class="card-open" data-open-algorithm="${esc(a.id)}">查看算法 <span aria-hidden="true">→</span></button></div></article>`).join('')}</div>`;
  }
  function home() {
    const platformProblemCount=key=>state.problems.filter(p=>platformKey(p.platform)===key).length;
    const platformContestCount=key=>state.contests.filter(c=>platformKey(c.platform)===key).length;
    const cf = platformProblemCount('codeforces');
    const ac = platformProblemCount('atcoder');
    const lg = platformProblemCount('luogu');
    const nc = platformProblemCount('niuke');
    main.innerHTML = pageHeader('算法档案','在本地整理比赛、题目与算法模板，让积累清晰可见。',addContestButton()+addProblemButton()+addAlgorithmButton(),'WORKSPACE / 本地工作空间') +
      `<section class="stats-grid" aria-label="题库统计"><article class="stat-card"><div class="stat-label">完整比赛</div><span class="stat-mark">▦</span><div class="stat-value">${state.contests.length}</div><div class="stat-note">已保存的完整比赛</div></article><article class="stat-card"><div class="stat-label">全部题目</div><span class="stat-mark blue">≡</span><div class="stat-value">${state.problems.length}</div><div class="stat-note">统一题库，实时同步</div></article><article class="stat-card"><div class="stat-label">算法模板</div><span class="stat-mark purple">{ }</span><div class="stat-value">${state.algorithms.length}</div><div class="stat-note">${state.algorithms.reduce((n,a)=>n+a.snippets.length,0)} 份代码</div></article><article class="stat-card"><div class="stat-label">Codeforces</div><span class="stat-mark gold">CF</span><div class="stat-value">${cf}</div><div class="stat-note">${platformContestCount('codeforces')} 场比赛 · ${cf} 道题目</div></article><article class="stat-card"><div class="stat-label">AtCoder</div><span class="stat-mark purple">AC</span><div class="stat-value">${ac}</div><div class="stat-note">${platformContestCount('atcoder')} 场比赛 · ${ac} 道题目</div></article><article class="stat-card"><div class="stat-label">洛谷</div><span class="stat-mark amber">洛</span><div class="stat-value">${lg}</div><div class="stat-note">${platformContestCount('luogu')} 场比赛 · ${lg} 道题目</div></article><article class="stat-card"><div class="stat-label">牛客</div><span class="stat-mark cyan">牛</span><div class="stat-value">${nc}</div><div class="stat-note">${platformContestCount('niuke')} 场比赛 · ${nc} 道题目</div></article></section>` +
      `<section class="home-intro"><span class="home-intro-icon" aria-hidden="true">{ }</span><div class="intro-copy"><h2>一份代码，多种整理方式。</h2><p>比赛中的题目会自动收录到全部题目；从任意入口修改，始终保存同一份解答。</p></div><button class="btn" data-nav="problems">打开全部题目 <span aria-hidden="true">→</span></button></section>` +
      `<section><div class="section-head"><h2>最近编辑</h2><a href="#problems" data-nav="problems">查看全部 →</a></div><div class="panel">${problemTable(sortedProblems(state.problems).slice(0,6))}</div></section>`+
      `<section><div class="section-head"><h2>最近的算法模板</h2><a href="#algorithms" data-nav="algorithms">管理算法 →</a></div>${algorithmCards(sortedAlgorithms(state.algorithms).slice(0,3))}</section>`+
      `<section><div class="section-head"><h2>最近的比赛</h2><a href="#contests" data-nav="contests">管理比赛 →</a></div>${contestCards(sortedContests(state.contests).slice(0,3))}</section>`;
  }
  function filtersHTML() {
    const f=state.filter, ctx=state.context;
    return `<div class="filters"><label class="search-field"><span aria-hidden="true">⌕</span><input id="filter-query" aria-label="搜索题目" placeholder="搜索题目、编号或比赛…" value="${esc(f.q)}"></label>${ctx.platform?'':`<select id="filter-platform" aria-label="平台筛选">${option('','全部平台',f.platform)}${problemPlatformOptions().map(([k,v])=>option(k,v,f.platform)).join('')}</select>`}${ctx.contest?'':`<select id="filter-contest" aria-label="比赛筛选">${option('','全部比赛',f.contest)}${option('none','未关联比赛',f.contest)}${state.contests.filter(c=>!(ctx.platform||f.platform)||c.platform===(ctx.platform||f.platform)).map(c=>option(c.id,c.title,f.contest)).join('')}</select>`}<select id="filter-language" aria-label="代码语言筛选">${option('','全部语言',f.language)}${Object.entries(languages).map(([k,v])=>option(k,v,f.language)).join('')}</select></div>`;
  }
  function filteredProblems() {
    const f=state.filter, ctx=state.context, q=f.q.trim().toLocaleLowerCase();
    const items=state.problems.filter(p=>(!ctx.platform||platformKey(p.platform)===ctx.platform)&&(!ctx.contest||p.contest_id===ctx.contest)&&(!ctx.algorithm||p.algorithm_id===ctx.algorithm)&&(!f.platform||platformKey(p.platform)===platformKey(f.platform))&&(!f.language||p.language===f.language)&&(!f.contest||(f.contest==='none'?!p.contest_id:p.contest_id===f.contest))&&(!q||[p.number,p.name,p.url,p.contest_title,p.algorithm_name,platformLabel(p.platform)].join(' ').toLocaleLowerCase().includes(q)));
    if(ctx.algorithm)return sortedAlgorithmProblems(items);
    if(state.route==='problems'&&!ctx.platform)return sortedGlobalProblems(items);
    return sortedProblems(items);
  }
  function tableArea() { return `<section class="panel">${filtersHTML()}<div id="problem-table"></div><div class="table-footer" id="problem-count"></div></section>`; }
  function updateTable() {
    const rows=filteredProblems(); $('#problem-table').innerHTML=problemTable(rows,!!Object.values(state.filter).some(Boolean));
    $('#problem-count').textContent=`共 ${rows.length} 道题目 · 所有入口共享同一份代码记录`;
    prepareAlgorithmProblemDragging();
  }
  function algorithmProblemIds(){
    const algorithmId=state.context.algorithm;
    if(algorithmId)return sortedAlgorithmProblems(state.problems.filter(problem=>problem.algorithm_id===algorithmId)).map(problem=>problem.id);
    if(state.route==='problems'&&!state.context.platform)return sortedGlobalProblems(state.problems).map(problem=>problem.id);
    return [];
  }
  function clearAlgorithmDropIndicators(){
    document.querySelectorAll('.algorithm-order-row').forEach(row=>row.classList.remove('drop-before','drop-after'));
  }
  function clearAlgorithmProblemDragState(){
    clearAlgorithmDropIndicators();
    document.querySelectorAll('.algorithm-order-row').forEach(row=>row.classList.remove('is-dragging'));
    document.body.classList.remove('problem-dragging');
    draggedAlgorithmProblemId=null;
  }
  function prepareAlgorithmProblemDragging(){
    clearAlgorithmProblemDragState();
    if(!algorithmProblemIds().length)return;
    document.querySelectorAll('#problem-table tbody tr').forEach(row=>{
      const problemId=row.dataset.problemPreview;
      const title=row.querySelector('.problem-title');
      const number=title?.querySelector('.number-box');
      if(!problemId||!title||!number)return;
      row.dataset.algorithmProblemRow=problemId;
      row.classList.add('algorithm-order-row');
      const problem=state.problems.find(item=>item.id===problemId);
      const handle=document.createElement('span');
      handle.className='drag-handle';
      handle.draggable=true;
      handle.dataset.dragAlgorithmProblem=problemId;
      handle.title='拖动调整顺序';
      handle.setAttribute('role','button');
      handle.setAttribute('tabindex','0');
      handle.setAttribute('aria-label',`拖动调整「${problemName(problem||{})}」的顺序`);
      handle.textContent='⠿';
      title.insertBefore(handle,number);
    });
  }
  async function saveAlgorithmProblemOrder(problemIds,successMessage='题目顺序已更新。'){
    if(state.busy)return;
    const algorithmId=state.context.algorithm;
    const algorithm=algorithmId?state.algorithms.find(item=>item.id===algorithmId):null;
    const globalOrder=state.route==='problems'&&!state.context.platform&&!algorithmId;
    if(!algorithm&&!globalOrder)return;
    state.busy=true;
    document.body.classList.add('problem-dragging');
    try{
      if(globalOrder){
        await api('/api/problems/order','PUT',{version:state.problemOrderVersion,problem_ids:problemIds});
      }else{
        await api(`/api/algorithms/${encodeURIComponent(algorithmId)}/problems/order`,'PUT',{version:algorithm.version,problem_ids:problemIds});
      }
      await loadState();
      if(globalOrder){
        updateTable();
      }else{
        const updated=state.algorithms.find(item=>item.id===algorithmId);
        if(updated&&state.route===`algorithm/${algorithmId}`)algorithmDetail(updated);
      }
      toast(successMessage);
    }catch(error){
      if(error.status===409)await loadState();
      if(globalOrder){
        updateTable();
      }else{
        const latest=state.algorithms.find(item=>item.id===algorithmId)||algorithm;
        if(state.route===`algorithm/${algorithmId}`)algorithmDetail(latest);
      }
      toast(error.message,true);
    }finally{
      state.busy=false;
      document.body.classList.remove('problem-dragging');
      clearAlgorithmProblemDragState();
    }
  }
  function reverseAllProblemOrder(){
    if(state.busy)return;
    const ids=sortedGlobalProblems(state.problems).map(problem=>problem.id).reverse();
    if(ids.length<2)return;
    saveAlgorithmProblemOrder(ids,'题目已逆序排列。');
  }
  function allProblems(platform='') {
    state.context={platform}; state.filter={q:'',platform:'',contest:'',language:''};
    const headerActions=platform
      ? addContestButton(platform)+addProblemButton('',platform)
      : '<button class="btn" data-import-problems>导入</button><button class="btn" data-reverse-problems>逆序排列</button>'+addProblemButton('',platform);
    main.innerHTML=pageHeader(platform?platforms[platform]:'全部题目',platform?'整理这个平台的比赛与题目，沉淀每一份解答。':'比赛题目与单独添加的题目，统一搜索、查看和编辑。',headerActions,platform?'PLATFORM / 平台题库':'PROBLEMS / 统一题库')+
      (platform?`<section><div class="section-head"><h2>平台比赛</h2><span class="count-label">${state.contests.filter(c=>platformKey(c.platform)===platform).length} 场比赛</span></div>${contestCards(sortedContests(state.contests.filter(c=>platformKey(c.platform)===platform)))}</section><div class="section-head"><h2>平台题目</h2></div>`:'')+tableArea();
    updateTable();
  }
  function allContests() {
    state.context={};
    main.innerHTML=pageHeader('完整比赛','把一整场比赛的题目与代码，整理在一起。',addContestButton(),'CONTESTS / 比赛档案')+
      `<div class="cards-toolbar"><input id="contest-search" aria-label="搜索比赛" placeholder="搜索比赛标题…"><select id="contest-platform" aria-label="比赛平台筛选">${option('','全部平台','')}${contestPlatformOptions().map(([k,v])=>option(k,v,'')).join('')}</select><span id="contest-count" class="count-label"></span></div><div id="contest-list"></div>`;
    updateContests();
  }
  function updateContests() {
    const q=$('#contest-search').value.toLowerCase().trim(), platform=$('#contest-platform').value;
    const items=sortedContests(state.contests.filter(c=>(!q||c.title.toLowerCase().includes(q))&&(!platform||platformKey(c.platform)===platformKey(platform))));
    $('#contest-list').innerHTML=items.length?contestCards(items):(q||platform?empty('没有找到匹配的比赛','试着调整关键词或平台筛选。'):contestCards([])); $('#contest-count').textContent=`${items.length} 场比赛`;
  }
  function allAlgorithms() {
    state.context={};
    const categories=[...new Set(state.algorithms.map(a=>a.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
    main.innerHTML=pageHeader('算法模板','在一个算法下管理题目、多份代码和多条参考链接。',addAlgorithmButton(),'ALGORITHMS / 算法积累')+
      `<div class="cards-toolbar algorithm-toolbar"><label class="search-field"><span aria-hidden="true">⌕</span><input id="algorithm-search" aria-label="搜索算法" placeholder="搜索算法、分类或代码模板…"></label><select id="algorithm-category" aria-label="算法分类筛选">${option('','全部分类','')}${categories.map(value=>option(value,value,'')).join('')}</select><span id="algorithm-count" class="count-label"></span></div><div id="algorithm-list"></div>`;
    updateAlgorithms();
  }
  function updateAlgorithms() {
    const q=$('#algorithm-search').value.toLocaleLowerCase().trim(), category=$('#algorithm-category').value;
    const items=sortedAlgorithms(state.algorithms.filter(a=>{
      const linkedProblems=state.problems.filter(problem=>problem.algorithm_id===a.id);
      const haystack=[a.name,a.category,a.description,...a.links.map(link=>link.title),...a.snippets.map(snippet=>snippet.title),...linkedProblems.flatMap(problem=>[problem.number,problem.name,problem.url])].join(' ').toLocaleLowerCase();
      return (!q||haystack.includes(q))&&(!category||a.category===category);
    }));
    $('#algorithm-list').innerHTML=items.length?algorithmCards(items):(q||category?empty('没有找到匹配的算法','试着调整关键词或分类筛选。'):algorithmCards([]));
    $('#algorithm-count').textContent=`${items.length} 个算法`;
  }
  function snippetTable(algorithm, snippets) {
    if(!snippets.length)return empty('还没有代码模板','为这个算法添加第一份完整代码。',`<button class="btn primary" data-new-snippet="${esc(algorithm.id)}"><span class="plus">+</span> 添加代码</button>`,true);
    return `<div class="table-wrap"><table class="snippet-table"><thead><tr><th>代码模板</th><th>语言</th><th>最近修改</th><th>操作</th></tr></thead><tbody>${snippets.map(snippet=>`<tr><td><div class="problem-title"><span class="number-box">{ }</span><button class="title-link" data-open-snippet="${esc(snippet.id)}">${esc(snippetName(snippet))}</button></div></td><td><span class="lang-badge">${esc(languages[snippet.language]||snippet.language)}</span></td><td class="date-cell">${time(snippet.updated_at)}</td><td><div class="table-actions"><button class="text-link" data-open-snippet="${esc(snippet.id)}">查看 / 编辑</button></div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function algorithmDetail(algorithm) {
    if(!algorithm){missing('这个算法不存在或已经删除。');return;}
    state.context={algorithm:algorithm.id};state.filter={q:'',platform:'',contest:'',language:''};
    const links=algorithm.links.length?`<div class="link-list">${algorithm.links.map(link=>`<a class="reference-link" href="${safeURL(link.url)}" target="_blank" rel="noopener noreferrer"><span>${esc(link.title||link.url)}</span><small>${esc(link.url)}</small><b aria-hidden="true">↗</b></a>`).join('')}</div>`:'<p class="muted">还没有参考链接。</p>';
    main.innerHTML=`<a class="back-link" href="#algorithms" data-nav="algorithms">← 返回算法模板</a>`+
      pageHeader(algorithm.name,algorithm.description||'这里还没有填写算法说明。',`<button class="btn" data-edit-algorithm="${esc(algorithm.id)}">编辑算法</button>${addProblemButton('','',algorithm.id)}<button class="btn" data-new-snippet="${esc(algorithm.id)}"><span class="plus">+</span> 添加代码</button>`,'ALGORITHM / 算法详情')+
      `<div class="algorithm-info"><span class="algorithm-category">${esc(algorithm.category||'未分类')}</span><span>${algorithm.problem_count||0} 道题目</span><span>${algorithm.snippets.length} 份代码</span><span>${algorithm.links.length} 个链接</span><span>最近修改 ${time(algorithm.updated_at)}</span><button class="text-link danger-text" data-delete-algorithm="${esc(algorithm.id)}">删除算法</button></div>`+
      `<section><div class="section-head"><h2>算法题目</h2><span class="muted">拖动题目左侧手柄调整这里的显示顺序</span></div>${tableArea()}</section>`+
      `<section class="algorithm-section"><div class="section-head"><h2>参考链接</h2><span class="muted">OI Wiki、博客和文档</span></div><div class="panel algorithm-notes"><h3>算法说明</h3><p>${esc(algorithm.description||'暂无说明')}</p><h3>参考资料</h3>${links}</div></section>`+
      `<section><div class="section-head"><h2>代码模板</h2><span class="muted">每份代码独立保存</span></div><div class="panel">${snippetTable(algorithm,algorithm.snippets)}</div></section>`;updateTable();
  }
  function contestDetail(id) {
    const c=state.contests.find(c=>c.id===id);
    if(!c){missing('这场比赛不存在或已经删除。');return;}
    state.context={contest:id,platform:c.platform};state.filter={q:'',platform:'',contest:'',language:''};
    main.innerHTML=`<a class="back-link" href="#contests" data-nav="contests">← 返回完整比赛</a>`+pageHeader(c.title, '在这里保存的题目，也会同步显示在全部题目中。',`<button class="btn" data-edit-contest="${esc(id)}">编辑比赛</button>${addProblemButton(id,c.platform)}`,`${platformLabel(c.platform)} / 比赛详情`)+
      `<div class="contest-info">${badge(c.platform)}<span>${state.problems.filter(p=>p.contest_id===id).length} 道题目</span><span>创建于 ${time(c.created_at)}</span>${external(c.url,'打开比赛 ↗')}<button class="text-link" data-delete-contest="${esc(id)}">删除比赛</button></div><div class="section-head"><h2>比赛题目</h2><span class="muted">同一题目，只保存一份代码</span></div>`+tableArea();updateTable();
  }
  function missing(message) { main.innerHTML=pageHeader('记录暂不可用',message)+empty('记录不存在','请返回题库，查看最新记录。','<button class="btn primary" data-nav="problems">返回全部题目</button>'); }
  async function renderRoute(route) {
    const seq=++renderNumber;
    const navRoute=route.startsWith('contest/')?'contests':route.startsWith('problem/')||route.startsWith('new-problem')?'problems':route.startsWith('algorithm/')||route.startsWith('new-algorithm')?'algorithms':route.startsWith('snippet/')||route.startsWith('new-snippet')?'algorithms':route;
    document.querySelectorAll('[data-nav]').forEach(el=>el.classList.toggle('active',el.closest('nav')&&navRoute===el.dataset.nav));
    try {
      await loadState(); if(seq!==renderNumber)return;
      state.context={}; const [path,query='']=route.split('?'); const parts=path.split('/');
      if(path==='home'||!path) home();
      else if(path==='contests') allContests();
      else if(path==='problems') allProblems();
      else if(path==='compiler') compilerWorkspace();
      else if(path==='algorithms') allAlgorithms();
      else if(parts[0]==='platform'&&platforms[parts[1]]) allProblems(parts[1]);
      else if(parts[0]==='contest') contestDetail(parts[1]);
      else if(parts[0]==='algorithm') algorithmDetail(state.algorithms.find(a=>a.id===parts[1]));
      else if(parts[0]==='problem') {const d=await api(`/api/problems/${encodeURIComponent(parts[1])}`);if(seq!==renderNumber)return;problemEditor(d.problem);}
      else if(path==='new-problem') {const qp=new URLSearchParams(query);const c=state.contests.find(c=>c.id===qp.get('contest'));const a=state.algorithms.find(a=>a.id===qp.get('algorithm'));problemEditor({platform:c?.platform||qp.get('platform')||'codeforces',number:'',name:'',url:'',language:'cpp',code:'',contest_id:c?.id||null,algorithm_id:a?.id||null});}
      else if(path==='new-snippet') {const qp=new URLSearchParams(query);const a=state.algorithms.find(a=>a.id===qp.get('algorithm'));if(!a){missing('所属算法不存在或已经删除。');return;}snippetEditor({algorithm_id:a.id,algorithm_name:a.name,title:'',language:'cpp',code:''});}
      else if(parts[0]==='snippet') {const d=await api(`/api/algorithm-snippets/${encodeURIComponent(parts[1])}`);if(seq!==renderNumber)return;snippetEditor(d.snippet);}
      else {await go('home',{force:true});return;}
      const heading=$('h1',main)?.textContent||'首页';
      document.title='算法档案';
      const toolbarTitle=$('#toolbar-title');if(toolbarTitle)toolbarTitle.textContent=path==='home'||!path?'算法档案':heading;
      window.scrollTo(0,0);
    } catch(e) { if(seq!==renderNumber)return; main.innerHTML=pageHeader('暂时无法读取数据','请保留启动窗口运行，再尝试重新加载。')+`<div class="error-banner">${esc(e.message)}</div><button class="btn primary" data-retry>重新加载</button>`; }
  }

  function contestSelect(platform, selected) { const key=platformKey(platform); return option('','未关联比赛',selected||'')+state.contests.filter(c=>platformKey(c.platform)===key).map(c=>option(c.id,c.title,selected)).join(''); }
  function algorithmSelect(selected) { return option('','未关联算法',selected||'')+sortedAlgorithms(state.algorithms).map(a=>option(a.id,a.name,selected)).join(''); }
  function normalizeCphTests(tests) {
    if(!Array.isArray(tests)||!tests.length)return [{input:'',output:''}];
    return tests.map(item=>({input:String(item?.input??''),output:String(item?.output??'')}));
  }
  function currentCphTest() {
    if(state.editor?.kind!=='problem')return null;
    const tests=state.editor.tests;
    return tests[state.cph.active]||tests[0]||null;
  }
  function commitCphFields() {
    const test=currentCphTest();
    if(!test)return;
    const input=$('#cph-input'), output=$('#cph-expected-output');
    if(input)test.input=input.value;
    if(output)test.output=output.value;
  }
  function cphStatusLabel(status) {
    return ({passed:'通过',wrong_answer:'答案错误',runtime_error:'运行错误',time_limit:'超时',cancelled:'已停止'}[status]||status||'');
  }
  function cphTestPanel(p) {
    const tests=normalizeCphTests(p.tests);
    const active=Math.min(state.cph.active,tests.length-1);
    state.cph.active=active;
    const current=tests[active];
    const existing=!!p.id||!!p.standalone;
    return `<section class="cph-runner" aria-labelledby="cph-title"><div class="cph-runner-head"><div><div class="cph-kicker">CPH COMPATIBLE / LOCAL RUNNER</div><h2 id="cph-title">测试用例</h2><p>编译当前编辑器中的代码，不会自动提交到在线评测。</p></div><div class="cph-head-actions"><input type="file" id="cph-import-file" accept=".prob,.json,application/json" hidden><button type="button" class="btn small" data-import-cph>导入 .prob</button><button type="button" class="btn small" data-export-cph>导出 CPH</button>${p.standalone?'':`<button type="button" class="btn small" data-save-cph-tests ${existing?'':'disabled'}>保存用例</button>`}</div></div><div class="cph-case-tabs" id="cph-case-tabs" role="tablist" aria-label="测试用例">${tests.map((test,index)=>`<button type="button" class="cph-case-tab${index===active?' active':''}${state.cph.results[index]?.status?' has-'+esc(state.cph.results[index].status):''}" role="tab" aria-selected="${index===active}" data-cph-case="${index}"><span>${index+1}</span>${state.cph.results[index]?.status?`<i title="${esc(cphStatusLabel(state.cph.results[index].status))}"></i>`:''}</button>`).join('')}<button type="button" class="cph-add-case" data-add-cph-test aria-label="添加测试用例">+</button><button type="button" class="cph-remove-case" data-remove-cph-test aria-label="删除当前测试用例" ${tests.length<=1?'disabled':''}>−</button></div><div class="cph-case-editor"><label><span>输入</span><textarea id="cph-input" spellcheck="false" wrap="off" placeholder="标准输入">${esc(current.input)}</textarea></label><label><span>期望输出</span><textarea id="cph-expected-output" spellcheck="false" wrap="off" placeholder="逐行比较时忽略每行首尾空白">${esc(current.output)}</textarea></label></div><div class="cph-runbar"><label class="cph-time-limit"><span>单例时限</span><input type="number" id="cph-time-limit" min="50" max="30000" step="50" value="${Number(state.cph.timeLimit)||3000}" aria-label="单个测试用例时限（毫秒）"><b>ms</b></label><span class="cph-tests-state" id="cph-tests-state">${cphTestsDirty()?(p.standalone?'● 草稿尚未保存':'● 用例尚未保存'):(p.standalone?'✓ 草稿已保存':'✓ 用例已保存')}</span><div class="cph-run-actions"><button type="button" class="btn small" data-run-cph-current ${existing?'':'disabled'}>运行当前</button><button type="button" class="btn small primary" data-run-cph-all ${existing?'':'disabled'}>运行全部</button><button type="button" class="btn small danger" data-stop-cph hidden>停止</button></div></div><div class="cph-results" id="cph-results" aria-live="polite"></div><div class="cph-source">兼容格式与评测行为参考 <strong>CPH</strong>，原作者 <strong>Divyanshu Agrawal</strong> · <a href="https://github.com/agrawal-d/cph" target="_blank" rel="noopener noreferrer">GitHub 仓库</a> · ${esc('GPL-3.0-or-later')}。本功能为算法档案独立实现。</div></section>`;
  }
  function renderCphCaseTabs() {
    if(state.editor?.kind!=='problem')return;
    const tests=state.editor.tests;
    state.cph.active=Math.max(0,Math.min(state.cph.active,tests.length-1));
    const current=tests[state.cph.active];
    const tabs=$('#cph-case-tabs');
    if(tabs){
      tabs.innerHTML=tests.map((test,index)=>`<button type="button" class="cph-case-tab${index===state.cph.active?' active':''}${state.cph.results[index]?.status?' has-'+esc(state.cph.results[index].status):''}" role="tab" aria-selected="${index===state.cph.active}" data-cph-case="${index}"><span>${index+1}</span>${state.cph.results[index]?.status?`<i title="${esc(cphStatusLabel(state.cph.results[index].status))}"></i>`:''}</button>`).join('')+'<button type="button" class="cph-add-case" data-add-cph-test aria-label="添加测试用例">+</button><button type="button" class="cph-remove-case" data-remove-cph-test aria-label="删除当前测试用例" '+(tests.length<=1?'disabled':'')+'>−</button>';
    }
    if($('#cph-input'))$('#cph-input').value=current.input;
    if($('#cph-expected-output'))$('#cph-expected-output').value=current.output;
    updateCphTestsState();
  }
  function updateCphTestsState() {
    const el=$('#cph-tests-state');
    if(!el||state.editor?.kind!=='problem')return;
    const dirty=cphTestsDirty();
    el.className=`cph-tests-state${dirty?' dirty':''}`;
    const standalone=state.editor.entity?.standalone;
    el.textContent=dirty?(standalone?'● 草稿尚未保存':'● 用例尚未保存'):(standalone?'✓ 草稿已保存':'✓ 用例已保存');
  }
  function addCphTest() {
    if(state.editor?.kind!=='problem')return;
    commitCphFields();
    if(state.editor.tests.length>=100){toast('单道题目最多保存 100 个测试用例。',true);return;}
    state.editor.tests.push({input:'',output:''});
    state.cph.active=state.editor.tests.length-1;
    renderCphCaseTabs();
    updateSaveState();
    $('#cph-input')?.focus();
  }
  function removeCphTest() {
    if(state.editor?.kind!=='problem'||state.editor.tests.length<=1)return;
    state.editor.tests.splice(state.cph.active,1);
    state.cph.results={};
    state.cph.active=Math.max(0,state.cph.active-1);
    renderCphCaseTabs();
    renderCphResults();
    updateSaveState();
  }
  function activateCphTest(index) {
    if(state.editor?.kind!=='problem'||!Number.isInteger(index))return;
    commitCphFields();
    state.cph.active=Math.max(0,Math.min(index,state.editor.tests.length-1));
    renderCphCaseTabs();
  }
  function renderCphResults() {
    const target=$('#cph-results');
    if(!target||state.editor?.kind!=='problem')return;
    const compile=state.cph.compile;
    const results=Object.entries(state.cph.results||{}).sort((a,b)=>Number(a[0])-Number(b[0]));
    if(!compile&&!results.length){target.innerHTML='';return;}
    let html='';
    if(compile&&compile.status!=='success'){
      const setupAction=compile.status==='compiler_missing'||compile.status==='compiler_error'?`<button type="button" class="btn small primary" data-open-compiler-settings>选择 g++ 编译器</button>`:'';
      html+=`<div class="cph-compile ${esc(compile.status)}"><div><strong>${compile.status==='compiler_missing'?'未找到 C++ 编译器':'编译失败'}</strong><span>${Number(compile.elapsed_ms)||0} ms</span></div><pre>${esc(compile.stderr||compile.stdout||'编译器没有返回详细信息。')}</pre>${setupAction?`<div class="cph-compile-action">${setupAction}<span>请在设置中选择完整 MinGW 工具链里的 bin\\g++.exe。</span></div>`:''}</div>`;
    }else{
      const passed=results.filter(([,item])=>item.status==='passed').length;
      html+=`<div class="cph-summary"><strong>${passed} / ${results.length} 通过</strong><span>编译 ${Number(compile?.elapsed_ms)||0} ms${state.cph.totalMs?` · 运行 ${state.cph.totalMs} ms`:''}</span></div>`;
      const currentIndex=state.cph.active;
      const current=results.find(([index])=>Number(index)===currentIndex);
      if(current){
        const item=current[1];
        html+=`<div class="cph-result ${esc(item.status)}"><div class="cph-result-head"><span class="cph-status">${esc(cphStatusLabel(item.status))}</span><span>用例 ${Number(current[0])+1} · ${Number(item.elapsed_ms)||0} ms · 退出码 ${esc(item.return_code)}</span></div><div class="cph-output-grid"><div><span>实际输出</span><pre>${esc(item.stdout||'（空）')}</pre></div><div><span>错误输出</span><pre>${esc(item.stderr||'（空）')}</pre></div></div></div>`;
      }else{
        html+=`<div class="cph-result-note">切换到带结果标记的用例查看输出。</div>`;
      }
    }
    target.innerHTML=html;
  }
  function setCphRunning(running) {
    state.cph.running=running;
    const all=$('[data-run-cph-all]'), current=$('[data-run-cph-current]'), stop=$('[data-stop-cph]');
    if(all)all.hidden=running;
    if(current)current.hidden=running;
    if(stop)stop.hidden=!running;
  }
  function newCphRunId() {
    if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID().replace(/[^A-Za-z0-9_-]/g,'').slice(0,80);
    return `run-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
  async function runCphTests(allCases=false) {
    if(state.busy||state.cph.running||state.editor?.kind!=='problem')return;
    const problem=state.editor.entity;
    if(!problem.id&&!problem.standalone){toast('请先保存题目，再运行测试。',true);return;}
    commitCphFields();
    const tests=allCases?state.editor.tests:[currentCphTest()];
    if(!tests.length||tests.some(test=>!test)){toast('请先填写测试用例。',true);return;}
    const timeLimit=Math.max(50,Math.min(30000,Number($('#cph-time-limit')?.value)||3000));
    state.cph.timeLimit=timeLimit;
    const runId=newCphRunId();
    state.cph.runId=runId;
    state.cph.compile=null;
    state.cph.results={};
    state.cph.totalMs=0;
    setCphRunning(true);
    renderCphResults();
    try{
      const endpoint=problem.standalone?'/api/compiler/run':`/api/problems/${encodeURIComponent(problem.id)}/run`;
      const result=await api(endpoint,'POST',{run_id:runId,code:$('#code-input').value,tests,time_limit_ms:timeLimit});
      state.cph.compile=result.compile;
      state.cph.totalMs=result.elapsed_ms;
      result.cases.forEach(item=>{
        const index=allCases?item.ordinal-1:state.cph.active;
        state.cph.results[index]=item;
      });
      if(result.cancelled)toast('测试运行已停止。');
      else if(result.ok)toast(allCases?'全部测试通过。':`测试 ${state.cph.active+1} 通过。`);
      else if(result.compile?.status!=='success')toast('编译失败，请查看测试面板。',true);
      else toast('测试未通过，请查看测试面板。',true);
    }catch(error){
      state.cph.compile={status:'runner_error',elapsed_ms:0,stderr:error.message,stdout:''};
      toast(error.message,true);
    }finally{
      setCphRunning(false);
      renderCphCaseTabs();
      renderCphResults();
    }
  }
  async function stopCphTests() {
    if(!state.cph.running||!state.cph.runId)return;
    const endpoint=state.editor.entity.standalone?'/api/compiler/run/stop':`/api/problems/${encodeURIComponent(state.editor.entity.id)}/run/stop`;
    try{await api(endpoint,'POST',{run_id:state.cph.runId});toast('正在停止测试…');}
    catch(error){toast(error.message,true);}
  }
  async function saveCphTests(quiet=false) {
    if(state.busy||state.editor?.kind!=='problem')return false;
    const problem=state.editor.entity;
    if(problem.standalone)return savePlaygroundDraft(quiet);
    if(!problem.id){if(!quiet)toast('请先保存题目，再保存测试用例。',true);return false;}
    commitCphFields();
    try{
      const result=await api(`/api/problems/${encodeURIComponent(problem.id)}/tests`,'PUT',{tests:state.editor.tests});
      state.editor.tests=normalizeCphTests(result.tests);
      state.editor.initialTests=JSON.stringify(state.editor.tests);
      state.cph.active=Math.min(state.cph.active,state.editor.tests.length-1);
      renderCphCaseTabs();updateSaveState();
      if(!quiet)toast('测试用例已保存。');
      return true;
    }catch(error){toast(error.message,true);return false;}
  }
  function extractCphTests(value) {
    const items=Array.isArray(value)?value:Array.isArray(value?.tests)?value.tests:Array.isArray(value?.testcases)?value.testcases:null;
    if(!items)throw new Error('文件中没有可导入的 tests 用例。');
    const tests=items.map(item=>{
      const source=item?.testcase&&typeof item.testcase==='object'?item.testcase:item;
      if(!source||typeof source!=='object')throw new Error('CPH 用例格式不正确。');
      return {input:String(source.input??''),output:String(source.output??'')};
    });
    if(!tests.length)throw new Error('文件中没有测试用例。');
    if(tests.length>100)throw new Error('单道题目最多保存 100 个测试用例。');
    return tests;
  }
  async function importCphFile(file) {
    if(!file||state.editor?.kind!=='problem')return;
    if(file.size>10*1024*1024){toast('CPH 用例文件不能超过 10 MiB。',true);return;}
    try{
      const tests=extractCphTests(JSON.parse(await file.text()));
      state.editor.tests=tests;state.cph.active=0;state.cph.results={};state.cph.compile=null;
      renderCphCaseTabs();renderCphResults();updateSaveState();
      if(state.editor.entity.id&&await saveCphTests(true))toast(`已导入并保存 ${tests.length} 个 CPH 测试用例。`);
      else if(state.editor.entity.standalone&&await savePlaygroundDraft(true))toast(`已导入 ${tests.length} 个测试用例到代码试跑草稿。`);
      else if(!state.editor.entity.id)toast(`已导入 ${tests.length} 个测试用例，保存题目时会一并写入。`);
    }catch(error){toast(error instanceof SyntaxError?'CPH 用例文件不是有效 JSON。':error.message,true);}
    finally{const input=$('#cph-import-file');if(input)input.value='';}
  }
  function exportCphFile() {
    if(state.editor?.kind!=='problem')return;
    commitCphFields();
    const problem=state.editor.entity;
    const payload={
      name:[problem.number,problem.name].filter(Boolean).join(' - ')||'AlgoArchive CPH',
      url:problem.url||'',
      tests:state.editor.tests.map((item,index)=>({id:Date.now()+index,input:item.input,output:item.output})),
      interactive:false,
      memoryLimit:1024,
      timeLimit:Math.max(50,Math.min(30000,Number($('#cph-time-limit')?.value)||3000)),
      srcPath:problem.code_path||'main.cpp',
      group:'local',
      local:true
    };
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}));
    const link=document.createElement('a');
    const base=([problem.number,problem.name].filter(Boolean).join('-')||'code-playground').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_');
    link.href=url;link.download=`${base}.prob`;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),0);
    toast('已导出 CPH 兼容 .prob 文件。');
  }
  function readPlaygroundForm() {
    const code=$('#code-input');
    return code?{code:code.value}:null;
  }
  function loadPlaygroundDraft() {
    try{
      const value=JSON.parse(localStorage.getItem(PLAYGROUND_DRAFT_KEY)||'null');
      if(value&&typeof value==='object'){
        return {
          code:typeof value.code==='string'?value.code:PLAYGROUND_DEFAULT_CODE,
          tests:normalizeCphTests(value.tests),
          timeLimit:Math.max(50,Math.min(30000,Number(value.timeLimit)||3000))
        };
      }
    }catch(_){}
    return {code:PLAYGROUND_DEFAULT_CODE,tests:[{input:'',output:''}],timeLimit:3000};
  }
  async function savePlaygroundDraft(quiet=false) {
    if(state.editor?.kind!=='problem'||!state.editor.entity?.standalone)return false;
    commitCphFields();
    const code=$('#code-input')?.value??'';
    const timeLimit=Math.max(50,Math.min(30000,Number($('#cph-time-limit')?.value)||3000));
    const draft={format:1,code,tests:state.editor.tests.map(item=>({input:item.input,output:item.output})),timeLimit,savedAt:new Date().toISOString()};
    try{localStorage.setItem(PLAYGROUND_DRAFT_KEY,JSON.stringify(draft));}
    catch(_){toast('草稿无法写入浏览器本地存储，请先复制代码保留。',true);return false;}
    state.editor.initial=JSON.stringify({code});
    state.editor.initialTests=JSON.stringify(state.editor.tests);
    state.editor.initialTimeLimit=timeLimit;
    state.cph.timeLimit=timeLimit;
    updateSaveState();updateCphTestsState();
    if(!quiet)toast('代码试跑草稿已保存在当前浏览器。');
    return true;
  }
  function resetPlayground() {
    if(!window.confirm('确定清空代码试跑草稿吗？此操作不会影响题库中的代码。'))return;
    try{localStorage.removeItem(PLAYGROUND_DRAFT_KEY);}catch(_){}
    compilerWorkspace();
    toast('代码试跑草稿已清空。');
  }
  function compilerMissingHTML(detail='') {
    return `<div class="compiler-missing-banner"><div class="compiler-missing-mark" aria-hidden="true">!</div><div><strong>未找到 C++ 编译器</strong><p>代码试跑需要完整的 MinGW-w64 工具链。请安装或解压 MinGW，然后选择其中的 <code>bin\\g++.exe</code>。${detail?`<span>${esc(detail)}</span>`:''}</p></div><button type="button" class="btn primary" data-open-compiler-settings>选择 g++ 编译器</button></div>`;
  }
  async function refreshCompilerAvailability() {
    const target=$('#compiler-availability');
    if(!target)return;
    try{
      const result=await api('/api/settings');
      state.settings=result.settings;
      const compiler=result.settings?.compiler||{};
      target.innerHTML=compiler.available?'':compilerMissingHTML(compiler.path?'当前路径无法执行。':'');
    }catch(error){
      target.innerHTML=compilerMissingHTML(error.message);
    }
  }
  function compilerWorkspace() {
    const draft=loadPlaygroundDraft();
    let hasSavedDraft=false;
    try{hasSavedDraft=!!localStorage.getItem(PLAYGROUND_DRAFT_KEY);}catch(_){}
    const p={standalone:true,id:null,number:'',name:'代码试跑',url:'',language:'cpp',code:draft.code,tests:draft.tests,code_path:'main.cpp'};
    state.context={};
    state.cph={active:0,results:{},compile:null,running:false,runId:'',totalMs:0,timeLimit:draft.timeLimit};
    state.editor={kind:'problem',entity:{...p},tests:normalizeCphTests(draft.tests),initial:'',initialTests:JSON.stringify(normalizeCphTests(draft.tests)),initialTimeLimit:draft.timeLimit};
    main.innerHTML=pageHeader('代码试跑','在独立草稿中编译 C++ 并用多组测试数据快速验证，不会写入题库。',`<button type="button" class="btn" data-reset-playground>清空草稿</button><button type="submit" form="playground-form" class="btn primary" id="save-playground">保存草稿 <span aria-hidden="true">↵</span></button>`,'COMPILER / 本地试跑')+
      `<div id="compiler-availability" class="compiler-availability" aria-live="polite"></div><div id="editor-error" class="error-banner" role="alert"></div><form id="playground-form" class="editor-panel" novalidate><div class="editor-toolbar"><div class="editor-title"><span aria-hidden="true">&gt;_</span><strong>源代码</strong><span class="playground-language">C++ · GNU++14</span></div><div class="actions">${editorShortcutHints()}<button type="button" class="btn small" data-copy-code>复制代码</button></div></div><div class="code-editor"><div class="gutter" aria-hidden="true"><div id="line-numbers"></div></div><div class="code-stage"><div class="code-selection-band" id="code-selection-band" aria-hidden="true"></div><pre aria-hidden="true" id="highlight-pre"><code id="highlight-code"></code></pre><textarea name="code" id="code-input" aria-label="代码试跑编辑器" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off"></textarea></div></div><div class="editor-status"><span id="save-state" class="save-state saved">${hasSavedDraft?'✓ 草稿已保存':'尚未保存'}</span><span id="cursor-status">第 1 行，第 1 列</span><span id="code-file-type">UTF-8 · .cpp</span></div></form><div class="below-editor"><span>草稿只保存在当前浏览器；切题、备份和题库导出均不会包含这里的临时代码。</span><span>使用设置中的 g++ 编译器</span></div>`+
      cphTestPanel(p);
    $('#code-input').value=draft.code;
    state.editor.initial=JSON.stringify(readPlaygroundForm());
    highlightCode();updateCursor();
    const importInput=$('#cph-import-file');
    if(importInput)importInput.addEventListener('change',()=>importCphFile(importInput.files?.[0]));
    refreshCompilerAvailability();
  }
  function problemEditor(p) {
    state.context={};
    p.tests=normalizeCphTests(p.tests);
    state.cph={active:0,results:{},compile:null,running:false,runId:'',totalMs:0};
    state.editor={kind:'problem',entity:{...p},tests:normalizeCphTests(p.tests),initial:'',initialTests:JSON.stringify(normalizeCphTests(p.tests))};
    const back=p.contest_id?`contest/${p.contest_id}`:p.algorithm_id?`algorithm/${p.algorithm_id}`:'problems';
    const backLabel=p.contest_id?'返回所属比赛':p.algorithm_id?'返回所属算法':'返回全部题目';
    main.innerHTML=`<a class="back-link" href="#${esc(back)}" data-nav="${esc(back)}">← ${backLabel}</a>`+pageHeader(p.id?'题目与代码':'添加一道题目',p.id?'修改会同步到所属比赛、所属算法与全部题目。':'可以直接保存，也可以关联到已有比赛或算法。',`<button class="btn" data-nav="${esc(back)}">返回</button><button class="btn primary" type="submit" form="problem-form" id="save-problem">保存${p.id?'修改':'题目'} <span aria-hidden="true">↵</span></button>`,p.id?'EDITOR / 代码工作台':'NEW PROBLEM / 新的积累')+
      `<div id="editor-error" class="error-banner" role="alert"></div><form id="problem-form" class="editor-panel" novalidate><div class="form-grid"><label class="field"><span>所属平台 <small>可输入任意平台</small></span><input name="platform" id="editor-platform" list="problem-platform-options" required maxlength="100" autocomplete="off" placeholder="例如 Codeforces、AtCoder、洛谷、牛客" value="${esc(platformLabel(p.platform))}"><datalist id="problem-platform-options">${problemPlatformOptions().map(([k,v])=>`<option value="${esc(v)}"></option>`).join('')}</datalist></label><label class="field"><span>题目编号 <small>编号与名称至少填写一项</small></span><input name="number" maxlength="50" placeholder="例如 A、B、abc350_a" value="${esc(p.number)}"></label><label class="field"><span>题目名称 <small>可选</small></span><input name="name" maxlength="300" placeholder="给这道题一个熟悉的名字" value="${esc(p.name)}"></label><label class="field wide"><span>题目链接</span><input name="url" type="text" required maxlength="2048" placeholder="粘贴任意题目页面链接，或先填写备注" value="${esc(p.url)}"></label><label class="field"><span>所属比赛 <small>可选</small></span><select name="contest_id" id="editor-contest">${contestSelect(p.platform,p.contest_id)}</select></label><label class="field"><span>所属算法 <small>可选</small></span><select name="algorithm_id" id="editor-algorithm">${algorithmSelect(p.algorithm_id)}</select></label></div><div class="editor-toolbar"><div class="editor-title"><span aria-hidden="true">{ }</span><strong>源代码</strong><select name="language" id="editor-language" aria-label="代码语言">${Object.entries(languages).map(([k,v])=>option(k,v,p.language)).join('')}</select></div><div class="actions">${editorShortcutHints()}<button type="button" class="btn small" data-copy-code>复制代码</button></div></div><div class="code-editor"><div class="gutter" aria-hidden="true"><div id="line-numbers"></div></div><div class="code-stage"><div class="code-selection-band" id="code-selection-band" aria-hidden="true"></div><pre aria-hidden="true" id="highlight-pre"><code id="highlight-code"></code></pre><textarea name="code" id="code-input" aria-label="代码编辑器" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off"></textarea></div></div><div class="editor-status"><span id="save-state" class="save-state saved">${p.id?'已保存到本地':'尚未保存'}</span><span id="cursor-status">第 1 行，第 1 列</span><span id="code-file-type">UTF-8 · ${esc(extensions[p.language]||'.txt')}</span></div></form><div class="below-editor"><span>${p.id?`文件：${esc(p.code_path || '')} · 最近修改 ${time(p.updated_at)}`:'代码将作为真实源文件保存在项目的 data/codes 文件夹中。'}</span><div class="actions">${p.id&&p.contest_id?'<button class="btn small" data-unlink-contest>取消比赛关联</button>':''}${p.id&&p.algorithm_id?'<button class="btn small" data-unlink-algorithm>取消算法关联</button>':''}${p.id?'<button class="btn small danger" data-delete-problem>删除题目</button>':''}</div></div>`+cphTestPanel(p);
    $('#code-input').value=p.code||'';
    state.editor.initial=JSON.stringify(readProblemForm());
    highlightCode(); updateCursor();
    const importInput=$('#cph-import-file');
    if(importInput)importInput.addEventListener('change',()=>importCphFile(importInput.files?.[0]));
  }
  function readProblemForm() {
    const form=$('#problem-form'); if(!form)return null;
    const data=new FormData(form);return {platform:data.get('platform'),number:data.get('number'),name:data.get('name'),url:data.get('url'),language:data.get('language'),contest_id:data.get('contest_id')||null,algorithm_id:data.get('algorithm_id')||null,code:data.get('code')};
  }
  function snippetEditor(p) {
    state.context={};
    const back=`algorithm/${p.algorithm_id}`;
    main.innerHTML=`<a class="back-link" href="#${esc(back)}" data-nav="${esc(back)}">← 返回 ${esc(p.algorithm_name||'算法详情')}</a>`+
      pageHeader(p.id?'代码模板':'添加代码模板',p.id?'修改这份模板不会影响同一算法下的其他代码。':'为当前算法保存一份完整、可复用的代码。',`<button class="btn" data-nav="${esc(back)}">返回</button><button class="btn primary" type="submit" form="snippet-form" id="save-snippet">保存${p.id?'修改':'代码'} <span aria-hidden="true">↵</span></button>`,p.id?'SNIPPET / 代码工作台':'NEW SNIPPET / 新的模板')+
      `<div id="editor-error" class="error-banner" role="alert"></div><form id="snippet-form" class="editor-panel" novalidate><div class="form-grid"><label class="field wide"><span>模板名称</span><input name="title" required maxlength="300" placeholder="例如 单点修改 + 区间查询" value="${esc(p.title)}"></label><div class="field"><span>所属算法</span><div class="readonly-value">${esc(p.algorithm_name||'')}</div></div></div><div class="editor-toolbar"><div class="editor-title"><span aria-hidden="true">{ }</span><strong>源代码</strong><select name="language" id="editor-language" aria-label="代码语言">${Object.entries(languages).map(([k,v])=>option(k,v,p.language)).join('')}</select></div><div class="actions">${editorShortcutHints()}<button type="button" class="btn small" data-copy-code>复制代码</button></div></div><div class="code-editor"><div class="gutter" aria-hidden="true"><div id="line-numbers"></div></div><div class="code-stage"><div class="code-selection-band" id="code-selection-band" aria-hidden="true"></div><pre aria-hidden="true" id="highlight-pre"><code id="highlight-code"></code></pre><textarea name="code" id="code-input" aria-label="代码编辑器" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off"></textarea></div></div><div class="editor-status"><span id="save-state" class="save-state saved">${p.id?'已保存到本地':'尚未保存'}</span><span id="cursor-status">第 1 行，第 1 列</span><span id="code-file-type">UTF-8 · ${esc(extensions[p.language]||'.txt')}</span></div></form><div class="below-editor"><span>${p.id?`文件：${esc(p.code_path||'')} · 最近修改 ${time(p.updated_at)}`:'代码将作为独立源文件保存在本地数据目录。'}</span><div class="actions">${p.id?'<button class="btn small danger" data-delete-snippet>删除代码模板</button>':''}</div></div>`;
    $('#code-input').value=p.code||'';
    state.editor={kind:'snippet',entity:{...p},initial:''};state.editor.initial=JSON.stringify(readSnippetForm());
    highlightCode();updateCursor();
  }
  function readSnippetForm() {
    const form=$('#snippet-form');if(!form)return null;
    const data=new FormData(form);return {title:data.get('title'),language:data.get('language'),code:data.get('code')};
  }
  function clearFieldError(element) {
    const field=element.closest('.field');if(!field)return;
    field.classList.remove('is-invalid');
    field.querySelector('.field-error')?.remove();
    element.removeAttribute('aria-invalid');
    element.removeAttribute('aria-describedby');
  }
  function validateRequiredFields(form) {
    form.querySelectorAll('.field.is-invalid').forEach(field=>{
      const control=field.querySelector('input,select,textarea');
      if(control)clearFieldError(control);
    });
    for(const element of form.querySelectorAll('[required]')){
      if(String(element.value||'').trim())continue;
      const field=element.closest('.field');
      if(!field)continue;
      const label=field.querySelector(':scope > span')?.childNodes[0]?.textContent?.trim()||'此字段';
      const error=document.createElement('span');
      const errorId=`${form.id||'form'}-${element.name||element.id||'field'}-error`;
      error.className='field-error';error.id=errorId;error.textContent=`请填写${label}。`;
      field.classList.add('is-invalid');field.appendChild(error);
      element.setAttribute('aria-invalid','true');element.setAttribute('aria-describedby',errorId);
      element.focus();
      return false;
    }
    return true;
  }
  const keywords=new Set('alignas alignof and asm auto bool break case catch char class const constexpr continue default delete do double else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept nullptr operator private protected public register reinterpret_cast return short signed sizeof static static_assert static_cast struct switch template this throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while include define elif endif pragma import from def lambda pass True False None in is not or as assert async await del except finally global nonlocal raise with yield abstract boolean byte extends final implements instanceof interface native package strictfp super synchronized throws transient var record sealed permits'.split(' '));
  const types=new Set('std string vector map set unordered_map unordered_set pair tuple queue deque stack priority_queue cin cout endl size_t null print range len self list dict input main System String Scanner ArrayList HashMap HashSet List Map Set'.split(' '));
  function highlightSource(code,lang) {
    if(lang==='other') return esc(code)+'\n';
    {
      const python=lang==='python';
      const token=python?/(#[^\n]*|"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g:/(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|^\s*#[^\n]*|\b\d+(?:\.\d+)?(?:[uUlLfF]+)?\b|\b[A-Za-z_]\w*\b)/gm;
      let result='',last=0,m;
      while((m=token.exec(code))!==null){result+=esc(code.slice(last,m.index));const v=m[0];let type='';if(v.startsWith('//')||v.startsWith('/*')||(python&&v.startsWith('#')))type='comment';else if(/^\s*#/.test(v))type='preprocessor';else if(v[0]==='"'||v[0]==="'")type='string';else if(/^\d/.test(v))type='number';else if(keywords.has(v))type='keyword';else if(types.has(v))type='type';result+=type?`<span class="tok-${type}">${esc(v)}</span>`:esc(v);last=m.index+v.length;}
      return result+esc(code.slice(last))+'\n';
    }
  }
  function highlightCode() {
    const area=$('#code-input');if(!area)return;const code=area.value,lang=$('#editor-language')?.value||state.editor?.entity?.language||'cpp';
    $('#highlight-code').innerHTML=highlightSource(code,lang);
    $('#line-numbers').textContent=Array.from({length:code.split('\n').length},(_,i)=>i+1).join('\n'); syncScroll(); updateSaveState();
  }
  function syncScroll(){const area=$('#code-input');if(!area)return;$('#highlight-pre').scrollTop=area.scrollTop;$('#highlight-pre').scrollLeft=area.scrollLeft;$('#line-numbers').style.transform=`translateY(${-area.scrollTop}px)`;}
  function updateCursor(){const a=$('#code-input');if(!a)return;const before=a.value.slice(0,a.selectionStart).split('\n');$('#cursor-status').textContent=`第 ${before.length} 行，第 ${before[before.length-1].length+1} 列 · ${a.value.length.toLocaleString()} 字符`;}
  function updateSaveState(){const status=$('#save-state');if(!status||!state.editor)return;const dirty=isDirty();const standalone=state.editor.entity?.standalone;status.className=`save-state ${dirty?'dirty':'saved'}`;status.textContent=dirty?'● 有未保存的修改':(standalone?'✓ 草稿已保存':(state.editor.entity.id?'✓ 已保存到本地':'尚未保存'));}
  function showEditorError(e){const el=$('#editor-error');el.innerHTML=esc(e.message)+(e.existing_id?`<br><button class="text-link" data-open-problem="${esc(e.existing_id)}">打开已有题目 →</button>（当前内容尚未保存）`:'')+(e.status===409&&!e.existing_id?' 请先复制当前代码，再重新打开当前记录查看最新内容。':'');el.scrollIntoView({block:'nearest',behavior:'smooth'});}
  async function saveProblem(event){event?.preventDefault();if(state.busy||!state.editor)return;const form=$('#problem-form');if(!validateRequiredFields(form))return;const data=readProblemForm();if(!data.number.trim()&&!data.name.trim()){showEditorError(new Error('题目编号与题目名称至少填写一项。'));return;}
    commitCphFields();const testsToSave=state.editor.tests.map(item=>({input:item.input,output:item.output}));const testsDirty=cphTestsDirty();
    state.busy=true;form.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=true;});const button=$('#save-problem');button.disabled=true;button.textContent='正在保存…';$('#editor-error').textContent='';
    try{const old=state.editor.entity;if(old.id&&testsDirty)await api(`/api/problems/${encodeURIComponent(old.id)}/tests`,'PUT',{tests:testsToSave});const saved=await api(old.id?`/api/problems/${encodeURIComponent(old.id)}`:'/api/problems',old.id?'PUT':'POST',{...data,...(old.id?{version:old.version}:{})});if(!old.id&&testsDirty)await api(`/api/problems/${encodeURIComponent(saved.problem.id)}/tests`,'PUT',{tests:testsToSave});await loadState();state.editor=null;state.route=`problem/${saved.problem.id}`;navigating=true;location.hash=state.route;setTimeout(()=>{navigating=false;},0);problemEditor(saved.problem);toast('题目、代码与测试用例已保存，所有页面已同步。');}
    catch(e){showEditorError(e);}finally{state.busy=false;$('#problem-form')?.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=false;});if($('#save-problem')){$('#save-problem').disabled=false;$('#save-problem').innerHTML='保存修改 <span aria-hidden="true">↵</span>';}}
  }
  async function saveSnippet(event){
    event?.preventDefault();if(state.busy||!state.editor||state.editor.kind!=='snippet')return;
    const form=$('#snippet-form');if(!validateRequiredFields(form))return;
    const data=readSnippetForm();
    state.busy=true;form.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=true;});
    const button=$('#save-snippet');button.disabled=true;button.textContent='正在保存…';$('#editor-error').textContent='';
    try{
      const old=state.editor.entity;
      const saved=await api(old.id?`/api/algorithm-snippets/${encodeURIComponent(old.id)}`:`/api/algorithms/${encodeURIComponent(old.algorithm_id)}/snippets`,old.id?'PUT':'POST',{...data,...(old.id?{version:old.version}:{})});
      await loadState();state.editor=null;state.route=`snippet/${saved.snippet.id}`;navigating=true;location.hash=state.route;setTimeout(()=>{navigating=false;},0);snippetEditor(saved.snippet);toast('代码模板已保存到本地。');
    }catch(e){showEditorError(e);}
    finally{state.busy=false;$('#snippet-form')?.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=false;});if($('#save-snippet')){$('#save-snippet').disabled=false;$('#save-snippet').innerHTML='保存修改 <span aria-hidden="true">↵</span>';}}
  }
  function saveCurrentEditor(event){if(state.editor?.kind==='snippet')return saveSnippet(event);if(state.editor?.entity?.standalone){event?.preventDefault();return savePlaygroundDraft();}return saveProblem(event);}
  async function copyCode(){const area=$('#code-input');try{await navigator.clipboard.writeText(area.value);toast('代码已复制。');}catch(_){const start=area.selectionStart,end=area.selectionEnd;area.focus();area.select();const ok=document.execCommand('copy');if(ok)area.setSelectionRange(start,end);toast(ok?'代码已复制。':'请按 Ctrl + C 复制选中的代码。',!ok);}}
  function closeModal(){if(state.busy)return;modal.close();modal.innerHTML='';}
  function setModalBusy(busy){state.busy=busy;modal.querySelectorAll('button,input,select,textarea').forEach(el=>{el.disabled=busy;});}
  function dialogHeader(title){return `<div class="modal-header"><h2 id="dialog-title">${esc(title)}</h2><button type="button" class="modal-close" data-close-modal aria-label="关闭">×</button></div>`;}
  function downloadProblemImportSample(){
    const sample={
      problems:[
        {
          platform:'洛谷',
          number:'P3374',
          name:'树状数组 1',
          url:'https://www.luogu.com.cn/problem/P3374',
          language:'cpp',
          contest:'',
          algorithm:'树状数组',
          code:'#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    return 0;\n}\n'
        }
      ]
    };
    const url=URL.createObjectURL(new Blob([JSON.stringify(sample,null,2)],{type:'application/json;charset=utf-8'}));
    const link=document.createElement('a');
    link.href=url;
    link.download='algoarchive-import-template.json';
    link.click();
    setTimeout(()=>URL.revokeObjectURL(url),0);
  }
  function openProblemImport(){
    let importItems=[];
    modal.innerHTML=`<form id="problem-import-form" novalidate>${dialogHeader('导入题目')}<div class="modal-body"><p>选择 JSON 文件，单次最多导入 200 道题目。</p><div class="import-file-picker"><input type="file" id="problem-import-file" accept=".json,application/json" hidden><button type="button" class="btn" data-choose-import-file>选择 JSON 文件</button><span id="problem-import-file-name">尚未选择文件</span></div><div class="import-format"><code>{ platform, number, name, url, language, code, contest, algorithm }</code><button type="button" class="text-link" data-download-import-sample>下载示例</button></div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn primary" disabled>导入</button></div></form>`;
    modal.showModal();
    const form=$('#problem-import-form');
    const fileInput=$('#problem-import-file');
    const fileName=$('#problem-import-file-name');
    const submit=form.querySelector('button[type="submit"]');
    const showError=message=>{const el=$('#dialog-error');if(el)el.textContent=message;};
    $('[data-choose-import-file]',form).addEventListener('click',()=>fileInput.click());
    $('[data-download-import-sample]',form).addEventListener('click',downloadProblemImportSample);
    fileInput.addEventListener('change',async()=>{
      showError('');
      importItems=[];
      submit.disabled=true;
      const file=fileInput.files?.[0];
      if(!file)return;
      if(file.size>3_500_000){fileName.textContent='文件过大';showError('导入文件不能超过 3.5 MiB。');return;}
      try{
        const parsed=JSON.parse(await file.text());
        const items=Array.isArray(parsed)?parsed:parsed?.problems;
        if(!Array.isArray(items)||!items.length)throw new Error('JSON 中没有可导入的题目。');
        if(items.length>200)throw new Error('单次最多导入 200 道题目。');
        if(items.some(item=>!item||typeof item!=='object'||Array.isArray(item)))throw new Error('每道题目都必须是 JSON 对象。');
        importItems=items;
        fileName.textContent=`${file.name} · ${items.length} 道题目`;
        submit.disabled=false;
      }catch(error){
        fileName.textContent=file.name;
        showError(error instanceof SyntaxError?'JSON 格式不正确。':error.message);
      }
    });
    form.addEventListener('submit',async event=>{
      event.preventDefault();
      if(state.busy||!importItems.length)return;
      setModalBusy(true);
      showError('');
      try{
        const result=await api('/api/problems/import','POST',{problems:importItems});
        setModalBusy(false);
        closeModal();
        toast(`已导入 ${result.count} 道题目。`);
        await go('problems',{force:true});
      }catch(error){
        setModalBusy(false);
        showError(error.message);
      }
    });
  }
  async function openProblemPreview(identifier){
    if(state.busy)return;
    try{
      const data=await api(`/api/problems/${encodeURIComponent(identifier)}`);
      const problem=data.problem;
      const origin=safeURL(problem.url);
      const originAction=origin==='#'
        ? '<button type="button" class="btn" data-problem-origin-unavailable>原题链接不可用</button>'
        : `<a class="btn" href="${origin}" target="_blank" rel="noopener noreferrer">打开原题 ↗</a>`;
      modal.innerHTML=`${dialogHeader(problemName(problem))}<div class="modal-body problem-code-preview"><div class="preview-meta"><span class="number-box">${esc(problem.number||'·')}</span>${badge(problem.platform)}<span>${esc(languages[problem.language]||problem.language)}</span><span>最近修改 ${time(problem.updated_at)}</span></div><pre class="preview-code"><code>${highlightSource(problem.code||'',problem.language)}</code></pre></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>关闭</button>${originAction}</div>`;
      modal.showModal();
    }catch(error){
      toast(error.message,true);
    }
  }
  const formatBytes = value => {
    const bytes = Number(value) || 0;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
    return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GiB`;
  };
  function settingsTabButton(id,label){
    return `<button type="button" class="settings-tab" data-settings-tab="${id}">${esc(label)}</button>`;
  }
  function settingsProfileHTML(){
    const currentAvatar = avatarSource(state.profile?.avatar);
    const initialName = String(state.profile?.name || userName || '本地用户').trim() || '本地用户';
    return `<form id="profile-form" novalidate><p>头像图片保存在本机数据目录的 avatar 文件夹中。</p><div class="profile-editor"><span class="profile-avatar profile-preview" id="profile-preview" data-current-avatar="${esc(currentAvatar)}" aria-hidden="true"></span><div class="profile-upload"><strong>头像</strong><small>支持 PNG、JPEG、WebP，原文件不超过 512 KiB。</small><div class="profile-upload-actions"><button type="button" class="btn small" data-choose-avatar>选择图片</button><button type="button" class="btn small ghost" data-reset-avatar>使用默认头像</button></div><input type="file" id="profile-avatar-file" accept="image/png,image/jpeg,image/webp" hidden></div></div><label class="field profile-name-field"><span>用户名</span><input id="profile-name-input" name="name" required maxlength="50" autocomplete="nickname" value="${esc(initialName)}"></label><div id="settings-error" class="error-text" role="alert"></div><div class="settings-actions"><button type="submit" class="btn primary">保存资料</button></div></form>`;
  }
  function settingsBrowserHTML(){
    const browser=state.settings?.browser||{};
    const mode=browser.mode||'default', windowMode=browser.window_mode||'tab';
    return `<form id="browser-settings-form" novalidate><div class="settings-section-head"><div><h3>启动浏览器</h3><p>首次使用系统默认浏览器；此设置不会修改 Windows 全局默认应用。</p></div></div><label class="field"><span>浏览器</span><select name="mode" id="browser-mode">${option('default','系统默认浏览器',mode)}${option('edge','Microsoft Edge',mode)}${option('chrome','Google Chrome',mode)}${option('firefox','Mozilla Firefox',mode)}${option('custom','自定义可执行文件',mode)}</select></label><label class="field" id="browser-custom-field"><span>自定义浏览器路径 <small>仅接受本机可执行文件</small></span><input name="custom_path" id="browser-custom-path" maxlength="2048" value="${esc(browser.custom_path||'')}" placeholder="C:\\Program Files\\Browser\\browser.exe"></label><label class="field"><span>窗口模式</span><select name="window_mode" id="browser-window-mode">${option('tab','普通标签页',windowMode)}${option('app','独立应用窗口（Chrome / Edge）',windowMode)}</select></label><div id="settings-error" class="error-text" role="alert"></div><div class="settings-actions"><button type="button" class="btn" id="browser-test">测试打开</button><button type="submit" class="btn primary">保存浏览器设置</button></div></form>`;
  }
  function settingsCompilerHTML(){
    const compiler=state.settings?.compiler||{};
    const standard=compiler.standard||'gnu++14';
    const missing=compiler.available?'':`<div class="compiler-missing-banner compact"><div class="compiler-missing-mark" aria-hidden="true">!</div><div><strong>未找到 C++ 编译器</strong><p>请安装或解压完整的 MinGW-w64，然后填写其 <code>bin\\g++.exe</code> 路径。不要只复制单个 g++.exe；它需要同一工具链中的配套程序。</p></div></div>`;
    return `<form id="compiler-settings-form" novalidate><div class="settings-section-head"><div><h3>C++ 编译与运行</h3><p>默认自动使用当前 VS Code 工作区的 MinGW g++ 8.1.0，并以 GNU++14 编译。</p></div></div><div class="compiler-status ${compiler.available?'ok':'missing'}"><span>${compiler.available?'可用':'未找到'}</span><div><strong>${esc(compiler.version||'没有检测到 g++')}</strong><small>${compiler.auto_detected?'自动检测路径':'自定义路径'} · ${esc(compiler.standard||standard)}</small></div></div>${missing}<label class="field"><span>g++ 可执行文件路径 <small>留空时自动检测</small></span><input name="cpp_path" id="compiler-cpp-path" maxlength="2048" value="${esc(compiler.configured_path||'')}" placeholder="${esc(compiler.path||'D:\\mingw64\\bin\\g++.exe')}"></label><div class="settings-path"><code>${esc(compiler.path||'未找到编译器')}</code><button type="button" class="btn small" data-copy-compiler-path>复制实际路径</button></div><label class="field"><span>C++ 标准</span><select name="standard" id="compiler-standard">${(compiler.standards||['gnu++14']).map(value=>option(value,value,standard)).join('')}</select></label><div id="compiler-diagnostic" class="compiler-diagnostic" aria-live="polite"><strong>尚未运行能力检查</strong><span>检查将对 __int128、multiset 和 unordered_map 进行真实编译运行。</span></div><div id="settings-error" class="error-text" role="alert"></div><div class="settings-actions"><button type="button" class="btn" id="compiler-test">编译能力检查</button><button type="submit" class="btn primary">保存编译器设置</button></div></form>`;
  }
  function settingsDataHTML(){
    const settings=state.settings||{};
    const backups=state.backups||[];
    return `<div class="settings-section"><div class="settings-section-head"><div><h3>数据位置</h3><p>程序目录与数据目录相互独立。迁移前会自动创建完整备份。</p></div></div><div class="settings-path"><code>${esc(settings.data_dir||'')}</code><div class="actions"><button type="button" class="btn small" data-copy-settings-path="data_dir">复制路径</button><button type="button" class="btn small" data-open-data-folder>打开文件夹</button></div></div><label class="field"><span>迁移到新的完整数据目录 <small>必须是绝对路径</small></span><input id="new-data-dir" maxlength="2048" value="${esc(settings.data_dir||'')}" placeholder="D:\\AlgoArchive\\data"></label><div class="settings-hint">迁移成功后程序会退出；重新打开后会使用新目录。已有有效数据的目标目录不会被覆盖。</div><div class="settings-actions"><button type="button" class="btn" id="change-data-dir">迁移数据目录</button></div></div><div class="settings-section"><div class="settings-section-head"><div><h3>完整备份与恢复</h3><p>备份包含 SQLite 数据库、全部题目和算法代码、头像及业务设置。</p></div><button type="button" class="btn primary" id="create-backup">创建完整备份</button></div><label class="field"><span>本机备份</span><select id="backup-select">${backups.length?backups.map(item=>option(item.name,`${item.name} · ${formatBytes(item.size)}`,'')).join(''):option('','暂无备份','')}</select></label><div class="settings-actions wrap"><button type="button" class="btn" id="restore-backup" ${backups.length?'':'disabled'}>恢复所选备份</button><button type="button" class="btn" id="import-backup">导入 ZIP 备份</button><input type="file" id="backup-file" accept=".zip,application/zip" hidden></div><div class="settings-note">恢复前会先备份当前数据；备份无效或恢复失败时不会保留半完成状态。</div></div><div class="settings-section"><div class="settings-section-head"><div><h3>备份位置</h3><p>最多保留最近 20 份应用内创建的备份。</p></div></div><div class="settings-path"><code>${esc(settings.backup_dir||'')}</code><button type="button" class="btn small" data-copy-settings-path="backup_dir">复制路径</button></div></div>`;
  }
  function settingsAboutHTML(){
    const settings=state.settings||{};
    const cph=settings.cph||{};
    return `<div class="settings-section"><div class="settings-section-head"><div><h3>关于与诊断</h3><p>这些信息可用于确认作者、源代码位置并排查启动问题。</p></div></div><dl class="settings-diagnostics"><dt>应用版本</dt><dd>${esc(settings.version||'')}</dd><dt>应用作者</dt><dd>Aqiw</dd><dt>源代码</dt><dd><a href="https://github.com/Aqiw-source/AlgoArchive" target="_blank" rel="noopener noreferrer">GitHub · Aqiw-source/AlgoArchive</a></dd><dt>实际服务地址</dt><dd><code>${esc(settings.address||'')}</code></dd><dt>数据目录</dt><dd><code>${esc(settings.data_dir||'')}</code></dd><dt>配置文件</dt><dd><code>${esc(settings.config_path||'')}</code></dd><dt>数据库版本</dt><dd>${esc(settings.database_schema||'')}</dd><dt>本地日志</dt><dd><code>${esc(settings.log_path||'')}</code></dd></dl><div class="settings-actions wrap"><button type="button" class="btn" data-copy-settings-path="log_path">复制日志路径</button><button type="button" class="btn" data-open-log-folder>打开日志文件夹</button><button type="button" class="btn danger" data-shutdown-app>退出算法档案</button></div></div><div class="settings-section"><div class="settings-section-head"><div><h3>CPH 第三方声明</h3><p>测试用例格式与本地评测行为兼容 CPH；运行器由算法档案独立实现。</p></div></div><dl class="settings-diagnostics"><dt>原作者</dt><dd>${esc(cph.author||'Divyanshu Agrawal')}</dd><dt>上游仓库</dt><dd><a href="${esc(cph.repository||'https://github.com/agrawal-d/cph')}" target="_blank" rel="noopener noreferrer">${esc(cph.repository||'https://github.com/agrawal-d/cph')}</a></dd><dt>许可证</dt><dd>${esc(cph.license||'GPL-3.0-or-later')}</dd><dt>参考提交</dt><dd><code>${esc(cph.reference_commit||'')}</code></dd></dl><div class="settings-note">程序目录中的 THIRD_PARTY.txt 与 licenses/CPH-GPL-3.0.txt 保留完整来源和许可证说明。</div></div><div class="settings-section"><div class="settings-note">程序使用普通启动窗口时，也可以关闭该窗口退出。退出会等待进行中的保存完成并释放数据锁。</div></div>`;
  }
  function showSettingsTab(tab='profile'){
    const safeTab=['profile','browser','compiler','data','about'].includes(tab)?tab:'profile';
    modal.querySelectorAll('[data-settings-tab]').forEach(button=>button.classList.toggle('active',button.dataset.settingsTab===safeTab));
    const content=$('#settings-content');
    content.innerHTML=safeTab==='profile'?settingsProfileHTML():safeTab==='browser'?settingsBrowserHTML():safeTab==='compiler'?settingsCompilerHTML():safeTab==='data'?settingsDataHTML():settingsAboutHTML();
    if(safeTab==='profile')bindProfileSettings();
    else if(safeTab==='browser')bindBrowserSettings();
    else if(safeTab==='compiler')bindCompilerSettings();
    else if(safeTab==='data')bindDataSettings();
    else bindAboutSettings();
  }
  async function openSettings(tab='profile'){
    if(state.busy)return;
    try{
      const [settingsResult,backupResult]=await Promise.all([api('/api/settings'),api('/api/backups')]);
      state.settings=settingsResult.settings;state.backups=backupResult.backups||[];
      modal.innerHTML=`${dialogHeader('设置')}<div class="settings-shell"><nav class="settings-tabs" aria-label="设置分类">${settingsTabButton('profile','个人资料')}${settingsTabButton('browser','启动与浏览器')}${settingsTabButton('compiler','编译与运行')}${settingsTabButton('data','数据管理')}${settingsTabButton('about','关于与诊断')}</nav><div id="settings-content" class="settings-content"></div></div>`;
      modal.showModal();
      $('.settings-tabs',modal).addEventListener('click',event=>{
        const button=event.target.closest('[data-settings-tab]');
        if(button)showSettingsTab(button.dataset.settingsTab);
      });
      showSettingsTab(tab);
    }catch(error){toast(error.message,true);}
  }
  function bindProfileSettings(){
    const currentAvatar=avatarSource(state.profile?.avatar);
    let pendingAvatar=null,previewAvatar=currentAvatar;
    const preview=$('#profile-preview'), nameInput=$('#profile-name-input'), fileInput=$('#profile-avatar-file'), error=$('#settings-error');
    const syncPreview=()=>paintAvatar(preview,previewAvatar);
    const showError=message=>{error.textContent=message;};
    syncPreview();
    nameInput.addEventListener('input',()=>{showError('');syncPreview();});
    $('[data-choose-avatar]',modal).addEventListener('click',()=>fileInput.click());
    $('[data-reset-avatar]',modal).addEventListener('click',()=>{pendingAvatar='';previewAvatar='';showError('');syncPreview();});
    fileInput.addEventListener('change',()=>{
      const file=fileInput.files?.[0];fileInput.value='';if(!file)return;
      if(!['image/png','image/jpeg','image/webp'].includes(file.type)){showError('请选择 PNG、JPEG 或 WebP 图片。');return;}
      if(file.size>512*1024){showError('头像图片不能超过 512 KiB。');return;}
      const reader=new FileReader();
      reader.onload=()=>{
        if(!validAvatarData(reader.result)){showError('无法读取这张图片，请换一张重试。');return;}
        pendingAvatar=reader.result;previewAvatar=reader.result;showError('');syncPreview();
      };
      reader.onerror=()=>showError('无法读取这张图片，请换一张重试。');
      reader.readAsDataURL(file);
    });
    $('#profile-form').addEventListener('submit',async event=>{
      event.preventDefault();if(state.busy)return;
      if(!validateRequiredFields(event.target))return;
      const name=nameInput.value.trim();
      setModalBusy(true);error.textContent='';
      try{
        const payload={name};if(pendingAvatar!==null)payload.avatar=pendingAvatar;
        const result=await api('/api/profile','PUT',payload);
        state.profile=result.profile;renderProfile(state.profile);setModalBusy(false);closeModal();toast('头像和用户名已保存。');
      }catch(e){setModalBusy(false);error.textContent=e.message;}
    });
    nameInput.focus();
    nameInput.select();
  }
  function readBrowserSettingsForm(){
    const form=$('#browser-settings-form');
    if(!form)return null;
    return {mode:form.elements.mode.value,window_mode:form.elements.window_mode.value,custom_path:form.elements.custom_path.value.trim()};
  }
  function syncBrowserCustomField(){
    const mode=$('#browser-mode')?.value;
    const field=$('#browser-custom-field');
    if(field)field.hidden=mode!=='custom';
  }
  function bindBrowserSettings(){
    syncBrowserCustomField();
    $('#browser-mode').addEventListener('change',syncBrowserCustomField);
    $('#browser-test').addEventListener('click',async()=>{
      if(state.busy)return;
      setModalBusy(true);
      try{const result=await api('/api/settings/browser/test','POST',readBrowserSettingsForm());setModalBusy(false);toast(result.launch.message,!result.launch.ok);}
      catch(error){setModalBusy(false);const target=$('#settings-error');if(target)target.textContent=error.message;}
    });
    $('#browser-settings-form').addEventListener('submit',async event=>{
      event.preventDefault();if(state.busy)return;setModalBusy(true);
      try{const result=await api('/api/settings/browser','PUT',readBrowserSettingsForm());state.settings.browser=result.browser;setModalBusy(false);toast('浏览器设置已保存。');}
      catch(error){setModalBusy(false);const target=$('#settings-error');if(target)target.textContent=error.message;}
    });
  }
  function readCompilerSettingsForm(){
    const form=$('#compiler-settings-form');
    if(!form)return null;
    return {cpp_path:form.elements.cpp_path.value.trim(),standard:form.elements.standard.value};
  }
  function bindCompilerSettings(){
    $('[data-copy-compiler-path]')?.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(state.settings?.compiler?.path||'');toast('编译器路径已复制。');}
      catch(_){toast('无法写入剪贴板。',true);}
    });
    $('#compiler-test')?.addEventListener('click',async()=>{
      if(state.busy)return;
      setModalBusy(true);
      const target=$('#compiler-diagnostic');
      if(target)target.innerHTML='<strong>正在编译能力检查…</strong><span>临时程序会依次验证 __int128、multiset 和 unordered_map。</span>';
      try{
        const result=await api('/api/settings/compiler/test','POST',readCompilerSettingsForm());
        setModalBusy(false);
        const diagnostic=result.diagnostic||{};
        if(target)target.className=`compiler-diagnostic ${diagnostic.ok?'ok':'error'}`;
        if(target)target.innerHTML=diagnostic.ok?`<strong>三项能力检查通过</strong><span>${esc(diagnostic.standard)} · __int128 ✓ · multiset ✓ · unordered_map ✓</span>`:`<strong>能力检查未通过</strong><span>${esc(diagnostic.result?.compile?.stderr||'请检查编译器路径和 C++ 标准。')}</span>`;
        toast(diagnostic.ok?'编译器能力检查通过。':'编译器能力检查未通过。',!diagnostic.ok);
      }catch(error){
        setModalBusy(false);
        if(target){target.className='compiler-diagnostic error';target.innerHTML=`<strong>能力检查未通过</strong><span>${esc(error.message)}</span>`;}
        toast(error.message,true);
      }
    });
    $('#compiler-settings-form')?.addEventListener('submit',async event=>{
      event.preventDefault();if(state.busy)return;setModalBusy(true);
      try{
        const result=await api('/api/settings/compiler','PUT',readCompilerSettingsForm());
        state.settings.compiler=result.compiler;setModalBusy(false);showSettingsTab('compiler');toast('编译器设置已保存。');
      }catch(error){setModalBusy(false);const target=$('#settings-error');if(target)target.textContent=error.message;}
    });
  }
  async function refreshBackups(){
    const result=await api('/api/backups');state.backups=result.backups||[];
    showSettingsTab('data');
  }
  async function uploadBackupFile(file){
    if(!file)return;
    if(!file.name.toLocaleLowerCase().endsWith('.zip'))throw new Error('请选择 ZIP 备份文件。');
    if(file.size>512*1024*1024)throw new Error('备份文件不能超过 512 MiB。');
    const response=await fetch('/api/backups/upload',{method:'POST',headers:{'X-CSRF-Token':csrf,'Content-Type':'application/zip','X-Backup-Filename':encodeURIComponent(file.name)},body:file});
    let data;try{data=await response.json();}catch(_){throw new Error('备份上传返回了无效内容。');}
    if(!response.ok)throw new Error(data.error||'备份导入失败。');
    return data.backup;
  }
  function bindDataSettings(){
    modal.querySelectorAll('[data-copy-settings-path]').forEach(button=>button.addEventListener('click',async()=>{
      const value=state.settings?.[button.dataset.copySettingsPath]||'';
      try{await navigator.clipboard.writeText(value);toast('路径已复制。');}catch(_){toast('无法写入剪贴板，请手动选择路径复制。',true);}
    }));
    $('[data-open-data-folder]')?.addEventListener('click',async()=>{try{await api('/api/open-data-folder','POST',{});}catch(error){toast(error.message,true);}});
    $('#change-data-dir')?.addEventListener('click',async()=>{
      const target=$('#new-data-dir').value.trim();
      if(!target){toast('请填写新的数据目录。',true);return;}
      if(!window.confirm('迁移成功后程序会退出，重新打开时使用新目录。确定继续吗？'))return;
      setModalBusy(true);
      try{const result=await api('/api/data-directory','POST',{data_dir:target});setModalBusy(false);$('#settings-content').innerHTML=`<div class="settings-complete"><h3>数据迁移完成</h3><p>${esc(result.message)}</p><code>${esc(result.new_data_dir)}</code></div>`;toast('数据已迁移，请重新打开程序。');}
      catch(error){setModalBusy(false);toast(error.message,true);}
    });
    $('#create-backup')?.addEventListener('click',async()=>{
      if(state.busy)return;setModalBusy(true);
      try{const result=await api('/api/backups/create','POST',{});setModalBusy(false);toast(`备份已创建：${result.backup.name}`);await refreshBackups();}
      catch(error){setModalBusy(false);toast(error.message,true);}
    });
    $('#restore-backup')?.addEventListener('click',async()=>{
      const select=$('#backup-select');if(!select?.value)return;
      if(!window.confirm('恢复备份会覆盖当前数据。程序会先备份当前数据，确定继续吗？'))return;
      setModalBusy(true);
      try{const result=await api('/api/backups/restore','POST',{name:select.value,confirmed:true});setModalBusy(false);closeModal();toast('备份已恢复。');await loadState();await renderRoute(state.route);}
      catch(error){setModalBusy(false);toast(error.message,true);}
    });
    const fileInput=$('#backup-file');
    $('#import-backup')?.addEventListener('click',()=>fileInput?.click());
    fileInput?.addEventListener('change',async()=>{
      const file=fileInput.files?.[0];fileInput.value='';if(!file)return;
      setModalBusy(true);
      try{const backup=await uploadBackupFile(file);setModalBusy(false);toast(`备份已导入：${backup.name}`);await refreshBackups();}
      catch(error){setModalBusy(false);toast(error.message,true);}
    });
  }
  function bindAboutSettings(){
    modal.querySelectorAll('[data-copy-settings-path]').forEach(button=>button.addEventListener('click',async()=>{
      try{await navigator.clipboard.writeText(state.settings?.[button.dataset.copySettingsPath]||'');toast('路径已复制。');}catch(_){toast('无法写入剪贴板。',true);}
    }));
    $('[data-open-log-folder]')?.addEventListener('click',async()=>{try{await api('/api/open-log-folder','POST',{});}catch(error){toast(error.message,true);}});
    $('[data-shutdown-app]')?.addEventListener('click',async()=>{
      if(!window.confirm('确定退出算法档案吗？'))return;
      try{await api('/api/shutdown','POST',{});setModalBusy(false);$('#settings-content').innerHTML='<div class="settings-complete"><h3>程序已退出</h3><p>可以关闭这个页面，需要时重新打开算法档案。</p></div>';}
      catch(error){toast(error.message,true);}
    });
  }
  function openContestForm(id='', platform=''){
    const c=state.contests.find(c=>c.id===id)||{platform:platform||'codeforces',title:'',url:''};
    modal.innerHTML=`<form id="contest-form" class="contest-form" novalidate>${dialogHeader(id?'编辑比赛':'新建比赛')}<div class="modal-body contest-form-body"><p class="form-intro">保存比赛信息，之后可以逐题加入代码。</p><div class="contest-form-grid"><label class="field"><span>所属平台 <small>自由输入</small></span><input name="platform" id="contest-form-platform" required maxlength="100" autocomplete="off" placeholder="Codeforces、AtCoder、洛谷、牛客…" value="${esc(platformLabel(c.platform))}"></label><label class="field"><span>比赛标题</span><input name="title" required maxlength="300" placeholder="例如 Codeforces Round 1000" value="${esc(c.title)}"></label><div class="platform-presets" aria-label="常用平台"><span>常用</span><button type="button" data-platform-preset="Codeforces"><b class="preset-icon cf">CF</b>Codeforces</button><button type="button" data-platform-preset="AtCoder"><b class="preset-icon ac">AC</b>AtCoder</button><button type="button" data-platform-preset="洛谷"><b class="preset-icon lg">洛</b>洛谷</button><button type="button" data-platform-preset="牛客"><b class="preset-icon ng">牛</b>牛客</button></div><label class="field full"><span>比赛链接 <small>也可以先填写备注</small></span><input name="url" type="text" required maxlength="2048" placeholder="粘贴比赛页面链接，或填写“链接稍后补充”" value="${esc(c.url)}"></label><div id="dialog-error" class="error-text" role="alert"></div></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn primary">${id?'保存修改':'创建比赛'}</button></div></form>`;
    modal.showModal();$('#contest-form').addEventListener('submit',async event=>{event.preventDefault();if(state.busy)return;if(!validateRequiredFields(event.target))return;const f=new FormData(event.target);setModalBusy(true);try{const result=await api(id?`/api/contests/${encodeURIComponent(id)}`:'/api/contests',id?'PUT':'POST',{platform:f.get('platform'),title:f.get('title'),url:f.get('url'),...(id?{version:c.version}:{})});setModalBusy(false);closeModal();toast(id?'比赛信息已更新。':'比赛已创建，可以开始添加题目。');await go(`contest/${result.contest.id}`,{force:true});}catch(e){setModalBusy(false);const err=$('#dialog-error');if(err)err.textContent=e.message;else toast(e.message,true);}});
    modal.querySelectorAll('[data-platform-preset]').forEach(button=>button.addEventListener('click',()=>{
      const input=$('#contest-form-platform');if(!input)return;
      input.value=button.dataset.platformPreset||'';clearFieldError(input);input.focus();
    }));
  }
  function algorithmLinkRow(link={}){
    return `<div class="link-row"><input data-link-title maxlength="300" placeholder="链接名称（可选）" value="${esc(link.title||'')}"><input data-link-url type="url" maxlength="2048" placeholder="https://…" value="${esc(link.url||'')}"><button type="button" class="icon-text danger-text" data-remove-algorithm-link aria-label="移除这条链接">移除</button></div>`;
  }
  function addAlgorithmLinkRow(){
    const list=$('#algorithm-link-rows');if(!list)return;
    list.insertAdjacentHTML('beforeend',algorithmLinkRow());
    list.lastElementChild?.querySelector('[data-link-title]')?.focus();
  }
  function openAlgorithmForm(id=''){
    const algorithm=state.algorithms.find(item=>item.id===id)||{name:'',category:'',description:'',links:[]};
    const rows=algorithm.links.length?algorithm.links.map(link=>algorithmLinkRow(link)).join(''):algorithmLinkRow();
    modal.innerHTML=`<form id="algorithm-form" novalidate>${dialogHeader(id?'编辑算法':'新建算法')}<div class="modal-body"><p>算法下可以关联多道题目，并保存多份代码模板和多个参考资料。</p><label class="field"><span>算法名称</span><input name="name" required maxlength="200" placeholder="例如 树状数组" value="${esc(algorithm.name)}"></label><label class="field"><span>分类 <small>可选</small></span><input name="category" maxlength="100" placeholder="例如 数据结构" value="${esc(algorithm.category)}"></label><label class="field"><span>算法说明 <small>可选</small></span><textarea name="description" maxlength="10000" rows="4" placeholder="记录适用范围、复杂度或学习摘要">${esc(algorithm.description)}</textarea></label><div class="link-editor"><div class="link-editor-head"><strong>参考链接</strong><button type="button" class="text-link" data-add-algorithm-link>+ 添加链接</button></div><div id="algorithm-link-rows">${rows}</div></div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn primary">${id?'保存修改':'创建算法'}</button></div></form>`;
    modal.showModal();
    $('#algorithm-form').addEventListener('submit',async event=>{
      event.preventDefault();if(state.busy)return;
      if(!validateRequiredFields(event.target))return;
      const f=new FormData(event.target);
      const links=[];
      for(const row of modal.querySelectorAll('.link-row')){
        const title=row.querySelector('[data-link-title]').value.trim();
        const url=row.querySelector('[data-link-url]').value.trim();
        if(title&&!url){$('#dialog-error').textContent='填写链接名称时，也必须填写 URL。';return;}
        if(url)links.push({title,url});
      }
      setModalBusy(true);
      try{
        const payload={name:f.get('name'),category:f.get('category'),description:f.get('description'),links,...(id?{version:algorithm.version}:{})};
        const result=await api(id?`/api/algorithms/${encodeURIComponent(id)}`:'/api/algorithms',id?'PUT':'POST',payload);
        setModalBusy(false);closeModal();toast(id?'算法信息已更新。':'算法已创建，可以添加题目和代码模板。');await go(`algorithm/${result.algorithm.id}`,{force:true});
      }catch(e){setModalBusy(false);const err=$('#dialog-error');if(err)err.textContent=e.message;else toast(e.message,true);}
    });
  }
  function deleteAlgorithm(id){
    const algorithm=state.algorithms.find(item=>item.id===id);if(!algorithm)return;
    const problemCount=state.problems.filter(problem=>problem.algorithm_id===id).length;
    modal.innerHTML=`<form id="delete-algorithm-form">${dialogHeader('删除算法')}<div class="modal-body"><p>确定删除「${esc(algorithm.name)}」吗？</p><div class="danger-note">将永久删除该算法、${algorithm.links.length} 个参考链接、${algorithm.snippets.length} 份代码模板及对应源码文件。${problemCount} 道题目会保留在全部题目中，但取消与本算法的关联。此操作无法撤销。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>保留算法</button><button type="submit" class="btn danger">删除算法及全部代码</button></div></form>`;
    modal.showModal();$('#delete-algorithm-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;setModalBusy(true);try{await api(`/api/algorithms/${encodeURIComponent(id)}`,'DELETE',{version:algorithm.version,confirmed:true});setModalBusy(false);closeModal();toast('算法、链接和代码已删除。');await go('algorithms',{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function deleteSnippet(){
    const snippet=state.editor?.kind==='snippet'?state.editor.entity:null;if(!snippet?.id)return;
    modal.innerHTML=`<form id="delete-snippet-form">${dialogHeader('删除代码模板')}<div class="modal-body"><p>确定删除「${esc(snippetName(snippet))}」吗？</p><div class="danger-note">模板记录和对应源码文件将被永久删除，所属算法仍会保留。此操作无法撤销。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>保留代码</button><button type="submit" class="btn danger">删除代码模板</button></div></form>`;
    modal.showModal();$('#delete-snippet-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;setModalBusy(true);try{await api(`/api/algorithm-snippets/${encodeURIComponent(snippet.id)}`,'DELETE',{version:snippet.version,confirmed:true});setModalBusy(false);closeModal();toast('代码模板已删除。');await go(`algorithm/${snippet.algorithm_id}`,{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function deleteContest(id){
    const c=state.contests.find(c=>c.id===id);if(!c)return;const count=state.problems.filter(p=>p.contest_id===id).length;
    modal.innerHTML=`<form id="delete-contest-form">${dialogHeader('删除比赛')}<div class="modal-body"><p>即将删除「${esc(c.title)}」。请选择如何处理比赛下的 ${count} 道题目。</p><label class="choice"><input type="radio" name="mode" value="keep" checked><span>保留题目与代码<small>仅删除比赛，题目将保留在全部题目中并取消关联。</small></span></label><label class="choice"><input type="radio" name="mode" value="delete"><span>同时删除所有题目与代码<small>永久删除该比赛下的题目记录与源代码文件。</small></span></label><div class="danger-note">此操作无法撤销，请确认已保留需要的代码。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn danger">确认删除比赛</button></div></form>`;
    modal.showModal();$('#delete-contest-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;const keep=new FormData(e.target).get('mode')==='keep';if(!keep&&!window.confirm(`再次确认：将永久删除「${c.title}」及其 ${count} 道题目和对应代码文件。确定继续吗？`))return;setModalBusy(true);try{await api(`/api/contests/${encodeURIComponent(id)}`,'DELETE',{version:c.version,keep_problems:keep,confirmed:true});setModalBusy(false);closeModal();toast(keep?'比赛已删除，题目和代码已保留。':'比赛及其题目、代码已删除。');await go('contests',{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function deleteProblem(){
    const p=state.editor?.kind==='problem'?state.editor.entity:null;if(!p?.id)return;
    modal.innerHTML=`<form id="delete-problem-form">${dialogHeader('确认删除题目')}<div class="modal-body"><p>确定删除「${esc([p.number,p.name].filter(Boolean).join(' · ')||'这道题目')}」吗？</p><div class="danger-note">题目记录和对应源代码文件将被永久删除。所属比赛与全部题目中都会移除该题目，此操作无法撤销。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>保留题目</button><button type="submit" class="btn danger">删除题目及代码</button></div></form>`;
    modal.showModal();$('#delete-problem-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;setModalBusy(true);try{await api(`/api/problems/${encodeURIComponent(p.id)}`,'DELETE',{version:p.version,confirmed:true});setModalBusy(false);closeModal();toast('题目及对应代码已删除。');const back=p.contest_id?`contest/${p.contest_id}`:p.algorithm_id?`algorithm/${p.algorithm_id}`:'problems';await go(back,{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function unlinkContest(){
    if(state.editor?.kind!=='problem')return;$('#editor-contest').value='';updateSaveState();toast('已取消比赛选择。点击「保存修改」后生效，题目和代码会保留。');$('#editor-contest').focus();
  }
  function unlinkAlgorithm(){
    if(state.editor?.kind!=='problem')return;$('#editor-algorithm').value='';updateSaveState();toast('已取消算法选择。点击「保存修改」后生效，题目和代码会保留。');$('#editor-algorithm').focus();
  }
  function codeKeydown(e){
    const a=e.target;if(a.id!=='code-input'||e.isComposing||e.keyCode===229||state.busy)return;
    if(e.key==='Tab'){
      e.preventDefault();const start=a.selectionStart,end=a.selectionEnd,text=a.value;
      if(e.shiftKey||text.slice(start,end).includes('\n')){const blockStart=text.lastIndexOf('\n',start-1)+1;let blockEnd=end;const block=text.slice(blockStart,blockEnd);let firstRemoved=0,total=0;const replacement=block.split('\n').map((line,i)=>{if(e.shiftKey){const n=(line.match(/^(?: {1,4}|\t)/)||[''])[0].length;if(i===0)firstRemoved=n;total+=n;return line.slice(n);}total+=4;return '    '+line;}).join('\n');a.setRangeText(replacement,blockStart,blockEnd,'preserve');a.setSelectionRange(e.shiftKey?Math.max(blockStart,start-firstRemoved):start+4,e.shiftKey?Math.max(blockStart,end-total):end+total);}
      else a.setRangeText('    ',start,end,'end');a.dispatchEvent(new Event('input',{bubbles:true}));
    } else if(e.key==='Enter') {e.preventDefault();const start=a.selectionStart;const before=a.value.slice(0,start);const line=before.slice(before.lastIndexOf('\n')+1);let indent=(line.match(/^\s*/)||[''])[0];if(/[{:][ \t]*$/.test(line))indent+='    ';a.setRangeText('\n'+indent,a.selectionStart,a.selectionEnd,'end');a.dispatchEvent(new Event('input',{bubbles:true}));}
    requestAnimationFrame(updateCursor);
  }
  const workspaceSidebar=$('.workspace-sidebar');
  workspaceSidebar?.addEventListener('wheel',e=>{
    if(window.matchMedia('(max-width: 720px)').matches||Math.abs(e.deltaY)<=Math.abs(e.deltaX))return;
    const maxScroll=workspaceSidebar.scrollHeight-workspaceSidebar.clientHeight;
    if(maxScroll<=1){e.preventDefault();return;}
    const atTop=workspaceSidebar.scrollTop<=0;
    const atBottom=Math.ceil(workspaceSidebar.scrollTop+workspaceSidebar.clientHeight)>=workspaceSidebar.scrollHeight;
    if((e.deltaY<0&&atTop)||(e.deltaY>0&&atBottom))e.preventDefault();
  },{passive:false});
  document.addEventListener('dragstart',e=>{
    const handle=e.target.closest?.('[data-drag-algorithm-problem]');
    if(!handle||state.busy){if(handle)e.preventDefault();return;}
    const row=handle.closest('[data-algorithm-problem-row]');
    draggedAlgorithmProblemId=handle.dataset.dragAlgorithmProblem;
    e.dataTransfer.effectAllowed='move';
    e.dataTransfer.setData('text/plain',draggedAlgorithmProblemId);
    if(row){row.classList.add('is-dragging');e.dataTransfer.setDragImage(row,18,18);}
    document.body.classList.add('problem-dragging');
  });
  document.addEventListener('dragover',e=>{
    if(!draggedAlgorithmProblemId)return;
    const row=e.target.closest?.('[data-algorithm-problem-row]');
    if(!row||row.dataset.algorithmProblemRow===draggedAlgorithmProblemId)return;
    e.preventDefault();
    e.dataTransfer.dropEffect='move';
    clearAlgorithmDropIndicators();
    const rect=row.getBoundingClientRect();
    row.classList.add(e.clientY>rect.top+rect.height/2?'drop-after':'drop-before');
  });
  document.addEventListener('drop',async e=>{
    if(!draggedAlgorithmProblemId)return;
    const row=e.target.closest?.('[data-algorithm-problem-row]');
    if(!row||row.dataset.algorithmProblemRow===draggedAlgorithmProblemId)return;
    e.preventDefault();
    const dragged=draggedAlgorithmProblemId;
    const target=row.dataset.algorithmProblemRow;
    const rect=row.getBoundingClientRect();
    const after=e.clientY>rect.top+rect.height/2;
    const ids=algorithmProblemIds();
    const original=ids.join('\u0000');
    const from=ids.indexOf(dragged);
    if(from<0)return;
    ids.splice(from,1);
    const targetIndex=ids.indexOf(target);
    if(targetIndex<0)return;
    ids.splice(targetIndex+(after?1:0),0,dragged);
    clearAlgorithmProblemDragState();
    if(ids.join('\u0000')!==original)await saveAlgorithmProblemOrder(ids);
  });
  document.addEventListener('dragend',()=>clearAlgorithmProblemDragState());
  document.addEventListener('click',async e=>{
    const t=e.target.closest('button,a,[data-open-contest],[data-open-algorithm]');if(!t)return;if(state.busy){e.preventDefault();return;}
    if(t.hasAttribute('data-problem-origin-unavailable')){e.preventDefault();toast('题目保存的链接不是可打开的网址。',true);}
    else if(t.hasAttribute('data-nav')){e.preventDefault();await go(t.dataset.nav);}
    else if(t.hasAttribute('data-open-problem')){e.preventDefault();await go(`problem/${t.dataset.openProblem}`);}
    else if(t.hasAttribute('data-open-contest')){e.preventDefault();await go(`contest/${t.dataset.openContest}`);}
    else if(t.hasAttribute('data-open-algorithm')){e.preventDefault();await go(`algorithm/${t.dataset.openAlgorithm}`);}
    else if(t.hasAttribute('data-open-snippet')){e.preventDefault();await go(`snippet/${t.dataset.openSnippet}`);}
    else if(t.hasAttribute('data-import-problems')){e.preventDefault();openProblemImport();}
    else if(t.hasAttribute('data-reverse-problems')){e.preventDefault();reverseAllProblemOrder();}
    else if(t.hasAttribute('data-new-problem')){e.preventDefault();const q=new URLSearchParams();if(t.dataset.newProblem)q.set('contest',t.dataset.newProblem);if(t.dataset.platform)q.set('platform',t.dataset.platform);if(t.dataset.newAlgorithm)q.set('algorithm',t.dataset.newAlgorithm);await go(`new-problem${q.size?'?'+q:''}`);}
    else if(t.hasAttribute('data-new-contest')){if(allowLeave())openContestForm('',t.dataset.newContest);}
    else if(t.hasAttribute('data-new-algorithm')){if(allowLeave())openAlgorithmForm();}
    else if(t.hasAttribute('data-new-snippet')){e.preventDefault();await go(`new-snippet?algorithm=${encodeURIComponent(t.dataset.newSnippet)}`);}
    else if(t.hasAttribute('data-edit-algorithm'))openAlgorithmForm(t.dataset.editAlgorithm);
    else if(t.hasAttribute('data-delete-algorithm'))deleteAlgorithm(t.dataset.deleteAlgorithm);
    else if(t.hasAttribute('data-edit-contest'))openContestForm(t.dataset.editContest);
    else if(t.hasAttribute('data-delete-contest'))deleteContest(t.dataset.deleteContest);
    else if(t.hasAttribute('data-add-algorithm-link'))addAlgorithmLinkRow();
    else if(t.hasAttribute('data-remove-algorithm-link'))t.closest('.link-row')?.remove();
    else if(t.hasAttribute('data-cph-case'))activateCphTest(Number(t.dataset.cphCase));
    else if(t.hasAttribute('data-add-cph-test'))addCphTest();
    else if(t.hasAttribute('data-remove-cph-test'))removeCphTest();
    else if(t.hasAttribute('data-save-cph-tests'))await saveCphTests();
    else if(t.hasAttribute('data-run-cph-all'))await runCphTests(true);
    else if(t.hasAttribute('data-run-cph-current'))await runCphTests(false);
    else if(t.hasAttribute('data-stop-cph'))await stopCphTests();
    else if(t.hasAttribute('data-import-cph'))$('#cph-import-file')?.click();
    else if(t.hasAttribute('data-export-cph'))exportCphFile();
    else if(t.hasAttribute('data-reset-playground'))resetPlayground();
    else if(t.hasAttribute('data-copy-code'))await copyCode();
    else if(t.hasAttribute('data-delete-problem'))deleteProblem();
    else if(t.hasAttribute('data-delete-snippet'))deleteSnippet();
    else if(t.hasAttribute('data-unlink-contest'))unlinkContest();
    else if(t.hasAttribute('data-unlink-algorithm'))unlinkAlgorithm();
    else if(t.hasAttribute('data-open-compiler-settings'))await openSettings('compiler');
    else if(t.hasAttribute('data-open-profile-settings'))await openSettings('profile');
    else if(t.hasAttribute('data-close-modal'))closeModal();
    else if(t.hasAttribute('data-retry'))await renderRoute(state.route);
  });
  document.addEventListener('click',async e=>{
    const row=e.target.closest?.('.problem-row-preview');
    if(!row||state.busy||modal.open)return;
    if(e.target.closest('button,a,.drag-handle'))return;
    const selection=window.getSelection();
    if(selection&&!selection.isCollapsed&&row.contains(selection.anchorNode))return;
    await openProblemPreview(row.dataset.problemPreview);
  });
  document.addEventListener('submit',e=>{if(e.target.id==='problem-form'||e.target.id==='snippet-form'||e.target.id==='playground-form')saveCurrentEditor(e);});
  document.addEventListener('input',e=>{
    if(e.target.closest('.field'))clearFieldError(e.target);
    if(e.target.id==='filter-query'){state.filter.q=e.target.value;updateTable();}
    else if(e.target.id==='contest-search')updateContests();
    else if(e.target.id==='algorithm-search')updateAlgorithms();
    else if(e.target.id==='cph-input'||e.target.id==='cph-expected-output'){commitCphFields();updateCphTestsState();updateSaveState();}
    else if(e.target.id==='code-input'){highlightCode();updateCursor();}
    else if(e.target.id==='editor-platform'){$('#editor-contest').innerHTML=contestSelect(e.target.value,'');updateSaveState();}
    else if(e.target.id==='cph-time-limit'){state.cph.timeLimit=Math.max(50,Math.min(30000,Number(e.target.value)||3000));updateSaveState();}
    else if(e.target.closest('#problem-form'))updateSaveState();
    else if(e.target.closest('#snippet-form'))updateSaveState();
  });
  document.addEventListener('change',e=>{
    if(e.target.closest('.field'))clearFieldError(e.target);
    if(e.target.id.startsWith('filter-')&&e.target.id!=='filter-query'){
      const key=e.target.id.replace('filter-','');state.filter[key]=e.target.value;
      if(key==='platform') {state.filter.contest='';const sel=$('#filter-contest');if(sel)sel.innerHTML=option('','全部比赛','')+option('none','未关联比赛','')+state.contests.filter(c=>!state.filter.platform||c.platform===state.filter.platform).map(c=>option(c.id,c.title,'')).join('');}updateTable();
    }else if(e.target.id==='contest-platform')updateContests();
    else if(e.target.id==='algorithm-category')updateAlgorithms();
    else if(e.target.id==='editor-platform'){$('#editor-contest').innerHTML=contestSelect(e.target.value,'');updateSaveState();}
    else if(e.target.id==='editor-language'){highlightCode();$('#code-file-type').textContent=`UTF-8 · ${extensions[e.target.value]||'.txt'}`;}
    else if(e.target.closest('#problem-form'))updateSaveState();
    else if(e.target.closest('#snippet-form'))updateSaveState();
  });
  document.addEventListener('keydown',e=>{
    const previewRow=e.target.closest?.('.problem-row-preview');
    if(previewRow&&e.target===previewRow&&(e.key==='Enter'||e.key===' ')){
      e.preventDefault();
      if(!state.busy&&!modal.open)openProblemPreview(previewRow.dataset.problemPreview);
      return;
    }
    const sortHandle=e.target.closest?.('[data-drag-algorithm-problem]');
    if(sortHandle&&e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)&&!state.busy){
      e.preventDefault();
      const ids=algorithmProblemIds();
      const index=ids.indexOf(sortHandle.dataset.dragAlgorithmProblem);
      const target=index+(e.key==='ArrowUp'?-1:1);
      if(index<0||target<0||target>=ids.length)return;
      [ids[index],ids[target]]=[ids[target],ids[index]];
      saveAlgorithmProblemOrder(ids);
      return;
    }
    if((e.key==='Enter'||e.key===' ')&&e.target.matches('.contest-card[data-open-contest],.algorithm-card[data-open-algorithm]')){e.preventDefault();if(!state.busy)go(e.target.hasAttribute('data-open-contest')?`contest/${e.target.dataset.openContest}`:`algorithm/${e.target.dataset.openAlgorithm}`);return;}
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&state.editor){e.preventDefault();if(!modal.open)saveCurrentEditor();}else codeKeydown(e);
  });
  document.addEventListener('keyup',e=>{if(e.target.id==='code-input')updateCursor();});
  document.addEventListener('click',e=>{if(e.target.id==='code-input')updateCursor();});
  document.addEventListener('scroll',e=>{if(e.target.id==='code-input')syncScroll();},true);
  window.addEventListener('beforeunload',e=>{if(state.busy||isDirty()){e.preventDefault();e.returnValue='';}});
  window.addEventListener('hashchange',()=>{const route=location.hash.slice(1)||'home';if(navigating||route===state.route)return;if(state.busy||!allowLeave()){navigating=true;location.hash=state.route;setTimeout(()=>{navigating=false;},0);return;}state.editor=null;state.route=route;renderRoute(route);});
  modal.addEventListener('cancel',e=>e.preventDefault());
  state.route=location.hash.slice(1)||'home';renderRoute(state.route);
})();
