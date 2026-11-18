"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createFixture } = require("../demo/fixture.cjs");
const { createStore } = require("../demo/store.js");
const { buildDemo } = require("../scripts/build-demo.cjs");

test("sidebar art preferences stay in the session and reject arbitrary images", () => {
  const s = createStore(createFixture());
  const initial = { image: "celebration", hidden: false };
  assert.deepEqual(s.request("GET", "/api/state").body.sidebar_art, initial);
  for (const image of ["debug", "thinking", "celebration"]) {
    const preference = { image, hidden: true };
    assert.equal(s.request("PUT", "/api/settings/sidebar-art", preference).status, 200);
    assert.deepEqual(s.request("GET", "/api/settings").body.settings.sidebar_art, preference);
    assert.deepEqual(s.request("GET", "/api/state").body.sidebar_art, preference);
  }
  assert.equal(s.request("PUT", "/api/settings/sidebar-art", { image: "custom.png", hidden: false }).status, 400);
  assert.equal(s.request("PUT", "/api/settings/sidebar-art", { image: "debug", hidden: "false" }).status, 400);
  assert.deepEqual(createStore(createFixture()).request("GET", "/api/state").body.sidebar_art, initial);
});

test("LeetCode and POJ normalize consistently without restricting custom platforms", () => {
  const s = createStore(createFixture());
  for (const [raw, canonical] of [["LeetCode", "力扣"], ["leetcode.cn", "力扣"], ["力扣", "力扣"], ["poj", "POJ"], ["POJ", "POJ"], ["自定义平台", "自定义平台"]]) {
    const c = s.request("POST", "/api/contests", { title: raw, platform: raw, url: "https://example.com" });
    assert.equal(c.body.contest.platform, canonical);
    const p = s.request("POST", "/api/problems", { name: raw, platform: raw, contest_id: c.body.contest.id });
    assert.equal(p.status, 200);
    assert.equal(p.body.problem.platform, canonical);
  }
});

