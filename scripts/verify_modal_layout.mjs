// 验证详情弹窗新布局 — 区块结构 + 字段无丢失
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import WebSocket from "ws";

const URL = process.argv[2] ?? "https://business-opportunity-discovery.linzhengbo111.workers.dev";
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9224;

const profile = mkdtempSync(join(tmpdir(), "modal-verify-"));
const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, URL,
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
await send("Runtime.enable");
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
  if (rows.length === 0) throw new Error("no rows");
  log.push("rows: " + rows.length);

  // 打开第一个项目详情
  rows[0].click();
  await sleep(1200);
  const modal = document.querySelector('[class*="max-h-[85vh]"][class*="flex-col"]');
  log.push("modal open: " + Boolean(modal));

  // 区块标题
  const sectionHeaders = [...document.querySelectorAll("h4")]
    .map((h) => h.textContent.trim())
    .filter((t) => t.length > 0);
  log.push("sections: " + JSON.stringify(sectionHeaders));

  const text = modal ? modal.innerText.toLowerCase() : "";
  const has = (needle) => text.includes(needle.toLowerCase());

  // ① 头部
  log.push("name shown: " + has(rows[0].querySelector("h3").textContent.trim()));
  // ② 关键参数
  log.push("grid cells: " + (modal?.querySelectorAll(".grid.grid-cols-2 > div").length ?? 0));
  log.push("查看原文 collapsible: " + Boolean(modal?.querySelector("details summary")));
  // ③ 采购链与来源
  log.push("procurement section: " + has("Procurement Chain & Source"));
  log.push("抓取日期: " + has("抓取日期"));
  // ④ 商机分析
  log.push("Opportunity Analysis: " + has("Opportunity Analysis"));
  log.push("采购时间窗 label: " + has("采购时间窗"));
  log.push("dimension details: " + has("Show dimension details"));
  // ⑤ 材质与产品
  log.push("Materials & Products: " + has("Materials & Products"));
  log.push("推荐材质 or 推荐产品 label: " + (has("推荐材质") || has("推荐产品")));
  // ⑥ 行动区
  log.push("Actions: " + has("Actions"));
  log.push("AI 分析摘要: " + has("AI 分析摘要"));
  log.push("生成作战卡: " + has("生成作战卡"));
  log.push("生成开发信: " + has("生成开发信"));
  log.push("FollowUpStatus: " + has("Follow-up"));

  // 旧字段都在: 不锈钢牌号 / 应用场景 / 腐蚀介质 / 原文摘要
  log.push("raw summary in details: " + Boolean(modal?.querySelector("details p")));
  // 找有数据的项目验证牌号/腐蚀介质 — 遍历行找有 stainlessSteel 或腐蚀介质 chip 的
  const modalText = text;
  log.push("modal length chars: " + modalText.length);

  return log.join("\\n");
})()
`;

const res = await send("Runtime.evaluate", { expression: script, awaitPromise: true, returnByValue: true });
const result = res.result?.result?.value ?? res.result?.exceptionDetails?.exception?.description;
console.log(result ?? JSON.stringify(res.result));
ws.close();
chrome.kill();
await sleep(500);
try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch {}
process.exit(0);
