// 验证商机看板项目卡片收藏标记 — 线上 URL headless Chrome (CDP)
// 检查: 1) 已收藏项目卡片右上角金色实心 Heart
//      2) 未收藏 hover 时显空心 Heart, 点击收藏不打开详情
//      3) 再点击取消收藏, localStorage 同步
//      4) 详情弹窗收藏按钮与列表 heart 同步
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import WebSocket from "ws";

const URL = process.argv[2] ?? "https://business-opportunity-discovery.linzhengbo111.workers.dev";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9223;

const profile = mkdtempSync(join(tmpdir(), "heart-verify-"));

const chrome = spawn(CHROME, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  URL,
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 等调试端口就绪
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

await send("Runtime.enable");
await send("Page.enable");
// 等页面 load
await send("Page.navigate", { url: URL });
await sleep(4000);

const script = `
(async () => {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  let rows = [];
  for (let i = 0; i < 60; i++) {
    rows = document.querySelectorAll(".project-row");
    if (rows.length > 0) break;
    await sleep(500);
  }
  log.push("rows: " + rows.length);
  if (rows.length === 0) throw new Error("no project rows rendered");

  // 1) 找未收藏 heart 按钮
  let unsavedBtn = null;
  for (const r of rows) {
    const btn = r.querySelector("button[aria-label='收藏']");
    if (btn) { unsavedBtn = btn; break; }
  }
  if (!unsavedBtn) throw new Error("no unsaved heart button found");
  const hidden = unsavedBtn.className.includes("opacity-0");
  log.push("unsaved heart hidden-by-default: " + hidden);

  // 2) 点击空心 Heart → 收藏, 详情弹窗不开
  unsavedBtn.click();
  await sleep(300);
  const modalOpen = Boolean(document.querySelector("[role='dialog']"));
  log.push("modal open after heart click: " + modalOpen);
  if (modalOpen) throw new Error("heart click opened detail modal");
  log.push("saved_projects after click: " + localStorage.getItem("saved_projects"));

  // 3) 按钮状态翻转: 金色实心常显
  const row = unsavedBtn.closest(".project-row");
  const nowSavedBtn = row.querySelector("button[aria-label='取消收藏']");
  if (!nowSavedBtn) throw new Error("heart did not switch to saved state");
  const svg = nowSavedBtn.querySelector("svg");
  const filled = svg.className.baseVal.includes("fill-current");
  const gold = nowSavedBtn.className.includes("text-fpso-gold");
  const visibleAlways = !nowSavedBtn.className.includes("opacity-0");
  log.push("saved heart: filled=" + filled + " gold=" + gold + " always-visible=" + visibleAlways);

  // 4) 再点击取消收藏
  nowSavedBtn.click();
  await sleep(300);
  log.push("saved_projects after unclick: " + localStorage.getItem("saved_projects"));
  if (JSON.parse(localStorage.getItem("saved_projects") ?? "[]").length !== 0)
    throw new Error("unclick did not clear saved key");

  // 5) 详情弹窗收藏 → 列表 heart 同步
  row.click();
  await sleep(800);
  const detailSaveBtn = document.querySelector("button[aria-label='收藏']");
  if (detailSaveBtn) {
    detailSaveBtn.click();
    await sleep(300);
    const listHearts = row.querySelectorAll("svg.fill-current");
    log.push("list heart synced after detail save: " + (listHearts.length > 0));
    const cancelBtn = document.querySelector("button[aria-label='取消收藏']");
    if (cancelBtn) { cancelBtn.click(); await sleep(300); }
  } else {
    log.push("detail modal save button not found");
  }

  return log.join("\\n");
})()
`;

const res = await send("Runtime.evaluate", {
  expression: script,
  awaitPromise: true,
  returnByValue: true,
});
const result = res.result?.result?.value ?? res.result?.exceptionDetails?.exception?.description;
console.log(result ?? JSON.stringify(res.result));

ws.close();
chrome.kill();
rmSync(profile, { recursive: true, force: true });
process.exit(0);
