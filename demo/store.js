"use strict";

(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.AlgoArchiveDemo = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const copy = value => JSON.parse(JSON.stringify(value));
  const bytes = value => new TextEncoder().encode(value).length;
  const aliases = { lanqiao: "蓝桥杯", "蓝桥": "蓝桥杯", lanqiaobei: "蓝桥杯", hdu: "HDU", hduoj: "HDU", "杭电": "HDU", "杭州电子科技大学": "HDU", matiji: "码蹄集", "码蹄": "码蹄集", codeforces: "Codeforces", atcoder: "AtCoder", acwing: "AcWing", luogu: "洛谷", niuke: "牛客", nowcoder: "牛客", leetcode: "力扣", "leetcode.cn": "力扣", "leetcode.com": "力扣", poj: "POJ", "poj.org": "POJ" };
  const platform = v => aliases[String(v || "").trim().toLowerCase()] || String(v || "").trim();
  const cardColors = ["blue", "cyan", "green", "amber", "rose", "violet"];
  const fail = (message, status = 400) => { const e = new Error(message); e.status = status; throw e; };

  function createStore(fixture, options = {}) {
    const data = copy(fixture);
    data.sidebar_art = data.sidebar_art || { image: "celebration", hidden: false };
    data.platform_problem_orders = data.platform_problem_orders || {};
    const nextColors = { algorithm: 0, contest: 0 };
    for (const [kind, collection] of [["algorithm", "algorithms"], ["contest", "contests"]]) {
      for (const item of [...data[collection]].sort((a,b)=>(Number(a.sort_order)||0)-(Number(b.sort_order)||0))) {
        if (!cardColors.includes(item.card_color)) item.card_color = cardColors[nextColors[kind]];
        nextColors[kind] = (nextColors[kind] + 1) % cardColors.length;
      }
    }
    let serial = 0;
    const snippets = data.algorithms.flatMap(a => a.snippets || []);
    const find = (items, id) => items.find(x => x.id === id) || fail("记录不存在或已被删除。", 404);
    const version = (record, payload) => {
      if (record.version !== payload.version) fail("记录已发生变化，请刷新页面后重新操作。", 409);
    };
    const touch = record => { record.version++; record.updated_at = new Date().toISOString(); };
    const base = () => ({ id: `demo-${Date.now()}-${++serial}`, version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    const tests = items => {
      if (!Array.isArray(items) || items.length > 100) fail("用例必须是数组且最多 100 个。");
      let total = 0;
      const result = items.map((t, i) => {
        if (!t || typeof t.input !== "string" || typeof t.output !== "string") fail("测试用例的 input 和 output 必须是文本。");
        const size = bytes(t.input) + bytes(t.output);
        if (size > 1024 * 1024) fail("单个测试用例不能超过 1 MiB。");
        total += size;
        return { ordinal: i, input: t.input, output: t.output };
      });
      if (total > 2 * 1024 * 1024) fail("全部测试用例合计不能超过 2 MiB。");
      return result;
    };
    const getProblem = p => ({ ...p, contest_title: data.contests.find(c => c.id === p.contest_id)?.title || null, algorithm_name: data.algorithms.find(a => a.id === p.algorithm_id)?.name || null });
    const getAlgorithm = a => ({ ...a, snippets: snippets.filter(s => s.algorithm_id === a.id), problem_count: data.problems.filter(p => p.algorithm_id === a.id).length });
    const getContest = c => ({ ...c, problem_count: data.problems.filter(p => p.contest_id === c.id).length });
    const platformKey = value => {
      const label=platform(value);
      return ({Codeforces:'codeforces',AtCoder:'atcoder',AcWing:'acwing','洛谷':'luogu','牛客':'niuke','蓝桥杯':'lanqiao',HDU:'hdu','码蹄集':'matiji','力扣':'leetcode',POJ:'poj'})[label]||label.toLowerCase();
    };
    function syncPlatformOrders(){
      const keys=new Set(['codeforces','atcoder','acwing','luogu','niuke','lanqiao','hdu','matiji','leetcode','poj',...Object.keys(data.platform_problem_orders),...data.problems.map(p=>platformKey(p.platform))]);
      keys.forEach(key=>{
        const old=data.platform_problem_orders[key];
        const records=data.problems.filter(p=>platformKey(p.platform)===key);
        if(!old)records.sort((a,b)=>(b.updated_at||'').localeCompare(a.updated_at||'')||a.id.localeCompare(b.id));
        const members=records.map(p=>p.id);
        const ids=old?old.problem_ids.filter(id=>members.includes(id)):[];
        members.forEach(id=>{if(!ids.includes(id))ids.push(id);});
        data.platform_problem_orders[key]={version:old?old.version+(JSON.stringify(ids)!==JSON.stringify(old.problem_ids)?1:0):1,problem_ids:ids};
      });
    }
    syncPlatformOrders();
    const state = () => ({ ...data, problems: data.problems.map(getProblem), contests: data.contests.map(getContest), algorithms: data.algorithms.map(getAlgorithm) });
    const validate = (kind, payload, old = null) => {
      const p = copy(payload);
      delete p.version; delete p.id; delete p.created_at; delete p.updated_at; delete p.card_color;
      if (kind === "problem" || kind === "snippet") {
        if (old?.code_locked && ((p.code !== undefined && p.code !== old.code) || (p.language !== undefined && p.language !== old.language))) fail("代码已锁定，请先解锁后再修改代码或语言。", 409);
        if (old && p.code_locked !== undefined && p.code_locked !== old.code_locked) fail("请使用代码锁定开关。", 409);
        if (p.code !== undefined && (typeof p.code !== "string" || bytes(p.code) > 2 * 1024 * 1024)) fail("代码必须是文本且不能超过 2 MiB。");
        if (p.code_locked !== undefined && typeof p.code_locked !== "boolean") fail("锁定状态必须是布尔值。");
      }
      if (kind === "problem") {
        delete p.contest_order; delete p.global_order; delete p.algorithm_order;
      }
      if (p.platform !== undefined) p.platform = platform(p.platform);
      if (p.tests !== undefined) p.tests = tests(p.tests);
      if (p.contest_id) {
        const c = find(data.contests, p.contest_id);
        if (p.platform && p.platform !== c.platform) fail("题目平台必须与比赛一致。");
        p.platform = c.platform;
      }
      if (p.algorithm_id) find(data.algorithms, p.algorithm_id);
      const key = kind === "contest" || kind === "snippet" ? "title" : "name";
      if (p[key] !== undefined && (typeof p[key] !== "string" || !p[key].trim())) fail("名称不能为空。");
      if (!old && !p[key]) fail("名称不能为空。");
      return p;
    };
    const nextContestOrder = id => id ? Math.max(-1, ...data.problems.filter(p => p.contest_id === id).map(p => p.contest_order)) + 1 : 0;
    const touchContests = ids => new Set(ids.filter(Boolean)).forEach(id => touch(find(data.contests, id)));
    const insertProblem = p => {
      const item = { ...base(), platform: "", number: "", name: "", language: "cpp", code: "", code_locked: false, url: "", tests: [], contest_id: null, algorithm_id: null,
        global_order: data.problems.length, algorithm_order: data.problems.length, ...p, contest_order: nextContestOrder(p.contest_id) };
      data.problems.push(item);
      touchContests([item.contest_id]);
      return getProblem(item);
    };
    function dispatch(method, route, payload) {
      if (method === "GET" && route === "/api/state") return state();
      if (method === "GET" && route === "/api/settings") return { settings: {
        version: options.version || "2.2.10", address: options.address || "GitHub Pages · 在线演示", database_schema: "演示内存数据",
        data_dir: "当前页面内存（刷新重置）", config_path: "不适用（在线演示）", log_path: "不适用（在线演示）", backup_dir: "不适用（在线演示）",
        browser: { mode: "default", window_mode: "tab" },
        sidebar_art: data.sidebar_art,
        compiler: { available: false, standard: "gnu++14", standards: ["gnu++11", "gnu++14", "gnu++17"], version: "在线演示不执行 C++，请使用本地版。", configured_path: "", path: "" },
      } };
      if (method === "GET" && route === "/api/settings/sidebar-art") return {sidebar_art:data.sidebar_art};
      if (method === "GET" && route === "/api/backups") return { backups: [] };
      if (method === "PUT" && route === "/api/settings/sidebar-art") {
        if (!["debug", "thinking", "celebration"].includes(payload.image) || typeof payload.hidden !== "boolean") fail("请选择内置侧栏插画，并指定是否隐藏。");
        data.sidebar_art = { image: payload.image, hidden: payload.hidden };
        return { sidebar_art: data.sidebar_art };
      }
      if (method === "PUT" && route === "/api/profile") {
        if (typeof payload.name !== "string" || !payload.name.trim() || payload.name.length > 50) fail("用户名必须为 1-50 字符。");
        data.profile = { name: payload.name.trim(), avatar: typeof payload.avatar === "string" && /^data:image\/(png|jpeg|webp);base64,/.test(payload.avatar) ? payload.avatar : "" };
        return { profile: data.profile };
      }
      const platformOrder=route.match(/^\/api\/platforms\/([^/]+)\/problems\/order$/);
      if(method==='PUT'&&platformOrder){
        const key=platformKey(decodeURIComponent(platformOrder[1])),old=data.platform_problem_orders[key]||{version:1,problem_ids:[]},ids=payload.problem_ids;
        if(!Array.isArray(ids)||ids.some(id=>typeof id!=='string')||new Set(ids).size!==ids.length)fail('题目顺序格式不正确。');
        if(!Number.isInteger(payload.version)||payload.version!==old.version)fail('排序已改变，请刷新。',409);
        if(ids.length!==old.problem_ids.length||ids.some(id=>!old.problem_ids.includes(id)))fail('题目列表已发生变化，请刷新。',409);
        data.platform_problem_orders[key]={version:old.version+1,problem_ids:[...ids]};
        return {platform:key,platform_order_version:old.version+1,problem_ids:ids};
      }
      const orderMatch = route.match(/^\/api\/(contests|algorithms|problems)\/order$/);
      if (method === "PUT" && orderMatch) {
        const collection = orderMatch[1], key = `${collection.slice(0, -1)}_order_version`;
        const ids = collection === "problems" ? payload.problem_ids : payload.ordered_ids;
        if (payload.version !== data[key]) fail("排序已改变，请刷新。", 409);
        if (!Array.isArray(ids) || ids.length !== data[collection].length || new Set(ids).size !== ids.length || ids.some(id => !data[collection].some(x => x.id === id))) fail("排序记录不完整。");
        ids.forEach((id, i) => { find(data[collection], id)[collection === "problems" ? "global_order" : "sort_order"] = i; });
        data[key]++;
        return { ok: true, version: data[key] };
      }
      if (method === "POST" && route === "/api/problems/import") {
        if (!Array.isArray(payload.problems) || payload.problems.length < 1 || payload.problems.length > 200) fail("单次导入 1-200 道题目。");
        const prepared = payload.problems.map(p => validate("problem", p));
        const imported = prepared.map(insertProblem);
        return { count: imported.length, imported: imported.length, problems: imported, warnings: [] };
      }
      const algorithmOrder = route.match(/^\/api\/algorithms\/([^/]+)\/problems\/order$/);
      if (method === "PUT" && algorithmOrder) {
        const a = find(data.algorithms, algorithmOrder[1]); version(a, payload);
        const items = data.problems.filter(p => p.algorithm_id === a.id), ids = payload.problem_ids;
        if (!Array.isArray(ids) || ids.length !== items.length || new Set(ids).size !== ids.length || ids.some(id => !items.some(p => p.id === id))) fail("排序记录不完整。");
        ids.forEach((id, i) => { find(items, id).algorithm_order = i; }); touch(a);
        return { ok: true, version: a.version };
      }
      const contestOrder = route.match(/^\/api\/contests\/([^/]+)\/problems\/order$/);
      if (method === "PUT" && contestOrder) {
        const c = find(data.contests, contestOrder[1]); version(c, payload);
        const items = data.problems.filter(p => p.contest_id === c.id), ids = payload.problem_ids;
        if (!Array.isArray(ids) || ids.some(id => typeof id !== "string") || new Set(ids).size !== ids.length) fail("题目顺序格式不正确。");
        if (ids.length !== items.length || ids.some(id => !items.some(p => p.id === id))) fail("题目列表已发生变化，请刷新页面后重新调整顺序。", 409);
        ids.forEach((id, i) => { find(items, id).contest_order = i; }); touch(c);
        return { contest: getContest(c) };
      }
      const snippetPost = route.match(/^\/api\/algorithms\/([^/]+)\/snippets$/);
      if (method === "POST" && snippetPost) {
        const a = find(data.algorithms, snippetPost[1]);
        const p = validate("snippet", { ...payload, algorithm_id: a.id });
        const item = { ...base(), code: "", language: "cpp", code_locked: false, ...p, algorithm_name: a.name };
        snippets.push(item); touch(a); return { snippet: item };
      }
      const lock = route.match(/^\/api\/(problems|algorithm-snippets)\/([^/]+)\/code-lock$/);
      if (method === "PUT" && lock) {
        const item = find(lock[1] === "problems" ? data.problems : snippets, lock[2]); version(item, payload);
        if (typeof payload.code_locked !== "boolean") fail("锁定状态必须是布尔值。");
        if (item.code_locked !== payload.code_locked) { item.code_locked = payload.code_locked; touch(item); }
        return { [lock[1] === "problems" ? "problem" : "snippet"]: item };
      }
      const testRoute = route.match(/^\/api\/problems\/([^/]+)\/tests$/);
      if (method === "PUT" && testRoute) {
        const item = find(data.problems, testRoute[1]); version(item, payload);
        const validated = tests(payload.tests); item.tests = validated; touch(item);
        return { tests: item.tests, version: item.version };
      }
      const resource = route.match(/^\/api\/(problems|contests|algorithms|algorithm-snippets)(?:\/([^/]+))?$/);
      if (resource) {
        const kind = { problems: "problem", contests: "contest", algorithms: "algorithm", "algorithm-snippets": "snippet" }[resource[1]];
        const items = kind === "snippet" ? snippets : data[resource[1]];
        const shape = item => kind === "problem" ? getProblem(item) : kind === "contest" ? getContest(item) : kind === "algorithm" ? getAlgorithm(item) : item;
        if (method === "GET" && resource[2]) return { [kind]: shape(find(items, resource[2])) };
        if (method === "POST" && !resource[2] && kind !== "snippet") {
          const p = validate(kind, payload);
          if (kind === "problem") return { problem: insertProblem(p) };
          const item = { ...base(), sort_order: items.length, ...(kind === "algorithm" ? { links: [], snippets: [], category: "", description: "" } : { url: "", platform: "" }), ...p };
          item.card_color = cardColors[nextColors[kind]];
          nextColors[kind] = (nextColors[kind] + 1) % cardColors.length;
          items.push(item); return { [kind]: shape(item) };
        }
        if ((method === "PUT" || method === "DELETE") && resource[2]) {
          const item = find(items, resource[2]); version(item, payload);
          if (method === "PUT") {
            const p = validate(kind, payload, item);
            if (kind === "problem") {
              const nextContest = p.contest_id === undefined ? item.contest_id : p.contest_id;
              if (nextContest !== item.contest_id) p.contest_order = nextContestOrder(nextContest);
              touchContests([item.contest_id, nextContest]);
            }
            Object.assign(item, p); touch(item);
            return { [kind]: shape(item) };
          }
          if (kind === "contest") {
            if (payload.keep_problems) data.problems.filter(p => p.contest_id === item.id).forEach(p => { p.contest_id = null; touch(p); });
            else data.problems = data.problems.filter(p => p.contest_id !== item.id);
          }
          if (kind === "algorithm") {
            for (let i = snippets.length - 1; i >= 0; i--) if (snippets[i].algorithm_id === item.id) snippets.splice(i, 1);
            data.problems.filter(p => p.algorithm_id === item.id).forEach(p => { p.algorithm_id = null; touch(p); });
          }
          items.splice(items.indexOf(item), 1);
          if (kind === "problem") touchContests([item.contest_id]);
          return { ok: true };
        }
      }
      fail("在线演示不执行此操作，请下载本地版使用。", 501);
    }
    return { request(method, route, payload = {}) {
      try { const result=dispatch(method.toUpperCase(), route.split("?")[0], copy(payload));syncPlatformOrders();return { status: 200, body: copy(result) }; }
      catch (error) { return { status: error.status || 400, body: { error: error.message, code: "demo_error" } }; }
    } };
  }
  return { createStore };
});
