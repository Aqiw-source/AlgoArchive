"use strict";
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { createFixture } = require("../demo/fixture.cjs");
const checks = {
  "s-fenwick-1": "Fenwick2D t(3,3); t.add(1,1,2); t.add(2,3,5); assert(t.sum(3,3)==7); assert(t.sum(1,3)==2);",
  "s-dsu-0": "DSU d(5); assert(d.unite(0,1)); assert(!d.unite(1,0)); assert(d.find(0)==d.find(1)); assert(d.find(2)!=d.find(1));",
  "s-dsu-1": "RollbackDSU d(5); d.unite(0,1); int v=d.snapshot(); d.unite(1,2); d.unite(3,4); d.rollback(v); assert(d.find(0)==d.find(1)); assert(d.find(2)!=d.find(1)); assert(d.find(3)!=d.find(4));",
  "s-segment-0": "SegmentTree t(5); t.add(1,1,5,2,4,3); t.add(1,1,5,3,5,2); assert(t.query(1,1,5,1,5)==15); assert(t.query(1,1,5,3,3)==5); assert(t.query(1,1,5,1,1)==0);",
  "s-segment-1": "SparseTable t({5,2,7,1,9}); assert(t.query(0,2)==2); assert(t.query(1,4)==1); assert(t.query(2,2)==7);",
  "s-binary-0": "vector<int>a={1,3,3,7}; assert(lower_bound_index(a,3)==1); assert(lower_bound_index(a,8)==4); assert(lower_bound_index({},0)==0);",
  "s-binary-1": "assert(first_true(0,100,[](long long x){return x*x>=30;})==6); assert(first_true(7,7,[](long long){return true;})==7);",
  "s-prefix-0": "assert(prefix_sum({1,-2,4})==vector<long long>({0,1,-1,3})); assert(prefix_sum({})==vector<long long>({0}));",
  "s-prefix-1": "assert(range_add(4,{{0,3,2},{1,2,-1}})==vector<long long>({2,1,1,2}));",
  "s-graph-0": "vector<vector<pair<int,int>>>g(4); g[0]={{1,2},{2,9}}; g[1]={{2,3}}; auto d=dijkstra(g,0); assert(d[2]==5); assert(d[3]==(1LL<<62));",
  "s-graph-1": "auto d=bfs({{1},{0,2},{1},{}},0); assert(d==vector<int>({0,1,2,-1}));",
  "s-topo-0": "auto a=topological_sort({{1},{2},{}}); assert(a==vector<int>({0,1,2})); assert(topological_sort({{1},{0}}).empty());",
  "s-dp-0": "assert(knapsack(5,{2,3,4},{3,4,8})==8); assert(knapsack(0,{1},{2})==0); assert(knapsack(4,{2},{3})==3);",
  "s-dp-1": "assert(lis_length({3,1,2,2,4})==3); assert(lis_length({})==0);",
  "s-kmp-0": "assert(kmp_search(\"aaaa\",\"aa\")==vector<int>({0,1,2})); assert(kmp_search(\"abc\",\"d\").empty()); assert(kmp_search(\"abc\",\"\").empty());",
  "s-kmp-1": "assert(z_function(\"aaaa\")==vector<int>({0,3,2,1})); assert(z_function(\"\").empty());",
  "s-number-0": "assert(linear_sieve(10)==vector<int>({2,3,5,7})); assert(linear_sieve(1).empty());",
  "s-number-1": "assert(mod_pow(2,10,1000)==24); assert(mod_pow(-2,3,7)==6); assert(mod_pow(7,0,1)==0);",
  "s-search-0": "auto p=permutations(3); assert(p.size()==6); set<vector<int>>s(p.begin(),p.end()); assert(s.size()==6); assert(permutations(0).size()==1);",
  "s-mst-0": "long long I=1LL<<60; assert(prim({{0,2,7},{2,0,3},{7,3,0}})==5); assert(prim({{0,I},{I,0}})==-1); assert(prim({})==0);",
};
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "algo-demo-cpp-"));
try {
  let count = 0;
  for (const a of createFixture().algorithms) for (const s of a.snippets) {
    const input = path.join(tmp, "test.cpp"), exe = path.join(tmp, "test.exe");
    const complete = s.id === "s-fenwick-0";
    if (!complete && !checks[s.id]) throw new Error(`Missing assertions: ${s.id}`);
    fs.writeFileSync(input, s.code + (complete ? "" : `\nint main(){ ${checks[s.id]} }\n`));
    const compile = spawnSync(process.env.CXX || "g++", ["-std=c++11", "-Wall", "-Wextra", input, "-o", exe], { encoding: "utf8", windowsHide: true, timeout: 30000 });
    if (compile.status !== 0) throw new Error(`${s.id}: ${compile.error || compile.stderr}`);
    const result = spawnSync(exe, { input: complete ? "5 3\n1 2 3 4 5\n2 2 4\n1 3 2\n2 1 3\n" : "", encoding: "utf8", windowsHide: true, timeout: 3000 });
    if (result.status !== 0 || (complete && result.stdout.replace(/\r/g, "") !== "9\n8\n")) throw new Error(`${s.id}: assertions failed ${result.stderr || result.stdout}`);
    console.log(`PASS ${a.name}: ${s.title}`); count++;
  }
  console.log(`${count} templates compiled and executed with C++11.`);
  for (const p of createFixture().problems.filter(p => p.code)) {
    const input = path.join(tmp, "problem.cpp"), exe = path.join(tmp, "problem.exe");
    fs.writeFileSync(input, p.code);
    const c = spawnSync(process.env.CXX || "g++", ["-std=c++11", input, "-o", exe], { encoding: "utf8", windowsHide: true, timeout: 30000 });
    if (c.status !== 0) throw new Error(`${p.number}: ${c.stderr}`);
    for (const t of p.tests) {
      const r = spawnSync(exe, { input: t.input, encoding: "utf8", windowsHide: true, timeout: 3000 });
      if (r.status !== 0 || r.stdout.replace(/\r/g, "") !== t.output) throw new Error(`Problem example failed: ${p.number}`);
    }
    console.log(`PASS problem ${p.number}`);
  }
} finally { fs.rmSync(tmp, { recursive: true, force: true }); }
