/* ============================================================================
 * tools/shotpage.mjs — 给任意本地页面拍一张整页截图（用于验收 index.html 这类静态页）
 *
 *   node tools/shotpage.mjs index.html shots/_index.png 1440 1000
 *
 * 和 shot.mjs 一样走 CDP：无头 Chrome 的 --screenshot 命令行方式在
 * "进程提前返回 / 用户目录被占用" 时会拍到空白，所以统一用调试协议。
 * ==========================================================================*/
import { spawn } from 'node:child_process';
import { writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [rel, out, wArg, hArg, waitArg, evalArg] = process.argv.slice(2);
if (!rel || !out) {
  console.error('用法: node tools/shotpage.mjs <页面> <输出png> [宽] [高] [等待ms]');
  process.exit(2);
}
const W = Number(wArg) || 1440;
const H = Number(hArg) || 1000;
const WAIT = Number(waitArg) || 1200;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await mkdir(path.dirname(path.resolve(ROOT, out)), { recursive: true });

function cdp(ws) {
  let id = 0;
  const pend = new Map();
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  };
  return (method, params) => new Promise((res, rej) => {
    const i = ++id;
    pend.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    setTimeout(() => { if (pend.has(i)) { pend.delete(i); rej(new Error('CDP 超时: ' + method)); } }, 60000);
  });
}

const port = 9499;
const url = 'file:///' + path.resolve(ROOT, rel).replace(/\\/g, '/');
const proc = spawn(CHROME, [
  '--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars',
  '--user-data-dir=' + path.join(ROOT, 'shots', '.profile-page'),
  '--remote-debugging-port=' + port, '--window-size=' + W + ',' + H,
  '--force-device-scale-factor=1', '--allow-file-access-from-files', url
], { stdio: 'ignore', windowsHide: true });

try {
  let page = null;
  for (let i = 0; i < 100 && !page; i++) {
    await sleep(200);
    try {
      const list = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
      page = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
    } catch { /* 端口没起来 */ }
  }
  if (!page) throw new Error('调试端口未就绪');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('WS 失败')); });
  const send = cdp(ws);
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await sleep(WAIT);
  if (evalArg) {                                   // 可选：截图前先在页面里求值（用来强制切换渲染路径）
    const e = await send('Runtime.evaluate', { expression: evalArg, returnByValue: true });
    console.log('eval → ' + JSON.stringify(e.result.result && e.result.result.value));
    await sleep(500);
  }
  const r = await send('Runtime.evaluate', {
    expression: 'JSON.stringify({title:document.title, h:document.body.scrollHeight, imgs:[].map.call(document.images,function(i){return i.naturalWidth+"x"+i.naturalHeight})})',
    returnByValue: true
  });
  const png = await send('Page.captureScreenshot', { format: 'png' });
  const buf = Buffer.from(png.result.data, 'base64');
  await writeFile(path.resolve(ROOT, out), buf);
  console.log('✔ ' + out + '  ' + (buf.length / 1024).toFixed(0) + ' KB  ' + r.result.result.value);
  ws.close();
} catch (e) {
  console.error('✗ ' + e.message);
  process.exitCode = 1;
} finally {
  try { proc.kill(); } catch { /* ignore */ }
}
