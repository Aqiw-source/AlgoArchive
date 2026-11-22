"use strict";
const fs = require("node:fs");
const path = require("node:path");

const fenwickCode = `#include <bits/stdc++.h>
using namespace std;

struct Fenwick {
    int n;
    vector<long long> tree;
    explicit Fenwick(int size) : n(size), tree(size + 1) {}
    void add(int x, long long value) {
        for (; x <= n; x += x & -x) tree[x] += value;
    }
    long long prefix(int x) const {
        long long result = 0;
        for (; x > 0; x -= x & -x) result += tree[x];
        return result;
    }
    long long range(int l, int r) const {
        return prefix(r) - prefix(l - 1);
    }
};

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n, q;
    cin >> n >> q;
    Fenwick bit(n);
    for (int i = 1; i <= n; ++i) {
        long long x;
        cin >> x;
        bit.add(i, x);
    }
    while (q--) {
        int type, x;
        long long y;
        cin >> type >> x >> y;
        if (type == 1) bit.add(x, y);
        else cout << bit.range(x, static_cast<int>(y)) << '\\n';
    }
}
`;

const templateGroups = [
  ["fenwick", "树状数组", "数据结构", "单点修改、前缀和与区间查询。", [
    ["单点修改 + 区间查询", fenwickCode],
    ["二维树状数组", `struct Fenwick2D {
    int n, m;
    vector<vector<long long>> t;
    Fenwick2D(int n, int m) : n(n), m(m), t(n + 1, vector<long long>(m + 1)) {}
    void add(int x, int y, long long v) {
        for (int i = x; i <= n; i += i & -i)
            for (int j = y; j <= m; j += j & -j) t[i][j] += v;
    }
    long long sum(int x, int y) const {
        long long ans = 0;
        for (int i = x; i > 0; i -= i & -i)
            for (int j = y; j > 0; j -= j & -j) ans += t[i][j];
        return ans;
    }
};`],
  ]],
  ["dsu", "并查集", "数据结构", "路径压缩与按大小合并。", [
    ["路径压缩 + 按大小合并", `struct DSU {
    vector<int> p, size;
    explicit DSU(int n) : p(n), size(n, 1) { iota(p.begin(), p.end(), 0); }
    int find(int x) { return p[x] == x ? x : p[x] = find(p[x]); }
    bool unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return false;
        if (size[a] < size[b]) swap(a, b);
        p[b] = a; size[a] += size[b];
        return true;
    }
};`],
    ["可回滚并查集", `struct RollbackDSU {
    vector<int> p, size;
    vector<pair<int, int>> history;
    explicit RollbackDSU(int n) : p(n), size(n, 1) { iota(p.begin(), p.end(), 0); }
    int find(int x) const { while (p[x] != x) x = p[x]; return x; }
    int snapshot() const { return static_cast<int>(history.size()); }
    void unite(int a, int b) {
        a = find(a); b = find(b);
        if (a == b) return;
        if (size[a] < size[b]) swap(a, b);
        history.push_back({b, size[a]});
        p[b] = a; size[a] += size[b];
    }
    void rollback(int checkpoint) {
        while (snapshot() > checkpoint) {
            auto item = history.back(); history.pop_back();
            int b = item.first;
            size[p[b]] = item.second; p[b] = b;
        }
    }
};`],
  ]],
  ["segment", "线段树", "数据结构", "区间聚合与延迟标记。", [
    ["区间加 + 区间求和", `struct SegmentTree {
    int n;
    vector<long long> sum, lazy;
    explicit SegmentTree(int n) : n(n), sum(4 * n + 4), lazy(4 * n + 4) {}
    void apply(int p, int l, int r, long long v) {
        sum[p] += (r - l + 1LL) * v; lazy[p] += v;
    }
    void push(int p, int l, int r) {
        int m = (l + r) / 2;
        apply(p * 2, l, m, lazy[p]); apply(p * 2 + 1, m + 1, r, lazy[p]);
        lazy[p] = 0;
    }
    void add(int p, int l, int r, int ql, int qr, long long v) {
        if (ql <= l && r <= qr) { apply(p, l, r, v); return; }
        push(p, l, r);
        int m = (l + r) / 2;
        if (ql <= m) add(p * 2, l, m, ql, qr, v);
        if (qr > m) add(p * 2 + 1, m + 1, r, ql, qr, v);
        sum[p] = sum[p * 2] + sum[p * 2 + 1];
    }
    long long query(int p, int l, int r, int ql, int qr) {
        if (ql <= l && r <= qr) return sum[p];
        push(p, l, r);
        int m = (l + r) / 2;
        long long ans = 0;
        if (ql <= m) ans += query(p * 2, l, m, ql, qr);
        if (qr > m) ans += query(p * 2 + 1, m + 1, r, ql, qr);
        return ans;
    }
};`],
    ["静态 RMQ · Sparse Table", `struct SparseTable {
    vector<int> lg;
    vector<vector<int>> st;
    explicit SparseTable(const vector<int>& a) : lg(a.size() + 1) {
        int n = static_cast<int>(a.size()); // Requires n > 0.
        for (int i = 2; i <= n; ++i) lg[i] = lg[i / 2] + 1;
        st.assign(lg[n] + 1, vector<int>(n)); st[0] = a;
        for (int k = 1; k <= lg[n]; ++k)
            for (int i = 0; i + (1 << k) <= n; ++i)
                st[k][i] = min(st[k - 1][i], st[k - 1][i + (1 << (k - 1))]);
    }
    int query(int l, int r) const {
        int k = lg[r - l + 1];
        return min(st[k][l], st[k][r - (1 << k) + 1]);
    }
};`],
  ]],
  ["binary", "二分查找", "基础算法", "单调边界与有序数组查询。", [
    ["第一个不小于 x 的位置", `int lower_bound_index(const vector<int>& a, int x) {
    int l = 0, r = static_cast<int>(a.size());
    while (l < r) {
        int m = l + (r - l) / 2;
        if (a[m] >= x) r = m;
        else l = m + 1;
    }
    return l;
}`],
    ["单调判定 · 最小可行解", `template<class Predicate>
long long first_true(long long l, long long r, Predicate check) {
    // Preconditions: 0 <= l <= r, check(r) is true, check is monotone.
    while (l < r) {
        long long m = l + (r - l) / 2;
        if (check(m)) r = m;
        else l = m + 1;
    }
    return l;
}`],
  ]],
  ["prefix", "前缀和与差分", "基础算法", "批量求和与离线区间增量。", [
    ["一维前缀和", `vector<long long> prefix_sum(const vector<int>& a) {
    vector<long long> s(a.size() + 1);
    for (size_t i = 0; i < a.size(); ++i) s[i + 1] = s[i] + a[i];
    return s; // Half-open [l, r): s[r] - s[l].
}`],
    ["区间加 · 差分还原", `vector<long long> range_add(int n, const vector<tuple<int, int, long long>>& updates) {
    vector<long long> d(n + 1), a(n);
    for (auto item : updates) {
        int l, r; long long value;
        tie(l, r, value) = item; // Zero-based inclusive [l, r].
        d[l] += value; d[r + 1] -= value;
    }
    long long current = 0;
    for (int i = 0; i < n; ++i) a[i] = current += d[i];
    return a;
}`],
  ]],
  ["graph", "最短路", "图论", "非负边权 Dijkstra 与无权 BFS。", [
    ["Dijkstra · 优先队列", `vector<long long> dijkstra(const vector<vector<pair<int, int>>>& g, int source) {
    const long long INF = (1LL << 62);
    vector<long long> d(g.size(), INF);
    priority_queue<pair<long long, int>, vector<pair<long long, int>>, greater<pair<long long, int>>> q;
    d[source] = 0; q.push({0, source});
    while (!q.empty()) {
        auto current = q.top(); q.pop();
        int u = current.second;
        if (current.first != d[u]) continue;
        for (auto edge : g[u]) {
            int v = edge.first, w = edge.second; // Requires w >= 0.
            if (d[v] > d[u] + w) { d[v] = d[u] + w; q.push({d[v], v}); }
        }
    }
    return d;
}`],
    ["BFS · 无权最短路", `vector<int> bfs(const vector<vector<int>>& g, int source) {
    vector<int> d(g.size(), -1);
    queue<int> q; q.push(source); d[source] = 0;
    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int v : g[u]) if (d[v] == -1) {
            d[v] = d[u] + 1; q.push(v);
        }
    }
    return d;
}`],
  ]],
  ["topo", "拓扑排序", "图论", "有向无环图的依赖顺序。", [
    ["Kahn · 入度队列", `vector<int> topological_sort(const vector<vector<int>>& g) {
    vector<int> degree(g.size()), order;
    for (const auto& edges : g) for (int v : edges) ++degree[v];
    queue<int> q;
    for (int i = 0; i < static_cast<int>(g.size()); ++i) if (!degree[i]) q.push(i);
    while (!q.empty()) {
        int u = q.front(); q.pop(); order.push_back(u);
        for (int v : g[u]) if (--degree[v] == 0) q.push(v);
    }
    if (order.size() != g.size()) return {}; // Cycle detected.
    return order;
}`],
  ]],
  ["dp", "动态规划", "动态规划", "容量模型与序列状态。", [
    ["0/1 背包 · 一维滚动", `long long knapsack(int capacity, const vector<int>& weight, const vector<int>& value) {
    vector<long long> dp(capacity + 1);
    for (size_t i = 0; i < weight.size(); ++i)
        for (int j = capacity; j >= weight[i]; --j)
            dp[j] = max(dp[j], dp[j - weight[i]] + value[i]);
    return dp[capacity];
}`],
    ["LIS · 严格递增子序列", `int lis_length(const vector<int>& a) {
    vector<int> tail;
    for (int x : a) {
        auto it = lower_bound(tail.begin(), tail.end(), x);
        if (it == tail.end()) tail.push_back(x);
        else *it = x;
    }
    return static_cast<int>(tail.size());
}`],
  ]],
  ["kmp", "字符串匹配", "字符串", "前缀函数与线性时间匹配。", [
    ["KMP · 所有匹配位置", `vector<int> kmp_search(const string& text, const string& pattern) {
    if (pattern.empty()) return {};
    int m = static_cast<int>(pattern.size());
    vector<int> pi(m), answer;
    for (int i = 1, j = 0; i < m; ++i) {
        while (j && pattern[i] != pattern[j]) j = pi[j - 1];
        if (pattern[i] == pattern[j]) ++j;
        pi[i] = j;
    }
    for (int i = 0, j = 0; i < static_cast<int>(text.size()); ++i) {
        while (j && text[i] != pattern[j]) j = pi[j - 1];
        if (text[i] == pattern[j]) ++j;
        if (j == m) { answer.push_back(i - m + 1); j = pi[j - 1]; }
    }
    return answer;
}`],
    ["Z 函数", `vector<int> z_function(const string& s) {
    int n = static_cast<int>(s.size());
    vector<int> z(n);
    for (int i = 1, l = 0, r = 0; i < n; ++i) {
        if (i <= r) z[i] = min(r - i + 1, z[i - l]);
        while (i + z[i] < n && s[z[i]] == s[i + z[i]]) ++z[i];
        if (i + z[i] - 1 > r) { l = i; r = i + z[i] - 1; }
    }
    return z;
}`],
  ]],
  ["number", "数论", "数学", "质数筛与模幂。", [
    ["线性筛素数", `vector<int> linear_sieve(int n) {
    vector<int> primes;
    vector<bool> composite(n + 1);
    for (int i = 2; i <= n; ++i) {
        if (!composite[i]) primes.push_back(i);
        for (int p : primes) {
            if (p > n / i) break;
            composite[p * i] = true;
            if (i % p == 0) break;
        }
    }
    return primes;
}`],
    ["快速幂 · 64 位防乘法溢出", `long long mod_pow(long long a, long long e, long long mod) {
    // Preconditions: e >= 0, mod > 0. Requires compiler support for __int128.
    a %= mod;
    if (a < 0) a += mod;
    long long result = 1 % mod;
    while (e) {
        if (e & 1) result = static_cast<__int128>(result) * a % mod;
        a = static_cast<__int128>(a) * a % mod;
        e >>= 1;
    }
    return result;
}`],
  ]],
  ["search", "搜索与回溯", "搜索", "枚举分支与恢复现场。", [
    ["排列枚举 · 回溯", `vector<vector<int>> permutations(int n) {
    vector<vector<int>> result;
    vector<int> path;
    vector<bool> used(n);
    function<void()> dfs = [&]() {
        if (static_cast<int>(path.size()) == n) { result.push_back(path); return; }
        for (int i = 0; i < n; ++i) if (!used[i]) {
            used[i] = true; path.push_back(i);
            dfs();
            path.pop_back(); used[i] = false;
        }
    };
    dfs();
    return result;
}`],
  ]],
  ["mst", "最小生成树", "图论", "按边权扩展连通分量。", [
    ["Prim · 稠密图", `long long prim(const vector<vector<long long>>& g) {
    const long long INF = (1LL << 60); // Absent edges must equal INF.
    int n = static_cast<int>(g.size());
    if (!n) return 0;
    vector<long long> d(n, INF);
    vector<bool> used(n);
    d[0] = 0;
    long long total = 0;
    for (int step = 0; step < n; ++step) {
        int u = -1;
        for (int v = 0; v < n; ++v) if (!used[v] && (u == -1 || d[v] < d[u])) u = v;
        if (u == -1 || d[u] == INF) return -1;
        used[u] = true; total += d[u];
        for (int v = 0; v < n; ++v) if (!used[v]) d[v] = min(d[v], g[u][v]);
    }
    return total;
}`],
  ]],
];

