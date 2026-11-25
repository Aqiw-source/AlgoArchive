"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { createFixture } = require("../demo/fixture.cjs");
const root = path.resolve(__dirname, "..");

function buildDemo(output, base = "/AlgoArchive/") {
  if (!/^\/(?:[A-Za-z0-9_-]+\/)*$/.test(base)) throw new Error("Invalid demo base path");
  const out = path.resolve(output);
  if (fs.existsSync(out) && fs.readdirSync(out).length) throw new Error("Demo output must be an empty directory");
  fs.mkdirSync(out, { recursive: true });
  fs.cpSync(path.join(root, "web"), out, { recursive: true });
  const version = fs.readFileSync(path.join(root, "app.py"), "utf8").match(/APP_VERSION = "([\d.]+)"/)[1];
  const demoData = `"use strict";\nwindow.__DEMO_VERSION__=${JSON.stringify(version)};\nwindow.__DEMO_FIXTURE__=${JSON.stringify(createFixture()).replaceAll("<", "\\u003c")};\n`;
  const dataVersion = createHash("sha256").update(demoData).digest("hex").slice(0, 16);
  const scripts = `<script src="${base}demo-store.js" defer></script>\n<script src="${base}demo-data.js?v=${dataVersion}" defer></script>\n<script src="${base}demo.js" defer></script>\n<link rel="stylesheet" href="${base}demo.css">\n`;
  let html = fs.readFileSync(path.join(out, "index.html"), "utf8")
    .replaceAll('__CSRF_TOKEN__', 'isolated-online-demo')
    .replaceAll('__USER_NAME__', 'Aqiw · 演示题库')
    .replaceAll('href="/', `href="${base}`).replaceAll('src="/', `src="${base}`)
    .replace(`<script src="${base}app.js`, scripts + `<script src="${base}app.js`);
  const localStatus = '<div class="topbar-status"><span class="online-dot"></span>本地</div>';
  if (!html.includes(localStatus)) throw new Error("Demo topbar insertion point not found");
  html = html.replace("在新标签页打开离线使用手册", "在新标签页打开演示使用手册");
  html = html.replace(localStatus, `<div class="topbar-status" data-demo-info tabindex="0" title="改动仅在当前页面生效，刷新重置；编译运行需使用本地版。" aria-label="在线演示：改动仅在当前页面生效，刷新重置；编译运行需使用本地版。">在线演示</div><button type="button" class="topbar-github demo-reset" data-demo-reset aria-label="重置演示" title="重置演示"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11a9 9 0 1 1 2.5 6.2M3 4v7h7"/></svg></button><a class="topbar-github demo-download" data-demo-download href="https://github.com/Aqiw-source/AlgoArchive/releases/latest" target="_blank" rel="noopener noreferrer">下载本地版</a>`);
  fs.writeFileSync(path.join(out, "index.html"), html);
  const manual = path.join(out, "manual.html");
  let manualHtml = fs.readFileSync(manual, "utf8");
  const editionNote = '<div class="edition-note"><b>Windows 本地版</b><span>本地版可离线查阅手册，题库保存在本机。</span></div>';
  if (!manualHtml.includes(editionNote)) throw new Error("Manual edition note insertion point not found");
  const intro = /<p class="hero-desc" data-demo-intro>[\s\S]*?<\/p>/;
  if (!intro.test(manualHtml)) throw new Error("Manual demo intro insertion point not found");
  const demoEntry = /<a class="button secondary" href="https:\/\/aqiw-source\.github\.io\/AlgoArchive\/"[\s\S]*?打开在线演示<\/a>/;
  if (!demoEntry.test(manualHtml)) throw new Error("Manual demo entry insertion point not found");
  const demoDownload = '<a class="button primary" href="https://github.com/Aqiw-source/AlgoArchive/releases/latest" target="_blank" rel="noopener noreferrer">下载 Windows 本地版</a>';
  manualHtml = manualHtml.replace(intro, '<p class="hero-desc">GitHub Pages 提供静态演示和示例题库；改动仅保存在当前页面；刷新后重置。此页面不能调用本机编译器、创建 Windows 快捷方式或执行其他系统操作。</p>')
    .replace(editionNote, '<div class="edition-note"><b>静态在线演示</b><span>页面仅操作示例数据；不会调用本机程序或下载、运行工具。需编译或创建快捷方式时，请使用 Windows 本地版。</span></div>')
    .replace(demoEntry, match => match + demoDownload);
  fs.writeFileSync(manual, manualHtml);
  // Identify the static edition even when served from localhost on a custom port.
  for (const entry of fs.readdirSync(out, { recursive: true }).filter(name => name.endsWith('.html') && name !== 'index.html')) {
    const file = path.join(out, entry);
    const source = fs.readFileSync(file, 'utf8');
    fs.writeFileSync(file, source.replace(/<html\b/, '<html data-static-demo'));
  }
  fs.writeFileSync(path.join(out, "app.js"), fs.readFileSync(path.join(out, "app.js"), "utf8")
    .replaceAll('src="/', `src="${base}`).replaceAll('href="/', `href="${base}`)
    .replace("document.title='算法档案';", "document.title='AlgoArchive · 在线演示';"));
  for (const [src, name] of [["store.js", "demo-store.js"], ["browser.js", "demo.js"], ["demo.css", "demo.css"]]) fs.copyFileSync(path.join(root, "demo", src), path.join(out, name));
  fs.writeFileSync(path.join(out, "demo-data.js"), demoData);
  fs.copyFileSync(path.join(root, "demo", "SOURCES.md"), path.join(out, "DEMO-SOURCES.md"));
  for (const name of ["LICENSE", "DISCLAIMER.md", "THIRD_PARTY.txt"]) fs.copyFileSync(path.join(root, name), path.join(out, name));
  fs.cpSync(path.join(root, "licenses"), path.join(out, "licenses"), { recursive: true });
  fs.writeFileSync(path.join(out, ".nojekyll"), "");
  const files = fs.readdirSync(out, { recursive: true }).map(String);
  if (files.some(name => /\.py$|sqlite|config\.json$|runtime[\\/]|codes[\\/]/i.test(name))) throw new Error("Unsafe demo output");
  return { output: out, base, version, files: files.length };
}
if (require.main === module) console.log(JSON.stringify(buildDemo(process.argv[2] || path.join(root, "dist", "demo"), process.argv[3] || "/AlgoArchive/")));
module.exports = { buildDemo };
