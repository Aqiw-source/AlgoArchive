'use strict';
(() => {
  const $ = (q, root = document) => root.querySelector(q);
  const main = $('#main');
  const modal = $('#modal');
  const csrf = $('meta[name="csrf-token"]').content;
  const platforms = {codeforces: 'Codeforces', atcoder: 'AtCoder'};
  const languages = {cpp: 'C++', python: 'Python', java: 'Java', other: '其他'};
  const extensions = {cpp: '.cpp', python: '.py', java: '.java', other: '.txt'};
  const state = {contests: [], problems: [], route: '', editor: null, filter: {q: '', platform: '', contest: '', language: ''}, context: {}, busy: false};
  let navigating = false;
  let renderNumber = 0;
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const time = v => { if (!v) return '—'; const d = new Date(v); return Number.isNaN(d.valueOf()) ? '—' : new Intl.DateTimeFormat('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d); };
  const safeURL = v => { try { const u = new URL(v); return ['https:','http:'].includes(u.protocol) ? esc(u.href) : '#'; } catch (_) { return '#'; } };
  const badge = p => `<span class="platform-badge ${esc(p)}">${esc(platforms[p] || p)}</span>`;
  const external = (url, label = '原题 ↗') => `<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  const option = (value,label,selected) => `<option value="${esc(value)}"${String(value)===String(selected)?' selected':''}>${esc(label)}</option>`;
  const problemName = p => p.name || p.number || '未命名题目';
  const problemButton = p => `<button class="title-link" data-open-problem="${esc(p.id)}">${esc(problemName(p))}</button>`;
  const sortedProblems = items => [...items].sort((a,b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const sortedContests = items => [...items].sort((a,b) => (b.updated_at || '').localeCompare(a.updated_at || ''));

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
    const data = await api('/api/state'); state.contests = data.contests || []; state.problems = data.problems || [];
    $('#nav-contests').textContent = state.contests.length; $('#nav-problems').textContent = state.problems.length;
  }
  function toast(message, error=false) {
    const el = document.createElement('div'); el.className = `toast${error?' error':''}`; el.textContent = message;
    $('#toast-area').append(el); setTimeout(() => el.remove(), 4300);
  }
  function isDirty() { return !!state.editor && state.editor.initial !== JSON.stringify(readProblemForm()); }
  function allowLeave() { return !isDirty() || window.confirm('这道题目有尚未保存的修改。确定放弃修改并离开吗？'); }
  async function go(route, {force=false}={}) {
    if (state.busy) { toast('正在保存，请稍候。'); return; }
    if (!force && route !== state.route && !allowLeave()) return;
    state.editor = null; state.route = route; navigating = true; location.hash = route;
    setTimeout(() => { navigating = false; }, 0); await renderRoute(route);
  }
  function pageHeader(title, desc, actions='', eyebrow='我的算法档案') {
    return `<header class="page-header"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(desc)}</p></div><div class="header-actions">${actions}</div></header>`;
  }
  function addProblemButton(contest='', platform='') { return `<button class="btn primary" data-new-problem="${esc(contest)}" data-platform="${esc(platform)}"><span class="plus">+</span> 添加题目</button>`; }
  function addContestButton(platform='') { return `<button class="btn" data-new-contest="${esc(platform)}"><span class="plus">+</span> 新建比赛</button>`; }
  function empty(title, desc, button='', compact=false) { return `<div class="empty${compact?' compact':''}"><div class="empty-symbol">⌘</div><h3>${esc(title)}</h3><p>${esc(desc)}</p>${button}</div>`; }
  function problemTable(items, filtered=false) {
    if (!items.length) return empty(filtered?'没有找到匹配的题目':'还没有题目',filtered?'试着调整关键词或筛选条件。':'保存第一份解答，从这里开始积累。',filtered?'':addProblemButton(state.context.contest || '',state.context.platform || ''));
    return `<div class="table-wrap"><table><thead><tr><th>题目名称与编号</th><th>平台</th><th>所属比赛</th><th>语言</th><th>最近修改</th><th>操作</th></tr></thead><tbody>${items.map(p => `<tr><td><div class="problem-title"><span class="number-box">${esc(p.number || '·')}</span>${problemButton(p)}</div></td><td>${badge(p.platform)}</td><td class="contest-cell">${p.contest_id?`<button class="text-link" data-open-contest="${esc(p.contest_id)}">${esc(p.contest_title || '查看比赛')}</button>`:'未关联比赛'}</td><td><span class="lang-badge">${esc(languages[p.language] || p.language)}</span></td><td class="date-cell">${time(p.updated_at)}</td><td><div class="table-actions"><button class="text-link" data-open-problem="${esc(p.id)}">查看 / 编辑</button>${external(p.url)}</div></td></tr>`).join('')}</tbody></table></div>`;
  }
  function contestCards(items) {
    if (!items.length) return empty('还没有比赛','新建一场比赛，把每一道题目的思路都收好。',addContestButton(state.context.platform || ''));
    return `<div class="contest-grid">${items.map(c => `<article class="contest-card"><div class="contest-card-top">${badge(c.platform)}<span class="muted" aria-hidden="true">▦</span></div><h3><button class="title-link" data-open-contest="${esc(c.id)}">${esc(c.title)}</button></h3><p>最近修改 ${time(c.updated_at)}</p><div class="contest-card-bottom"><span>${state.problems.filter(p=>p.contest_id===c.id).length} 道题目</span><button class="card-open" data-open-contest="${esc(c.id)}">进入比赛 <span aria-hidden="true">→</span></button></div></article>`).join('')}</div>`;
  }
  function home() {
    const cf = state.problems.filter(p=>p.platform==='codeforces').length;
    const ac = state.problems.filter(p=>p.platform==='atcoder').length;
    main.innerHTML = pageHeader('每一份解答，都值得记录。','在本地整理比赛与题目，让积累清晰可见。',addContestButton()+addProblemButton(),'WORKSPACE / 本地工作空间') +
      `<section class="stats-grid" aria-label="题库统计"><article class="stat-card"><div class="stat-label">完整比赛</div><span class="stat-mark">▦</span><div class="stat-value">${state.contests.length}</div><div class="stat-note">已保存的完整比赛</div></article><article class="stat-card"><div class="stat-label">全部题目</div><span class="stat-mark blue">≡</span><div class="stat-value">${state.problems.length}</div><div class="stat-note">统一题库，实时同步</div></article><article class="stat-card"><div class="stat-label">Codeforces</div><span class="stat-mark gold">CF</span><div class="stat-value">${cf}</div><div class="stat-note">${state.contests.filter(c=>c.platform==='codeforces').length} 场比赛 · ${cf} 道题目</div></article><article class="stat-card"><div class="stat-label">AtCoder</div><span class="stat-mark purple">AC</span><div class="stat-value">${ac}</div><div class="stat-note">${state.contests.filter(c=>c.platform==='atcoder').length} 场比赛 · ${ac} 道题目</div></article></section>` +
      `<section class="home-intro"><span class="home-intro-icon" aria-hidden="true">{ }</span><div class="intro-copy"><h2>一份代码，多种整理方式。</h2><p>比赛中的题目会自动收录到全部题目；从任意入口修改，始终保存同一份解答。</p></div><button class="btn" data-nav="problems">打开全部题目 <span aria-hidden="true">→</span></button></section>` +
      `<section><div class="section-head"><h2>最近编辑</h2><a href="#problems" data-nav="problems">查看全部 →</a></div><div class="panel">${problemTable(sortedProblems(state.problems).slice(0,6))}</div></section>`+
      `<section><div class="section-head"><h2>最近的比赛</h2><a href="#contests" data-nav="contests">管理比赛 →</a></div>${contestCards(sortedContests(state.contests).slice(0,3))}</section>`;
  }
  function filtersHTML() {
    const f=state.filter, ctx=state.context;
    return `<div class="filters"><label class="search-field"><span aria-hidden="true">⌕</span><input id="filter-query" aria-label="搜索题目" placeholder="搜索题目、编号或比赛…" value="${esc(f.q)}"></label>${ctx.platform?'':`<select id="filter-platform" aria-label="平台筛选">${option('','全部平台',f.platform)}${Object.entries(platforms).map(([k,v])=>option(k,v,f.platform)).join('')}</select>`}${ctx.contest?'':`<select id="filter-contest" aria-label="比赛筛选">${option('','全部比赛',f.contest)}${option('none','未关联比赛',f.contest)}${state.contests.filter(c=>!(ctx.platform||f.platform)||c.platform===(ctx.platform||f.platform)).map(c=>option(c.id,c.title,f.contest)).join('')}</select>`}<select id="filter-language" aria-label="代码语言筛选">${option('','全部语言',f.language)}${Object.entries(languages).map(([k,v])=>option(k,v,f.language)).join('')}</select></div>`;
  }
  function filteredProblems() {
    const f=state.filter, ctx=state.context, q=f.q.trim().toLocaleLowerCase();
    return sortedProblems(state.problems.filter(p=>(!ctx.platform||p.platform===ctx.platform)&&(!ctx.contest||p.contest_id===ctx.contest)&&(!f.platform||p.platform===f.platform)&&(!f.language||p.language===f.language)&&(!f.contest||(f.contest==='none'?!p.contest_id:p.contest_id===f.contest))&&(!q||[p.number,p.name,p.url,p.contest_title,platforms[p.platform]].join(' ').toLocaleLowerCase().includes(q))));
  }
  function tableArea() { return `<section class="panel">${filtersHTML()}<div id="problem-table"></div><div class="table-footer" id="problem-count"></div></section>`; }
  function updateTable() {
    const rows=filteredProblems(); $('#problem-table').innerHTML=problemTable(rows,!!Object.values(state.filter).some(Boolean));
    $('#problem-count').textContent=`共 ${rows.length} 道题目 · 所有入口共享同一份代码记录`;
  }
  function allProblems(platform='') {
    state.context={platform}; state.filter={q:'',platform:'',contest:'',language:''};
    main.innerHTML=pageHeader(platform?platforms[platform]:'全部题目',platform?'整理这个平台的比赛与题目，沉淀每一份解答。':'比赛题目与单独添加的题目，统一搜索、查看和编辑。', (platform?addContestButton(platform):'')+addProblemButton('',platform),platform?'PLATFORM / 平台题库':'PROBLEMS / 统一题库')+
      (platform?`<section><div class="section-head"><h2>平台比赛</h2><span class="count-label">${state.contests.filter(c=>c.platform===platform).length} 场比赛</span></div>${contestCards(sortedContests(state.contests.filter(c=>c.platform===platform)))}</section><div class="section-head"><h2>平台题目</h2></div>`:'')+tableArea();
    updateTable();
  }
  function allContests() {
    state.context={};
    main.innerHTML=pageHeader('完整比赛','把一整场比赛的题目与代码，整理在一起。',addContestButton(),'CONTESTS / 比赛档案')+
      `<div class="cards-toolbar"><input id="contest-search" aria-label="搜索比赛" placeholder="搜索比赛标题…"><select id="contest-platform" aria-label="比赛平台筛选">${option('','全部平台','')}${Object.entries(platforms).map(([k,v])=>option(k,v,'')).join('')}</select><span id="contest-count" class="count-label"></span></div><div id="contest-list"></div>`;
    updateContests();
  }
  function updateContests() {
    const q=$('#contest-search').value.toLowerCase().trim(), platform=$('#contest-platform').value;
    const items=sortedContests(state.contests.filter(c=>(!q||c.title.toLowerCase().includes(q))&&(!platform||c.platform===platform)));
    $('#contest-list').innerHTML=items.length?contestCards(items):(q||platform?empty('没有找到匹配的比赛','试着调整关键词或平台筛选。'):contestCards([])); $('#contest-count').textContent=`${items.length} 场比赛`;
  }
  function contestDetail(id) {
    const c=state.contests.find(c=>c.id===id);
    if(!c){missing('这场比赛不存在或已经删除。');return;}
    state.context={contest:id,platform:c.platform};state.filter={q:'',platform:'',contest:'',language:''};
    main.innerHTML=`<a class="back-link" href="#contests" data-nav="contests">← 返回完整比赛</a>`+pageHeader(c.title, '在这里保存的题目，也会同步显示在全部题目中。',`<button class="btn" data-edit-contest="${esc(id)}">编辑比赛</button>${addProblemButton(id,c.platform)}`,`${platforms[c.platform]} / 比赛详情`)+
      `<div class="contest-info">${badge(c.platform)}<span>${state.problems.filter(p=>p.contest_id===id).length} 道题目</span><span>创建于 ${time(c.created_at)}</span>${external(c.url,'打开比赛 ↗')}<button class="text-link" data-delete-contest="${esc(id)}">删除比赛</button></div><div class="section-head"><h2>比赛题目</h2><span class="muted">同一题目，只保存一份代码</span></div>`+tableArea();updateTable();
  }
  function missing(message) { main.innerHTML=pageHeader('记录暂不可用',message)+empty('记录不存在','请返回题库，查看最新记录。','<button class="btn primary" data-nav="problems">返回全部题目</button>'); }
  async function renderRoute(route) {
    const seq=++renderNumber;
    document.querySelectorAll('[data-nav]').forEach(el=>el.classList.toggle('active',el.closest('nav')&&((route.startsWith('contest/')?'contests':route.startsWith('problem/')||route.startsWith('new-problem')?'problems':route)===el.dataset.nav)));
    try {
      await loadState(); if(seq!==renderNumber)return;
      state.context={}; const [path,query='']=route.split('?'); const parts=path.split('/');
      if(path==='home'||!path) home();
      else if(path==='contests') allContests();
      else if(path==='problems') allProblems();
      else if(parts[0]==='platform'&&platforms[parts[1]]) allProblems(parts[1]);
      else if(parts[0]==='contest') contestDetail(parts[1]);
      else if(parts[0]==='problem') {const d=await api(`/api/problems/${encodeURIComponent(parts[1])}`);if(seq!==renderNumber)return;problemEditor(d.problem);}
      else if(path==='new-problem') {const qp=new URLSearchParams(query);const c=state.contests.find(c=>c.id===qp.get('contest'));problemEditor({platform:c?.platform||qp.get('platform')||'codeforces',number:'',name:'',url:'',language:'cpp',code:'',contest_id:c?.id||null});}
      else {await go('home',{force:true});return;}
      document.title=`${$('h1',main)?.textContent||'首页'} · 算法档案`;
      window.scrollTo(0,0);
    } catch(e) { if(seq!==renderNumber)return; main.innerHTML=pageHeader('暂时无法读取数据','请保留启动窗口运行，再尝试重新加载。')+`<div class="error-banner">${esc(e.message)}</div><button class="btn primary" data-retry>重新加载</button>`; }
  }

  function contestSelect(platform, selected) { return option('','未关联比赛',selected||'')+state.contests.filter(c=>c.platform===platform).map(c=>option(c.id,c.title,selected)).join(''); }
  function problemEditor(p) {
    state.context={};
    const back=p.contest_id?`contest/${p.contest_id}`:'problems';
    main.innerHTML=`<a class="back-link" href="#${esc(back)}" data-nav="${esc(back)}">← ${p.contest_id?'返回所属比赛':'返回全部题目'}</a>`+pageHeader(p.id?'题目与代码':'添加一道题目',p.id?'修改会同步到所属比赛与全部题目。':'可以直接保存，也可以将题目关联到已有比赛。',`<button class="btn" data-nav="${esc(back)}">返回</button><button class="btn primary" type="submit" form="problem-form" id="save-problem">保存${p.id?'修改':'题目'} <span aria-hidden="true">↵</span></button>`,p.id?'EDITOR / 代码工作台':'NEW PROBLEM / 新的积累')+
      `<div id="editor-error" class="error-banner" role="alert"></div><form id="problem-form" class="editor-panel"><div class="form-grid"><label class="field"><span>所属平台</span><select name="platform" id="editor-platform">${Object.entries(platforms).map(([k,v])=>option(k,v,p.platform)).join('')}</select></label><label class="field"><span>题目编号 <small>编号与名称至少填写一项</small></span><input name="number" maxlength="50" placeholder="例如 A、B、abc350_a" value="${esc(p.number)}"></label><label class="field"><span>题目名称 <small>可选</small></span><input name="name" maxlength="300" placeholder="给这道题一个熟悉的名字" value="${esc(p.name)}"></label><label class="field wide"><span>题目链接</span><input name="url" type="url" required maxlength="2048" placeholder="粘贴 Codeforces 或 AtCoder 题目链接" value="${esc(p.url)}"></label><label class="field"><span>所属比赛 <small>可选，可随时更改</small></span><select name="contest_id" id="editor-contest">${contestSelect(p.platform,p.contest_id)}</select></label></div><div class="editor-toolbar"><div class="editor-title"><span aria-hidden="true">{ }</span><strong>源代码</strong><select name="language" id="editor-language" aria-label="代码语言">${Object.entries(languages).map(([k,v])=>option(k,v,p.language)).join('')}</select></div><div class="actions"><span class="editor-hint">Tab 缩进 · Ctrl / ⌘ + S 保存</span><button type="button" class="btn small" data-copy-code>复制代码</button></div></div><div class="code-editor"><div class="gutter" aria-hidden="true"><div id="line-numbers"></div></div><div class="code-stage"><pre aria-hidden="true" id="highlight-pre"><code id="highlight-code"></code></pre><textarea name="code" id="code-input" aria-label="代码编辑器" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off"></textarea></div></div><div class="editor-status"><span id="save-state" class="save-state saved">${p.id?'已保存到本地':'尚未保存'}</span><span id="cursor-status">第 1 行，第 1 列</span><span id="code-file-type">UTF-8 · ${esc(extensions[p.language]||'.txt')}</span></div></form><div class="below-editor"><span>${p.id?`文件：${esc(p.code_path || '')} · 最近修改 ${time(p.updated_at)}`:'代码将作为真实源文件保存在项目的 data/codes 文件夹中。'}</span><div class="actions">${p.id&&p.contest_id?'<button class="btn small" data-unlink-problem>取消比赛关联</button>':''}${p.id?'<button class="btn small danger" data-delete-problem>删除题目</button>':''}</div></div>`;
    $('#code-input').value=p.code||'';
    state.editor={problem:{...p},initial:''}; state.editor.initial=JSON.stringify(readProblemForm());
    highlightCode(); updateCursor();
  }
  function readProblemForm() {
    const form=$('#problem-form'); if(!form)return null;
    const data=new FormData(form);return {platform:data.get('platform'),number:data.get('number'),name:data.get('name'),url:data.get('url'),language:data.get('language'),contest_id:data.get('contest_id')||null,code:data.get('code')};
  }
  const keywords=new Set('alignas alignof and asm auto bool break case catch char class const constexpr continue default delete do double else enum explicit export extern false float for friend goto if inline int long mutable namespace new noexcept nullptr operator private protected public register reinterpret_cast return short signed sizeof static static_assert static_cast struct switch template this throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while include define elif endif pragma import from def lambda pass True False None in is not or as assert async await del except finally global nonlocal raise with yield abstract boolean byte extends final implements instanceof interface native package strictfp super synchronized throws transient var record sealed permits'.split(' '));
  const types=new Set('std string vector map set unordered_map unordered_set pair tuple queue deque stack priority_queue cin cout endl size_t null print range len self list dict input main System String Scanner ArrayList HashMap HashSet List Map Set'.split(' '));
  function highlightCode() {
    const area=$('#code-input');if(!area)return;const code=area.value,lang=$('#editor-language').value;
    if(lang==='other') $('#highlight-code').textContent=code+'\n';
    else {
      const python=lang==='python';
      const token=python?/(#[^\n]*|"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|\b\d+(?:\.\d+)?\b|\b[A-Za-z_]\w*\b)/g:/(\/\/[^\n]*|\/\*[\s\S]*?(?:\*\/|$)|"(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|^\s*#[^\n]*|\b\d+(?:\.\d+)?(?:[uUlLfF]+)?\b|\b[A-Za-z_]\w*\b)/gm;
      let result='',last=0,m;
      while((m=token.exec(code))!==null){result+=esc(code.slice(last,m.index));const v=m[0];let type='';if(v.startsWith('//')||v.startsWith('/*')||(python&&v.startsWith('#')))type='comment';else if(/^\s*#/.test(v))type='preprocessor';else if(v[0]==='"'||v[0]==="'")type='string';else if(/^\d/.test(v))type='number';else if(keywords.has(v))type='keyword';else if(types.has(v))type='type';result+=type?`<span class="tok-${type}">${esc(v)}</span>`:esc(v);last=m.index+v.length;}
      $('#highlight-code').innerHTML=result+esc(code.slice(last))+'\n';
    }
    $('#line-numbers').textContent=Array.from({length:code.split('\n').length},(_,i)=>i+1).join('\n'); syncScroll(); updateSaveState();
  }
  function syncScroll(){const area=$('#code-input');if(!area)return;$('#highlight-pre').scrollTop=area.scrollTop;$('#highlight-pre').scrollLeft=area.scrollLeft;$('#line-numbers').style.transform=`translateY(${-area.scrollTop}px)`;}
  function updateCursor(){const a=$('#code-input');if(!a)return;const before=a.value.slice(0,a.selectionStart).split('\n');$('#cursor-status').textContent=`第 ${before.length} 行，第 ${before[before.length-1].length+1} 列 · ${a.value.length.toLocaleString()} 字符`;}
  function updateSaveState(){const status=$('#save-state');if(!status||!state.editor)return;const dirty=isDirty();status.className=`save-state ${dirty?'dirty':'saved'}`;status.textContent=dirty?'● 有未保存的修改':(state.editor.problem.id?'✓ 已保存到本地':'尚未保存');}
  function showEditorError(e){const el=$('#editor-error');el.innerHTML=esc(e.message)+(e.existing_id?`<br><button class="text-link" data-open-problem="${esc(e.existing_id)}">打开已有题目 →</button>（当前内容尚未保存）`:'')+(e.status===409&&!e.existing_id?' 请先复制当前代码，再重新打开这道题目查看最新记录。':'');el.scrollIntoView({block:'nearest',behavior:'smooth'});}
  async function saveProblem(event){event?.preventDefault();if(state.busy||!state.editor)return;const form=$('#problem-form');if(!form.reportValidity())return;const data=readProblemForm();if(!data.number.trim()&&!data.name.trim()){showEditorError(new Error('题目编号与题目名称至少填写一项。'));return;}
    state.busy=true;form.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=true;});const button=$('#save-problem');button.disabled=true;button.textContent='正在保存…';$('#editor-error').textContent='';
    try{const old=state.editor.problem;const saved=await api(old.id?`/api/problems/${encodeURIComponent(old.id)}`:'/api/problems',old.id?'PUT':'POST',{...data,...(old.id?{version:old.version}:{})});await loadState();state.editor=null;state.route=`problem/${saved.problem.id}`;navigating=true;location.hash=state.route;setTimeout(()=>{navigating=false;},0);problemEditor(saved.problem);toast('题目与代码已保存，所有页面已同步。');}
    catch(e){showEditorError(e);}finally{state.busy=false;$('#problem-form')?.querySelectorAll('input,select,textarea,button').forEach(el=>{el.disabled=false;});if($('#save-problem')){$('#save-problem').disabled=false;$('#save-problem').innerHTML='保存修改 <span aria-hidden="true">↵</span>';}}
  }
  async function copyCode(){const area=$('#code-input');try{await navigator.clipboard.writeText(area.value);toast('代码已复制。');}catch(_){const start=area.selectionStart,end=area.selectionEnd;area.focus();area.select();const ok=document.execCommand('copy');if(ok)area.setSelectionRange(start,end);toast(ok?'代码已复制。':'请按 Ctrl + C 复制选中的代码。',!ok);}}
  function closeModal(){if(state.busy)return;modal.close();modal.innerHTML='';}
  function setModalBusy(busy){state.busy=busy;modal.querySelectorAll('button,input,select').forEach(el=>{el.disabled=busy;});}
  function dialogHeader(title){return `<div class="modal-header"><h2 id="dialog-title">${esc(title)}</h2><button type="button" class="modal-close" data-close-modal aria-label="关闭">×</button></div>`;}
  function openContestForm(id='', platform=''){
    const c=state.contests.find(c=>c.id===id)||{platform:platform||'codeforces',title:'',url:''};
    modal.innerHTML=`<form id="contest-form">${dialogHeader(id?'编辑比赛':'新建一场比赛')}<div class="modal-body"><p>保存比赛信息，之后就可以逐题添加代码。</p><label class="field"><span>所属平台</span><select name="platform">${Object.entries(platforms).map(([k,v])=>option(k,v,c.platform)).join('')}</select></label><label class="field"><span>比赛标题</span><input name="title" required maxlength="300" placeholder="例如 Codeforces Round 1000" value="${esc(c.title)}"></label><label class="field"><span>比赛链接</span><input name="url" type="url" required maxlength="2048" placeholder="粘贴比赛页面链接" value="${esc(c.url)}"></label><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn primary">${id?'保存修改':'创建比赛'}</button></div></form>`;
    modal.showModal();$('#contest-form').addEventListener('submit',async event=>{event.preventDefault();if(state.busy)return;const f=new FormData(event.target);setModalBusy(true);try{const result=await api(id?`/api/contests/${encodeURIComponent(id)}`:'/api/contests',id?'PUT':'POST',{platform:f.get('platform'),title:f.get('title'),url:f.get('url'),...(id?{version:c.version}:{})});setModalBusy(false);closeModal();toast(id?'比赛信息已更新。':'比赛已创建，可以开始添加题目。');await go(`contest/${result.contest.id}`,{force:true});}catch(e){setModalBusy(false);const err=$('#dialog-error');if(err)err.textContent=e.message;else toast(e.message,true);}});
  }
  function deleteContest(id){
    const c=state.contests.find(c=>c.id===id);if(!c)return;const count=state.problems.filter(p=>p.contest_id===id).length;
    modal.innerHTML=`<form id="delete-contest-form">${dialogHeader('删除比赛')}<div class="modal-body"><p>即将删除「${esc(c.title)}」。请选择如何处理比赛下的 ${count} 道题目。</p><label class="choice"><input type="radio" name="mode" value="keep" checked><span>保留题目与代码<small>仅删除比赛，题目将保留在全部题目中并取消关联。</small></span></label><label class="choice"><input type="radio" name="mode" value="delete"><span>同时删除所有题目与代码<small>永久删除该比赛下的题目记录与源代码文件。</small></span></label><div class="danger-note">此操作无法撤销，请确认已保留需要的代码。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>取消</button><button type="submit" class="btn danger">确认删除比赛</button></div></form>`;
    modal.showModal();$('#delete-contest-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;const keep=new FormData(e.target).get('mode')==='keep';if(!keep&&!window.confirm(`再次确认：将永久删除「${c.title}」及其 ${count} 道题目和对应代码文件。确定继续吗？`))return;setModalBusy(true);try{await api(`/api/contests/${encodeURIComponent(id)}`,'DELETE',{version:c.version,keep_problems:keep,confirmed:true});setModalBusy(false);closeModal();toast(keep?'比赛已删除，题目和代码已保留。':'比赛及其题目、代码已删除。');await go('contests',{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function deleteProblem(){
    const p=state.editor?.problem;if(!p?.id)return;
    modal.innerHTML=`<form id="delete-problem-form">${dialogHeader('确认删除题目')}<div class="modal-body"><p>确定删除「${esc([p.number,p.name].filter(Boolean).join(' · ')||'这道题目')}」吗？</p><div class="danger-note">题目记录和对应源代码文件将被永久删除。所属比赛与全部题目中都会移除该题目，此操作无法撤销。</div><div id="dialog-error" class="error-text" role="alert"></div></div><div class="modal-actions"><button type="button" class="btn" data-close-modal>保留题目</button><button type="submit" class="btn danger">删除题目及代码</button></div></form>`;
    modal.showModal();$('#delete-problem-form').addEventListener('submit',async e=>{e.preventDefault();if(state.busy)return;setModalBusy(true);try{await api(`/api/problems/${encodeURIComponent(p.id)}`,'DELETE',{version:p.version,confirmed:true});setModalBusy(false);closeModal();toast('题目及对应代码已删除。');await go(p.contest_id?`contest/${p.contest_id}`:'problems',{force:true});}catch(err){setModalBusy(false);const el=$('#dialog-error');if(el)el.textContent=err.message;else toast(err.message,true);}});
  }
  function unlinkProblem(){
    if(!state.editor)return;$('#editor-contest').value='';updateSaveState();toast('已取消比赛选择。点击「保存修改」后生效，题目和代码会保留。');$('#editor-contest').focus();
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
  document.addEventListener('click',async e=>{
    const t=e.target.closest('button,a');if(!t)return;if(state.busy){e.preventDefault();return;}
    if(t.hasAttribute('data-nav')){e.preventDefault();await go(t.dataset.nav);}
    else if(t.hasAttribute('data-open-problem')){e.preventDefault();await go(`problem/${t.dataset.openProblem}`);}
    else if(t.hasAttribute('data-open-contest')){e.preventDefault();await go(`contest/${t.dataset.openContest}`);}
    else if(t.hasAttribute('data-new-problem')){e.preventDefault();const q=new URLSearchParams();if(t.dataset.newProblem)q.set('contest',t.dataset.newProblem);if(t.dataset.platform)q.set('platform',t.dataset.platform);await go(`new-problem${q.size?'?'+q:''}`);}
    else if(t.hasAttribute('data-new-contest')){if(allowLeave())openContestForm('',t.dataset.newContest);}
    else if(t.hasAttribute('data-edit-contest'))openContestForm(t.dataset.editContest);
    else if(t.hasAttribute('data-delete-contest'))deleteContest(t.dataset.deleteContest);
    else if(t.hasAttribute('data-copy-code'))await copyCode();
    else if(t.hasAttribute('data-delete-problem'))deleteProblem();
    else if(t.hasAttribute('data-unlink-problem'))unlinkProblem();
    else if(t.hasAttribute('data-close-modal'))closeModal();
    else if(t.hasAttribute('data-retry'))await renderRoute(state.route);
  });
  document.addEventListener('submit',e=>{if(e.target.id==='problem-form')saveProblem(e);});
  document.addEventListener('input',e=>{
    if(e.target.id==='filter-query'){state.filter.q=e.target.value;updateTable();}
    else if(e.target.id==='contest-search')updateContests();
    else if(e.target.id==='code-input'){highlightCode();updateCursor();}
    else if(e.target.closest('#problem-form'))updateSaveState();
  });
  document.addEventListener('change',e=>{
    if(e.target.id.startsWith('filter-')&&e.target.id!=='filter-query'){
      const key=e.target.id.replace('filter-','');state.filter[key]=e.target.value;
      if(key==='platform') {state.filter.contest='';const sel=$('#filter-contest');if(sel)sel.innerHTML=option('','全部比赛','')+option('none','未关联比赛','')+state.contests.filter(c=>!state.filter.platform||c.platform===state.filter.platform).map(c=>option(c.id,c.title,'')).join('');}updateTable();
    }else if(e.target.id==='contest-platform')updateContests();
    else if(e.target.id==='editor-platform'){$('#editor-contest').innerHTML=contestSelect(e.target.value,'');updateSaveState();}
    else if(e.target.id==='editor-language'){highlightCode();$('#code-file-type').textContent=`UTF-8 · ${extensions[e.target.value]||'.txt'}`;}
    else if(e.target.closest('#problem-form'))updateSaveState();
  });
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&state.editor){e.preventDefault();if(!modal.open)saveProblem();}else codeKeydown(e);});
  document.addEventListener('keyup',e=>{if(e.target.id==='code-input')updateCursor();});
  document.addEventListener('click',e=>{if(e.target.id==='code-input')updateCursor();});
  document.addEventListener('scroll',e=>{if(e.target.id==='code-input')syncScroll();},true);
  window.addEventListener('beforeunload',e=>{if(state.busy||isDirty()){e.preventDefault();e.returnValue='';}});
  window.addEventListener('hashchange',()=>{const route=location.hash.slice(1)||'home';if(navigating||route===state.route)return;if(state.busy||!allowLeave()){navigating=true;location.hash=state.route;setTimeout(()=>{navigating=false;},0);return;}state.editor=null;state.route=route;renderRoute(route);});
  modal.addEventListener('cancel',e=>{if(state.busy)e.preventDefault();});
  modal.addEventListener('click',e=>{if(e.target===modal&&!e.composedPath().some(x=>x instanceof Element&&x.tagName==='FORM')){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
  state.route=location.hash.slice(1)||'home';renderRoute(state.route);
})();
