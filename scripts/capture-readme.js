"use strict";

const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = process.env.QA_URL || "http://127.0.0.1:8879/";
const screenshots = path.resolve(__dirname, "..", "docs", "screenshots");

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
  });

  try {
    await page.goto(baseUrl, { waitUntil: "networkidle" });
    const initial = await page.evaluate(() => fetch("/api/state").then(response => response.json()));

    async function request(route, method, payload) {
      return page.evaluate(async ({ route, method, payload }) => {
        const token = document.querySelector('meta[name="csrf-token"]').content;
        const response = await fetch(route, {
          method,
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": token,
          },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(`${method} ${route}: ${data.error || response.status}`);
        }
        return data;
      }, { route, method, payload });
    }

    let algorithm;
    let featureProblem;
    if (!initial.algorithms.length && !initial.contests.length && !initial.problems.length) {
      await request("/api/profile", "PUT", { name: "Aqiw", avatar: "" });
      algorithm = (await request("/api/algorithms", "POST", {
        name: "树状数组",
        category: "数据结构",
        description: "用二进制最低位维护前缀信息，支持单点修改和区间查询。",
        links: [
          { title: "OI Wiki · 树状数组", url: "https://oi-wiki.org/ds/fenwick/" },
          { title: "cp-algorithms · Fenwick Tree", url: "https://cp-algorithms.com/data_structures/fenwick.html" },
        ],
      })).algorithm;
      await request(`/api/algorithms/${algorithm.id}/snippets`, "POST", {
        title: "单点修改 + 区间查询",
        language: "cpp",
        code: [
          "#include <bits/stdc++.h>",
          "using namespace std;",
          "",
          "struct Fenwick {",
          "    int n;",
          "    vector<long long> tree;",
          "    Fenwick(int n) : n(n), tree(n + 1) {}",
          "    void add(int x, long long value) {",
          "        for (; x <= n; x += x & -x) tree[x] += value;",
          "    }",
          "    long long sum(int x) const {",
          "        long long result = 0;",
          "        for (; x > 0; x -= x & -x) result += tree[x];",
          "        return result;",
          "    }",
          "};",
          "",
          "int main() {",
          "    ios::sync_with_stdio(false);",
          "    cin.tie(nullptr);",
          "    return 0;",
          "}",
          "",
        ].join("\n"),
      });

      const contest = (await request("/api/contests", "POST", {
        platform: "codeforces",
        title: "Codeforces Round 1000 (Div. 2)",
        url: "https://codeforces.com/contest/2062",
      })).contest;
      const baseProblem = {
        platform: "codeforces",
        url: "https://codeforces.com/contest/2062/problem/A",
        language: "cpp",
        contest_id: contest.id,
      };
      await request("/api/problems", "POST", {
        ...baseProblem,
        number: "A",
        name: "Minimal Coprime",
        code: [
          "#include <bits/stdc++.h>",
          "using namespace std;",
          "",
          "int main() {",
          "    ios::sync_with_stdio(false);",
          "    cin.tie(nullptr);",
          "    int T;",
          "    cin >> T;",
          "    while (T--) {",
          "        int l, r;",
          "        cin >> l >> r;",
          "        cout << (l == 1 && r == 1 ? 1 : r - l + 1) << '\\n';",
          "    }",
          "    return 0;",
          "}",
          "",
        ].join("\n"),
      });
      await request("/api/problems", "POST", {
        ...baseProblem,
        url: "https://codeforces.com/contest/2062/problem/B",
        number: "B",
        name: "Subsequence Update",
        code: [
          "#include <bits/stdc++.h>",
          "using namespace std;",
          "",
          "int main() {",
          "    ios::sync_with_stdio(false);",
          "    cin.tie(nullptr);",
          "    int T;",
          "    cin >> T;",
          "    while (T--) {",
          "        int n, l, r;",
          "        cin >> n >> l >> r;",
          "        vector<long long> a(n);",
          "        for (long long &value : a) cin >> value;",
          "        cout << accumulate(a.begin(), a.end(), 0LL) << '\\n';",
          "    }",
          "}",
          "",
        ].join("\n"),
      });
      featureProblem = (await request("/api/problems", "POST", {
        ...baseProblem,
        url: "https://codeforces.com/contest/2062/problem/C",
        number: "C",
        name: "Remove Exactly Two",
        algorithm_id: algorithm.id,
        code: [
          "#include <bits/stdc++.h>",
          "using namespace std;",
          "",
          "struct Fenwick {",
          "    int n;",
          "    vector<long long> tree;",
          "    explicit Fenwick(int size) : n(size), tree(n + 1) {}",
          "    void add(int index, long long value) {",
          "        for (; index <= n; index += index & -index)",
          "            tree[index] += value;",
          "    }",
          "    long long prefix(int index) const {",
          "        long long result = 0;",
          "        for (; index > 0; index -= index & -index)",
          "            result += tree[index];",
          "        return result;",
          "    }",
          "};",
          "",
          "int main() {",
          "    ios::sync_with_stdio(false);",
          "    cin.tie(nullptr);",
          "    int n, q;",
          "    cin >> n >> q;",
          "    Fenwick bit(n);",
          "    while (q--) {",
          "        int type, x;",
          "        cin >> type >> x;",
          "        if (type == 1) bit.add(x, 1);",
          "        else cout << bit.prefix(x) << '\\n';",
          "    }",
          "}",
          "",
        ].join("\n"),
      })).problem;
    } else {
      algorithm = initial.algorithms[0];
      featureProblem = initial.problems.find(problem => problem.algorithm_id === algorithm?.id) || initial.problems[0];
    }

    if (!algorithm || !featureProblem) {
      throw new Error("演示数据不完整，请使用新的空数据目录运行截图脚本。");
    }

    await page.reload({ waitUntil: "networkidle" });
    await page.goto(`${baseUrl}#home`, { waitUntil: "networkidle" });
    await page.waitForSelector(".stats-grid");
    await page.screenshot({ path: path.join(screenshots, "dashboard.png") });

    await page.goto(`${baseUrl}#algorithm/${algorithm.id}`, { waitUntil: "networkidle" });
    await page.waitForSelector(".algorithm-info");
    await page.screenshot({ path: path.join(screenshots, "algorithm.png") });

    await page.goto(`${baseUrl}#problem/${featureProblem.id}`, { waitUntil: "networkidle" });
    await page.waitForSelector("#code-input");
    await page.screenshot({ path: path.join(screenshots, "editor.png") });

    await page.click("#open-profile-settings");
    await page.click('[data-settings-tab="browser"]');
    await page.waitForSelector("#browser-settings-form");
    await page.screenshot({ path: path.join(screenshots, "settings.png") });

    console.log(JSON.stringify({
      algorithm_id: algorithm.id,
      problem_id: featureProblem.id,
      screenshots: ["dashboard.png", "algorithm.png", "editor.png", "settings.png"],
    }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