test("substantial public demo data keeps ICPC and Lanqiao separate", () => {
  const data = createFixture();
  assert.ok(data.contests.length >= 13);
  assert.ok(data.problems.length >= 100);
  const lanqiao = data.contests.filter(c => c.platform === "蓝桥杯");
  assert.equal(lanqiao.length, 6);
  for (const year of [2023, 2024, 2025]) {
    assert.ok(lanqiao.some(c => c.title.includes(`${year}`) && c.title.includes("省赛")));
    assert.ok(lanqiao.some(c => c.title.includes(`${year}`) && c.title.includes("国赛")));
  }
  assert.ok(data.contests.some(c => c.platform === "Codeforces" && c.title.includes("Yokohama")));
  assert.ok(data.problems.every(p => data.contests.some(c => c.id === p.contest_id && c.platform === p.platform)));
  assert.equal(new Set(data.problems.map(p => p.id)).size, data.problems.length);
  assert.ok(data.problems.every(p => /^https:\/\//.test(p.url)));
});

test("AcWing and Nowcoder contest archives contain browsable problems without code files", () => {
  const store = createStore(createFixture());
  const state = store.request("GET", "/api/state").body;
  for (const [platform, expectedNumbers] of [["AcWing", ["6098", "6099", "6100"]], ["牛客", ["A", "B", "C", "D", "F", "G"]]]) {
    const contest = state.contests.find(c => c.platform === platform);
    assert.ok(contest, `${platform} has a contest in its workspace`);
    const problems = state.problems.filter(p => p.contest_id === contest.id);
    assert.equal(contest.problem_count, expectedNumbers.length);
    assert.deepEqual(problems.map(p => p.number), expectedNumbers);
    for (const p of problems) {
      const response = store.request("GET", `/api/problems/${p.id}`);
      assert.equal(response.status, 200);
      const problem = response.body.problem;
      assert.equal(problem.platform, platform);
      assert.equal(new URL(problem.url).hostname, new URL(contest.url).hostname);
      assert.equal(problem.code, "");
      assert.ok(!problem.code_path);
      assert.deepEqual(problem.tests, []);
    }
  }
  assert.deepEqual(state.problems.filter(p => p.platform === "AcWing").map(p => p.url), [
    "https://www.acwing.com/problem/content/6101/",
    "https://www.acwing.com/problem/content/6102/",
    "https://www.acwing.com/problem/content/6103/",
  ]);
});

test("state and details are isolated copies; a fresh store resets edits", () => {
  const fixture = createFixture();
  const store = createStore(fixture);
  const p = store.request("GET", "/api/state").body.problems[0];
  p.name = "not a write";
  assert.notEqual(store.request("GET", `/api/problems/${p.id}`).body.problem.name, p.name);
  const original = store.request("GET", `/api/problems/${p.id}`).body.problem;
  assert.equal(store.request("PUT", `/api/problems/${p.id}`, { ...original, name: "edited" }).status, 200);
  assert.equal(createStore(fixture).request("GET", `/api/problems/${p.id}`).body.problem.name, original.name);
});

test("code lock enforces versions and protects code, not metadata", () => {
  const store = createStore(createFixture());
  const p = store.request("GET", "/api/state").body.problems[0];
  const locked = store.request("PUT", `/api/problems/${p.id}/code-lock`, { version: p.version, code_locked: true });
  assert.equal(locked.status, 200);
  assert.equal(locked.body.problem.code_locked, true);
  assert.equal(store.request("PUT", `/api/problems/${p.id}`, { ...p, name: "stale" }).status, 409);
  const current = locked.body.problem;
  assert.equal(store.request("PUT", `/api/problems/${p.id}`, { ...current, code: "changed" }).status, 409);
  assert.equal(store.request("PUT", `/api/problems/${p.id}`, { ...current, name: "metadata" }).status, 200);
});

test("contest problem ordering is scoped to one contest", () => {
  const store = createStore(createFixture());
  const state = store.request("GET", "/api/state").body;
  const contest = state.contests.find(item => state.problems.filter(p => p.contest_id === item.id).length >= 2);
  const problems = state.problems.filter(item => item.contest_id === contest.id);
  const ids = problems.map(item => item.id);
  const globalOrder = Object.fromEntries(problems.map(item => [item.id, item.global_order]));
  const result = store.request("PUT", `/api/contests/${contest.id}/problems/order`, {
    version: contest.version,
    problem_ids: ids.slice().reverse(),
  });
  assert.equal(result.status, 200);
  const ordered = store.request("GET", "/api/state").body.problems
    .filter(item => item.contest_id === contest.id)
    .sort((a, b) => a.contest_order - b.contest_order);
  assert.deepEqual(ordered.map(item => item.id), ids.slice().reverse());
  assert.deepEqual(
    Object.fromEntries(ordered.filter(item => ids.includes(item.id)).map(item => [item.id, item.global_order])),
    globalOrder,
  );
  assert.equal(store.request("PUT", `/api/contests/${contest.id}/problems/order`, {
    version: contest.version, problem_ids: ids,
  }).status, 409);
  assert.equal(store.request("PUT", `/api/contests/${contest.id}/problems/order`, {
    version: result.body.contest.version, problem_ids: ids.slice(1),
  }).status, 409);
});

test("CRUD, templates, tests, ordering, import and deletion use API-shaped contracts", () => {
  const s = createStore(createFixture());
  const c = s.request("POST", "/api/contests", { platform: "蓝桥", title: "演示比赛", url: "https://www.lanqiao.cn/" }).body.contest;
  assert.equal(c.platform, "蓝桥杯");
  const p = s.request("POST", "/api/problems", { contest_id: c.id, platform: "蓝桥杯", name: "演示", language: "cpp", code: "abc" }).body.problem;
  assert.equal(s.request("PUT", `/api/problems/${p.id}/tests`, { version: p.version, tests: [{ input: "1", output: "2" }] }).body.tests.length, 1);
  const a = s.request("POST", "/api/algorithms", { name: "演示算法", links: [] }).body.algorithm;
  const n = s.request("POST", `/api/algorithms/${a.id}/snippets`, { title: "模板", language: "cpp", code: "x" }).body.snippet;
  assert.equal(s.request("PUT", `/api/algorithm-snippets/${n.id}/code-lock`, { version: n.version, code_locked: true }).body.snippet.code_locked, true);
  const state = s.request("GET", "/api/state").body;
  assert.equal(state.algorithms.find(x => x.id === a.id).snippets.length, 1);
  assert.equal(s.request("PUT", "/api/contests/order", { version: state.contest_order_version, ordered_ids: state.contests.map(x => x.id).reverse() }).status, 200);
  assert.equal(s.request("POST", "/api/problems/import", { problems: [{ platform: "HDU", name: "import", tests: [{ input: "i", output: "o" }] }] }).body.imported, 1);
  const current = s.request("GET", `/api/contests/${c.id}`).body.contest;
  assert.equal(s.request("DELETE", `/api/contests/${c.id}`, { version: current.version, keep_problems: true }).status, 200);
  assert.equal(s.request("GET", `/api/problems/${p.id}`).body.problem.contest_id, null);
});

test("system APIs never report fake execution success", () => {
  const s = createStore(createFixture());
  for (const route of ["/api/compiler/run", "/api/settings/desktop-shortcut", "/api/shutdown", "/api/backups/create", "/api/open-data-folder", "/api/unknown"]) {
    const r = s.request("POST", route, {});
    assert.equal(r.status, 501, route);
    assert.match(r.body.error, /本地版|演示/);
  }
});

test("static build supports project subpaths without shipping local data", () => {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), "algo-demo-test-"));
  try {
    buildDemo(out, "/AlgoArchive/");
    const html = fs.readFileSync(path.join(out, "index.html"), "utf8");
    assert.ok(html.includes('/AlgoArchive/demo.js'));
    assert.ok(html.indexOf("demo.js") < html.indexOf("/AlgoArchive/app.js"));
    assert.ok(!html.includes("__CSRF_TOKEN__"));
    assert.ok(!html.includes("demo-notice"));
    assert.ok(html.includes('data-demo-download'));
    assert.ok(html.includes('data-demo-reset'));
    assert.ok(html.indexOf('class="topbar-status"') < html.indexOf('data-demo-download'));
    const sourceImage = fs.readFileSync(path.join(out, "sidebar-art.png"));
    assert.equal(sourceImage.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    assert.equal(sourceImage.readUInt32BE(16), 938);
    assert.equal(sourceImage.readUInt32BE(20), 1670);
    const sourceHtml = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
    for (const asset of ["app.js", "workspace-updates.css"]) {
      const sourceUrl = sourceHtml.match(new RegExp(`(?:src|href)="(/${asset.replaceAll('.', '\\.')}\\?v=[^"]+)"`))?.[1];
      assert.ok(sourceUrl, `${asset} has an explicit cache version`);
      assert.ok(html.includes(`/AlgoArchive${sourceUrl}`), `${asset} keeps its source version under the demo subpath`);
    }
    assert.ok(!/<img[^>]+src="[^" ]*sidebar-art-blended/.test(html), 'initial markup must not fetch art before preferences are known');
    assert.ok(fs.readFileSync(path.join(out,'app.js'),'utf8').includes("?v=20261117-local2210-r7"));
    for (const file of ["sidebar-art-blended.webp", "sidebar-art-debug.png", "sidebar-art-thinking.png", "sidebar-art-debug-blended.webp", "sidebar-art-thinking-blended.webp", "platform-icons/leetcode.png", "platform-icons/poj.png"]) {
      assert.ok(fs.existsSync(path.join(out, file)), file);
    }
    const files = fs.readdirSync(out, { recursive: true }).map(String);
    assert.ok(files.includes('LICENSE') && files.includes('DISCLAIMER.md') && files.includes('THIRD_PARTY.txt'));
    assert.match(fs.readFileSync(path.join(out, 'LICENSE'), 'utf8'), /MIT License/);
    assert.ok(files.every(p => !/\.py$|sqlite|config\.json$|runtime[\\/]|codes[\\/]/i.test(p)));
    assert.ok(!fs.readFileSync(path.join(out, "app.js"), "utf8").includes('src="/platform-icons/'));
    assert.ok(fs.readFileSync(path.join(out, "app.js"), "utf8").includes("document.title='AlgoArchive · 在线演示';"));
    assert.ok(!fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8").includes("demo.js"));
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});

test("card colors cycle independently and remain stable after rename, sort and deletion", () => {
  const fixture = createFixture();
  fixture.algorithms = []; fixture.contests = []; fixture.problems = [];
  const s = createStore(fixture);
  const expected = ["blue", "cyan", "green", "amber", "rose", "violet", "blue", "cyan"];
  for (const [collection, kind, field] of [["algorithms","algorithm","name"],["contests","contest","title"]]) {
    const records = Array.from({length:8}, (_,i) => s.request("POST", `/api/${collection}`, {
      [field]: `Item ${i}`, platform:"HDU", url:`https://example.com/${i}`, card_color:"violet"
    }).body[kind]);
    assert.deepEqual(records.map(item=>item.card_color), expected);
    const renamed = s.request("PUT", `/api/${collection}/${records[0].id}`, {
      version:1, [field]:"Renamed search", card_color:"rose"
    }).body[kind];
    assert.equal(renamed.card_color,"blue");
    assert.equal(s.request("PUT", `/api/${collection}/order`, {version:1,ordered_ids:records.map(item=>item.id).reverse()}).status,200);
    for (const record of records) assert.equal(s.request("GET", `/api/${collection}/${record.id}`).body[kind].card_color,record.card_color);
    assert.equal(s.request("DELETE", `/api/${collection}/${records[7].id}`, {version:1,confirmed:true,keep_problems:true}).status,200);
    assert.equal(s.request("POST", `/api/${collection}`, {[field]:"Next",platform:"HDU",url:"https://example.com/next"}).body[kind].card_color,"green");
  }
});

test("legacy demo fixtures receive six colors without changing source data", () => {
  const fixture = createFixture(), original = structuredClone(fixture);
  const s = createStore(fixture);
  const state = s.request("GET", "/api/state").body;
  for (const collection of ["algorithms","contests"]) {
    assert.deepEqual(state[collection].slice(0,6).map(item=>item.card_color),["blue","cyan","green","amber","rose","violet"]);
  }
  assert.deepEqual(fixture,original);
});


test("platform orders mirror versioning, membership and independent art reads",()=>{
  const fixture=createFixture();fixture.problems=[];fixture.contests=[];fixture.algorithms=[];
  const store=createStore(fixture),request=(method,url,body)=>store.request(method,url,body);
  assert.deepEqual(request('GET','/api/settings/sidebar-art').body.sidebar_art,{image:'celebration',hidden:false});
  const ids=[];for(let i=0;i<3;i++)ids.push(request('POST','/api/problems',{name:'p'+i,platform:'Codeforces',url:'note',language:'cpp',code:''}).body.problem.id);
  let order=request('GET','/api/state').body.platform_problem_orders.codeforces;
  assert.deepEqual(order.problem_ids,ids);
  const body={version:order.version,problem_ids:[...ids].reverse()};
  assert.equal(request('PUT','/api/platforms/codeforces/problems/order',body).status,200);
  assert.equal(request('PUT','/api/platforms/codeforces/problems/order',body).status,409);
  order=request('GET','/api/state').body.platform_problem_orders.codeforces;
  assert.equal(request('PUT','/api/platforms/codeforces/problems/order',{version:order.version,problem_ids:[ids[0],ids[0],ids[1]]}).status,400);
  const p=request('GET','/api/problems/'+ids[0]).body.problem;
  request('PUT','/api/problems/'+p.id,{version:p.version,platform:'AtCoder',name:'moved'});
  const state=request('GET','/api/state').body;
  assert.deepEqual(state.platform_problem_orders.codeforces.problem_ids,[ids[2],ids[1]]);
  assert.deepEqual(state.platform_problem_orders.atcoder.problem_ids,[ids[0]]);
});