function createFixture() {
  const created = "2026-11-14T10:00:00+00:00";
  const common = { version: 1, created_at: created, updated_at: created };
  const algorithms = templateGroups.map(([id, name, category, description, items], order) => ({
    ...common, id: `a-${id}`, name, category, description, sort_order: order,
    links: [{ id: `link-${id}`, title: "OI Wiki", url: "https://oi-wiki.org/" }],
    snippets: items.map(([title, source], i) => ({
      ...common, id: `s-${id}-${i}`, algorithm_id: `a-${id}`, algorithm_name: name,
      title, language: "cpp", code_locked: false,
      code: source.startsWith("#include") ? source : `#include <bits/stdc++.h>\nusing namespace std;\n\n${source}\n`,
    })),
  }));
  const contests = [], problems = [];
  function addContest(id, platform, title, url, rows) {
    contests.push({ ...common, id, platform, title, url, sort_order: contests.length, problem_count: rows.length });
    for (const [contest_order, [number, name, link, algorithm_id = null]] of rows.entries()) {
      problems.push({ ...common, id: `p-${id}-${number}`, platform, number, name, url: link,
        language: "cpp", code: "", code_locked: false, tests: [], contest_id: id,
        contest_title: title, contest_order, algorithm_id, algorithm_order: problems.length, global_order: problems.length,
        algorithm_name: algorithms.find(a => a.id === algorithm_id)?.name || null });
    }
  }
  const icpcTitles = ["Tatami Renovation", "Minimizing Wildlife Damage", "Seagull Population", "Decompose and Concatenate", "Cutting Tofu", "Astral Geometry", "Charity Raffle", "U-Shaped Panels", "Game of Names", "ICPC Board", "Membership Structure of a Secret Society", "Common Tangent Lines"];
  addContest("icpc-yokohama", "Codeforces", "ICPC 2025 · Asia Yokohama Regional", "https://codeforces.com/gym/106268", icpcTitles.map((name, i) => {
    const letter = String.fromCharCode(65 + i);
    return [letter, name, `https://codeforces.com/gym/106268/problem/${letter}`];
  }));
  for (const letter of "ABCDEF") {
    const problem = problems.find(p => p.id === `p-icpc-yokohama-${letter}`);
    const base = path.join(__dirname, "solutions", `yokohama-${letter.toLowerCase()}`);
    problem.code = fs.readFileSync(base + ".cpp", "utf8").replace(/\r\n/g, "\n");
    problem.tests = JSON.parse(fs.readFileSync(base + ".json", "utf8"))
      .map(({ input, output }, ordinal) => ({ ordinal, input, output }));
  }
  const lanqiao = [
    [2023, "省", [["P9239", "填空问题"], ["P9240", "冶炼金属"], ["P9241", "飞机降落"], ["P9242", "接龙数列"], ["P9243", "岛屿个数"], ["P9244", "子串简写"], ["P9245", "景区导游"], ["P9246", "砍树"], ["P12085", "整数删除"]]],
    [2023, "国", [["P9420", "子 2023 / 双子数"], ["P9421", "班级活动"], ["P9422", "合并数列"], ["P9423", "数三角"], ["P9424", "删边问题"], ["P9425", "AB 路线"], ["P9426", "抓娃娃"], ["P9427", "拼数字"], ["P9428", "逃跑"]]],
    [2024, "省", [["P10423", "填空问题"], ["P10424", "好数"], ["P10425", "R 格式"], ["P10426", "宝石组合"], ["P10427", "数字接龙"], ["P10428", "爬山"], ["P10429", "拔河"]]],
    [2024, "国", [["P10906", "合法密码"], ["P10907", "蚂蚁开会"], ["P10908", "选数概率"], ["P10909", "立定跳远"], ["P10910", "最小字符串"], ["P10911", "数位翻转"], ["P10912", "数星星"], ["P10913", "套手镯"], ["P10914", "跳石头"]]],
    [2025, "省", [["P12130", "移动距离"], ["P12131", "客流量上限"], ["P12132", "可分解的正整数"], ["P12133", "产值调整"], ["P12134", "画展布置"], ["P12135", "水质检测"], ["P12136", "生产车间"], ["P12137", "装修报价"]]],
    [2025, "国", [["P12830", "新型锁"], ["P12831", "互质藏卡"], ["P12832", "数字轮盘"], ["P12834", "项链排列"], ["P12835", "蓝桥星数字"], ["P12836", "翻倍"], ["P12838", "子串去重"], ["P12839", "涂格子"]]],
  ];
  for (const [year, stage, rows] of lanqiao) {
    const keyword = `蓝桥杯 ${year} ${stage} B`;
    addContest(`lanqiao-${year}-${stage === "省" ? "province" : "national"}`, "蓝桥杯", `蓝桥杯 ${year} ${stage}赛 · C/C++ B 组选编`, `https://www.luogu.com.cn/problem/list?keyword=${encodeURIComponent(keyword)}`, rows.map(([number, name]) => [number, name, `https://www.luogu.com.cn/problem/${number}`]));
  }
  const abc = {
    390: ["12435", "Geometric Sequence", "Paint to make a rectangle", "Stone XOR", "Vitamin Balance", "Double Sum 3", "Permutation Concatenation"],
    391: ["Lucky Direction", "Seek Grid", "Pigeonhole Query", "Gravity", "Hierarchical Majority Vote", "K-th Largest Triplet", "Many LCS"],
    392: ["Shuffled Equation", "Who is Missing?", "Bib", "Doubles", "Cables and Servers", "Insert", "Fine Triplets"],
    393: ["Poisonous Oyster", "A..B..C", "Make it Simple", "Swap to Gather", "GCD of Subset", "Prefix LIS Query", "Unevenness"],
  };
  for (const [id, titles] of Object.entries(abc)) addContest(`abc${id}`, "AtCoder", `AtCoder Beginner Contest ${id}`, `https://atcoder.jp/contests/abc${id}`, titles.map((name, i) => [String.fromCharCode(65 + i), name, `https://atcoder.jp/contests/abc${id}/tasks/abc${id}_${String.fromCharCode(97 + i)}`]));
  const hdu = ["A + B Problem", "Sum Problem", "A + B Problem II", "Max Sum", "Let the Balloon Rise", "Number Sequence"];
  addContest("hdu-practice", "HDU", "HDU · 入门练习选编", "https://acm.hdu.edu.cn/listproblem.php?vol=1", hdu.map((name, i) => [String(1000 + i), name, `https://acm.hdu.edu.cn/showproblem.php?pid=${1000 + i}`]));
  const luogu = [["P3374", "【模板】树状数组 1", "fenwick"], ["P3367", "【模板】并查集", "dsu"], ["P3375", "【模板】KMP", "kmp"], ["P3383", "【模板】线性筛素数", "number"], ["P3384", "【模板】重链剖分 / 树链剖分", "segment"], ["P3372", "【模板】线段树 1", "segment"], ["P3373", "【模板】线段树 2", "segment"], ["P3385", "【模板】负环", "graph"]];
  addContest("luogu-templates", "洛谷", "洛谷 · 数据结构与图论模板选编", "https://www.luogu.com.cn/problem/list", luogu.map(([number, name, a]) => [number, name, `https://www.luogu.com.cn/problem/${number}`, `a-${a}`]));
  addContest("acwing-weekly-163", "AcWing", "AcWing · 第 163 场周赛", "https://www.acwing.com/activity/content/4066/", [
    ["6098", "A. 局部最小值", "https://www.acwing.com/problem/content/6101/"],
    ["6099", "B. 座位", "https://www.acwing.com/problem/content/6102/"],
    ["6100", "C. 奶牛选美", "https://www.acwing.com/problem/content/6103/"],
  ]);
  const nowcoder = "https://ac.nowcoder.com/acm/contest/112576";
  addContest("nowcoder-weekly-100", "牛客", "牛客周赛 Round 100 · 题目选编", nowcoder, [
    ["A", "小红的双排列"],
    ["B", "小红的双排列拆分"],
    ["C", "小红的双排列删除"],
    ["D", "小红的双排列权值"],
    ["F", "小红的双排列期望（easy）"],
    ["G", "小红的双排列期望（hard）"],
  ].map(([number, name]) => [number, `${number}. ${name}`, `${nowcoder}/${number}`]));
  const feature = problems.find(p => p.number === "P3374");
  feature.code = fenwickCode;
  feature.tests = [{ ordinal: 0, input: "5 3\n1 2 3 4 5\n2 2 4\n1 3 2\n2 1 3\n", output: "9\n8\n" }];
  function fill(number, code, input, output) {
    const p = problems.find(p => p.number === number);
    p.code = `#include <bits/stdc++.h>\nusing namespace std;\n\n${code}\n`;
    p.tests = [{ ordinal: 0, input, output }];
  }
  fill("1000", `int main() {
    long long a, b;
    while (cin >> a >> b) cout << a + b << '\\n';
}`, "1 2\n-3 7\n", "3\n4\n");
  fill("1001", `int main() {
    long long n;
    while (cin >> n) cout << n * (n + 1) / 2 << "\\n\\n";
}`, "1\n100\n", "1\n\n5050\n\n");
  const sourceFor = id => algorithms.flatMap(a => a.snippets).find(s => s.id === id).code.replace(/^#include <bits\/stdc\+\+\.h>\nusing namespace std;\n\n/, "");
  fill("P3367", sourceFor("s-dsu-0") + `
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, m; cin >> n >> m;
    DSU d(n + 1);
    while (m--) {
        int type, a, b; cin >> type >> a >> b;
        if (type == 1) d.unite(a, b);
        else cout << (d.find(a) == d.find(b) ? "Y" : "N") << '\\n';
    }
}`, "4 4\n1 1 2\n2 1 2\n2 1 3\n1 2 3\n", "Y\nN\n");
  fill("P3375", `int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    string text, pattern; cin >> text >> pattern;
    int n = text.size(), m = pattern.size();
    vector<int> pi(m);
    for (int i = 1, j = 0; i < m; ++i) {
        while (j && pattern[i] != pattern[j]) j = pi[j - 1];
        if (pattern[i] == pattern[j]) ++j;
        pi[i] = j;
    }
    for (int i = 0, j = 0; i < n; ++i) {
        while (j && text[i] != pattern[j]) j = pi[j - 1];
        if (text[i] == pattern[j]) ++j;
        if (j == m) { cout << i - m + 2 << '\\n'; j = pi[j - 1]; }
    }
    for (int i = 0; i < m; ++i) cout << pi[i] << (i + 1 == m ? '\\n' : ' ');
}`, "ABABABC\nABA\n", "1\n3\n0 0 1\n");
  fill("P3383", sourceFor("s-number-0") + `
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, q; cin >> n >> q;
    vector<int> primes = linear_sieve(n);
    while (q--) { int k; cin >> k; cout << primes[k - 1] << '\\n'; }
}`, "10 4\n1\n2\n3\n4\n", "2\n3\n5\n7\n");
  fill("P3372", sourceFor("s-segment-0") + `
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, m; cin >> n >> m;
    SegmentTree t(n);
    for (int i = 1; i <= n; ++i) {
        long long x; cin >> x; t.add(1, 1, n, i, i, x);
    }
    while (m--) {
        int type, l, r; cin >> type >> l >> r;
        if (type == 1) { long long k; cin >> k; t.add(1, 1, n, l, r, k); }
        else cout << t.query(1, 1, n, l, r) << '\\n';
    }
}`, "5 3\n1 2 3 4 5\n2 2 4\n1 1 3 2\n2 1 3\n", "9\n12\n");
  return { profile: { name: "Aqiw · 演示题库", avatar: "" }, contests, problems, algorithms,
    problem_order_version: 1, contest_order_version: 1, algorithm_order_version: 1 };
}

module.exports = { createFixture, templateGroups };
