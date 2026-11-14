"use strict";

(() => {
  const store = AlgoArchiveDemo.createStore(window.__DEMO_FIXTURE__, { address: location.origin + location.pathname, version: window.__DEMO_VERSION__ });
  delete window.__DEMO_FIXTURE__;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/")) return nativeFetch(input, init);
    if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    let payload = {};
    try {
      const body = init.body === undefined && input instanceof Request ? await input.clone().text() : init.body;
      if (typeof body === "string" && body) payload = JSON.parse(body);
    } catch (_) {
      return Response.json({ error: "在线演示不支持上传此文件，请使用本地版。" }, { status: 501 });
    }
    const result = store.request(init.method || (input instanceof Request ? input.method : "GET"), url.pathname, payload);
    return Response.json(result.body, { status: result.status });
  };
  const demoStorage = new Map();
  const draftKeys = new Set(["algoarchive.compiler-playground.v1", "algoarchive.playground-code-lock"]);
  // Keep demo drafts in this page's memory, not the installed app or persistent storage.
  const get = Storage.prototype.getItem, set = Storage.prototype.setItem, remove = Storage.prototype.removeItem;
  Storage.prototype.getItem = function (key) { return draftKeys.has(key) ? demoStorage.get(key) ?? null : get.call(this, key); };
  Storage.prototype.setItem = function (key, value) { if (draftKeys.has(key)) demoStorage.set(key, String(value)); else set.call(this, key, value); };
  Storage.prototype.removeItem = function (key) { if (draftKeys.has(key)) demoStorage.delete(key); else remove.call(this, key); };
  document.addEventListener("DOMContentLoaded", () => {
    document.title = "AlgoArchive · 在线演示";
    document.querySelector(".identity-copy small").textContent = "算法档案 · 演示工作空间";
    document.querySelector("[data-demo-reset]").addEventListener("click", () => {
      if (window.confirm("重置所有演示改动？不会影响本地程序。")) location.reload();
    });
  });
})();
