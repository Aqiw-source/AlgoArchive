"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { createFixture } = require("../demo/fixture.cjs");
const root = path.resolve(__dirname, "..");

function buildDemo(output, base = "/AlgoArchive/") {
  if (!/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(base)) throw new Error("Invalid demo base path");
  const out = path.resolve(output);
  if (fs.existsSync(out) && fs.readdirSync(out).length) throw new Error("Demo output must be an empty directory");
  fs.mkdirSync(out, { recursive: true });
  fs.cpSync(path.join(root, "web"), out, { recursive: true });
  const version = fs.readFileSync(path.join(root, "app.py"), "utf8").match(/APP_VERSION = "([\d.]+)"/)[1];
  const scripts = `<script src="${base}demo-store.js" defer></script>\n<script src="${base}demo-data.js" defer></script>\n<script src="${base}demo.js" defer></script>\n<link rel="stylesheet" href="${base}demo.css">\n`;
  let html = fs.readFileSync(path.join(out, "index.html"), "utf8")
    .replaceAll('__CSRF_TOKEN__', 'isolated-online-demo')
    .replaceAll('__USER_NAME__', 'Aqiw · 演示题库')
    .replaceAll('href="/', `href="${base}`).replaceAll('src="/', `src="${base}`)
    .replace(`<script src="${base}app.js`, scripts + `<script src="${base}app.js`);
  html = html.replace('<body>', `<body>\n<div class="demo-notice" role="note"><p><strong>在线演示</strong>改动仅在当前页面生效，刷新重置；编译运行需使用本地版。</p><nav aria-label="演示操作"><a href="https://github.com/Aqiw-source/AlgoArchive/releases/latest" target="_blank" rel="noopener noreferrer">下载本地版</a><button type="button" class="demo-reset" data-demo-reset aria-label="重置演示" title="重置演示"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11a9 9 0 1 1 2.5 6.2M3 4v7h7"/></svg></button></nav></div>`);
  fs.writeFileSync(path.join(out, "index.html"), html);
  fs.writeFileSync(path.join(out, "app.js"), fs.readFileSync(path.join(out, "app.js"), "utf8").replaceAll('src="/', `src="${base}`).replaceAll('href="/', `href="${base}`));
  for (const [src, name] of [["store.js", "demo-store.js"], ["browser.js", "demo.js"], ["demo.css", "demo.css"]]) fs.copyFileSync(path.join(root, "demo", src), path.join(out, name));
  fs.writeFileSync(path.join(out, "demo-data.js"), `"use strict";\nwindow.__DEMO_VERSION__=${JSON.stringify(version)};\nwindow.__DEMO_FIXTURE__=${JSON.stringify(createFixture()).replaceAll("<", "\\u003c")};\n`);
  fs.copyFileSync(path.join(root, "demo", "SOURCES.md"), path.join(out, "DEMO-SOURCES.md"));
  fs.writeFileSync(path.join(out, ".nojekyll"), "");
  const files = fs.readdirSync(out, { recursive: true }).map(String);
  if (files.some(name => /\.py$|sqlite|config\.json$|runtime[\\/]|codes[\\/]/i.test(name))) throw new Error("Unsafe demo output");
  return { output: out, base, version, files: files.length };
}
if (require.main === module) console.log(JSON.stringify(buildDemo(process.argv[2] || path.join(root, "dist", "demo"), process.argv[3] || "/AlgoArchive/")));
module.exports = { buildDemo };
