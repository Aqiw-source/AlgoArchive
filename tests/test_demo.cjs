"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createFixture } = require("../demo/fixture.cjs");
const { createStore } = require("../demo/store.js");
const { buildDemo } = require("../scripts/build-demo.cjs");

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
  assert.equal(s.request("DELETE", `/api/contests/${c.id}`, { version: c.version, keep_problems: true }).status, 200);
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
    const sourceImage = fs.readFileSync(path.join(out, "sidebar-art.png"));
    assert.equal(sourceImage.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
    assert.equal(sourceImage.readUInt32BE(16), 938);
    assert.equal(sourceImage.readUInt32BE(20), 1670);
    assert.ok(html.includes('src="/AlgoArchive/sidebar-art-blended.webp?v=20261114-celebration-blend"'));
    assert.ok(fs.existsSync(path.join(out, "sidebar-art-blended.webp")));
    const appJs = fs.readFileSync(path.join(out, "app.js"), "utf8");
    assert.ok(appJs.includes("/AlgoArchive/sidebar-art.png?v=20261114-celebration"));
    const files = fs.readdirSync(out, { recursive: true }).map(String);
    assert.ok(files.every(p => !/\.py$|sqlite|config\.json$|runtime[\\/]|codes[\\/]/i.test(p)));
    assert.ok(!fs.readFileSync(path.join(out, "app.js"), "utf8").includes('src="/platform-icons/'));
    assert.ok(fs.readFileSync(path.join(out, "app.js"), "utf8").includes("document.title='AlgoArchive · 在线演示';"));
    assert.ok(!fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8").includes("demo.js"));
  } finally { fs.rmSync(out, { recursive: true, force: true }); }
});
