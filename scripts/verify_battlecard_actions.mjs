// 验证战报中心卡片收藏/飞书推送按钮 — 线上 URL headless Chrome (CDP)
// phase 1 战报中心: Heart+Send 渲染, 点 Heart → 金色实心, 弹窗不开, localStorage 写入
// phase 2 商机看板: 同项目行 heart 金色实心 (跨页同步)
// phase 3 战报中心: 未登录点 Send → toast '请先登录飞书' + 跳飞书 OAuth
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import WebSocket from "ws";

const BASE = process.argv[2] ?? "https://business-opportunity-discovery.linzhengbo111.workers.dev";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9225;

const profile = mkdtempSync(join(tmpdir(), "bc-verify-"));

const chrome = spawn(CHROME, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  `${BASE}/battlecards`,
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target = null;
for (let i = 0; i < 50; i++) {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/json/list`);
    const targets = await res.json();
    target = targets.find((t) => t.type === "page");
    if (target) break;
  } catch {}
  await sleep(200);
}
if (!target) { chrome.kill(); throw new Error("CDP target not ready"); }

const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });

let msgId = 0;
const pending = new Map();
ws.on("message", (data) => {
  const msg = JSON.parse(data.toString());
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
});
function send(method, params = {}) {
  const id = ++msgId;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res) => pending.set(id, res));
}
async function evalPage(expression) {
  const res = await send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return res.result?.result?.value ?? res.result?.exceptionDetails?.exception?.description;
}

await send("Runtime.enable");
await send("Page.enable");
await send("Page.navigate", { url: `${BASE}/battlecards` });
await sleep(5000);

// ---- phase 1: 战报中心卡片 ----
const phase1 = await evalPage(`
(async () => {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  localStorage.removeItem("saved_projects");

  let cards = [];
  for (let i = 0; i < 60; i++) {
    cards = document.querySelectorAll('div[role="button"].cursor-pointer');
    if (cards.length > 0) break;
    await sleep(500);
  }
  log.push("cards: " + cards.length);
  if (cards.length === 0) throw new Error("no battle cards rendered");

  const card = cards[0];
  window.__BC_NAME = card.querySelector("h2")?.textContent?.trim() ?? "";

  const heart = card.querySelector("button[aria-label='收藏'], button[aria-label='取消收藏']");
  const send = card.querySelector("button[aria-label='推送到飞书']");
  log.push("buttons: heart=" + !!heart + " send=" + !!send);
  if (!heart || !send) throw new Error("heart or send button missing on card");

  heart.click();
  await sleep(400);
  log.push("modal open after heart click: " + Boolean(document.querySelector("[role='dialog']")));
  const savedKeys = JSON.parse(localStorage.getItem("saved_projects") ?? "[]");
  if (savedKeys.length !== 1) throw new Error("saved key not written");
  const nowSaved = card.querySelector("button[aria-label='取消收藏']");
  if (!nowSaved) throw new Error("heart did not switch to saved state");
  const svg = nowSaved.querySelector("svg");
  const filled = svg.className.baseVal.includes("fill-current");
  const gold = nowSaved.className.includes("text-fpso-gold");
  log.push("saved heart: filled=" + filled + " gold=" + gold);
  if (!filled || !gold) throw new Error("saved heart not filled gold");
  log.push("project: " + window.__BC_NAME);
  return log.join("\\n");
})()
`);
console.log("== phase1 battlecards ==");
console.log(phase1);

// ---- phase 2: 整页跳商机看板, 验跨页同步 (导航在 eval 外等) ----
await evalPage(`location.href = "/"; "navigating"`);
await sleep(5500);

const phase2 = await evalPage(`
(async () => {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let rows = [];
  for (let i = 0; i < 60; i++) {
    rows = document.querySelectorAll(".project-row");
    if (rows.length > 0) break;
    await sleep(500);
  }
  log.push("dashboard rows: " + rows.length);
  if (rows.length === 0) throw new Error("no dashboard rows after nav");
  const savedKeys = JSON.parse(localStorage.getItem("saved_projects") ?? "[]");
  log.push("saved_projects kept: " + JSON.stringify(savedKeys));
  const syncedRows = [...rows].filter((r) => r.querySelector("button[aria-label='取消收藏']"));
  log.push("dashboard synced-filled rows: " + syncedRows.length);
  if (syncedRows.length === 0) throw new Error("no dashboard row shows saved heart");
  return log.join("\\n");
})()
`);
console.log("== phase2 dashboard sync ==");
console.log(phase2);

// ---- phase 3: 回战报中心, 未登录点 Send → toast + OAuth 跳转 ----
await evalPage(`location.href = "/battlecards"; "navigating"`);
await sleep(5500);

const phase3 = await evalPage(`
(async () => {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let cards = [];
  for (let i = 0; i < 60; i++) {
    cards = document.querySelectorAll('div[role="button"].cursor-pointer');
    if (cards.length > 0) break;
    await sleep(500);
  }
  log.push("cards: " + cards.length);
  const target = [...cards].find((c) => (c.querySelector("h2")?.textContent?.trim() ?? "") === window.__BC_NAME) ?? cards[0];
  const savedHeart = target.querySelector("button[aria-label='取消收藏']");
  log.push("heart still saved on battlecard: " + !!savedHeart);
  const send = target.querySelector("button[aria-label='推送到飞书']");
  if (!send) throw new Error("send button missing");
  send.click();
  await sleep(300);
  const toastText = [...document.querySelectorAll("[data-sonner-toast]")].map((t) => t.textContent).join("|");
  log.push("send toast: " + toastText);
  log.push("modal open after send click: " + Boolean(document.querySelector("[role='dialog']")));
  return log.join("\\n");
})()
`);
console.log("== phase3 logged-out send ==");
console.log(phase3);

// 登录跳转验证: send 点击后 login() 应跳飞书 OAuth
await sleep(2000);
const finalUrl = await evalPage(`location.href`);
console.log("after send URL: " + finalUrl);

ws.close();
chrome.kill();
await sleep(800);
try { rmSync(profile, { recursive: true, force: true, maxRetries: 3, retryDelay: 300 }); } catch {}
process.exit(0);
