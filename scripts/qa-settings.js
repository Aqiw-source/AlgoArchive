"use strict";

const { chromium } = require("playwright");

(async () => {
  const baseUrl = process.env.QA_URL || "http://127.0.0.1:8876/";
  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", error => errors.push(error.message));

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  const githubHref = await page.locator(".topbar-github").getAttribute("href");
  const githubTitle = await page.locator(".topbar-github").getAttribute("title");
  const authorLabel = await page.locator(".author-badge").textContent();
  const desktopHeaderOverlap = await page.evaluate(() => {
    const tab = document.querySelector(".workspace-tab").getBoundingClientRect();
    const meta = document.querySelector(".topbar-meta").getBoundingClientRect();
    return tab.right > meta.left;
  });
  await page.evaluate(() => window.scrollTo(0, 280));
  const scrollBeforeSidebarWheel = await page.evaluate(() => window.scrollY);
  await page.locator(".workspace-sidebar").hover({ position: { x: 120, y: 280 } });
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(100);
  const scrollAfterSidebarWheel = await page.evaluate(() => window.scrollY);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.mouse.move(1000, 500);
  await page.screenshot({
    path: ".qa-data/home-desktop.png",
    fullPage: true,
  });
  await page.click("#open-profile-settings");
  await page.waitForSelector("#settings-content");
  const tabs = await page.locator("[data-settings-tab]").allTextContents();

  await page.click('[data-settings-tab="browser"]');
  const browserVisible = await page.locator("#browser-settings-form").isVisible();
  await page.click('[data-settings-tab="data"]');
  const dataPath = await page.locator(".settings-path code").first().textContent();
  await page.click('[data-settings-tab="about"]');
  const diagnosticsVisible = await page.locator(".settings-diagnostics").first().isVisible();
  await page.screenshot({
    path: ".qa-data/settings-desktop.png",
    fullPage: true,
  });
  const desktopOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  const mobileHeaderOverlap = await page.evaluate(() => {
    const tab = document.querySelector(".workspace-tab").getBoundingClientRect();
    const meta = document.querySelector(".topbar-meta").getBoundingClientRect();
    return tab.right > meta.left;
  });
  await page.screenshot({
    path: ".qa-data/home-mobile.png",
    fullPage: true,
  });
  const mobileOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth
  );
  const mobileSettingsButton = page.locator("#open-profile-settings");
  if (await mobileSettingsButton.isVisible()) {
    await mobileSettingsButton.click();
    await page.waitForSelector(".settings-shell");
    await page.screenshot({
      path: ".qa-data/settings-mobile.png",
      fullPage: true,
    });
  }

  console.log(JSON.stringify({
    githubHref,
    githubTitle,
    authorLabel,
    desktopHeaderOverlap,
    scrollBeforeSidebarWheel,
    scrollAfterSidebarWheel,
    sidebarWheelBlocked: scrollBeforeSidebarWheel === scrollAfterSidebarWheel,
    mobileHeaderOverlap,
    tabs,
    browserVisible,
    dataPath,
    diagnosticsVisible,
    desktopOverflow,
    mobileOverflow,
    errors,
  }, null, 2));
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exit(1);
});
