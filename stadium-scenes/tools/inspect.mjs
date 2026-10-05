/* tools/inspect.mjs — 载入某个场景页并求值一段表达式，用于确认运行时真实状态
 *   node tools/inspect.mjs day "JSON.stringify({sun:__SCENES__.day.sun,vig:__SCENES__.day.vignette,tile:[__engine.cloudTile&&__engine.cloudTile.width,__engine.cloudTile&&__engine.cloudTile.height],photo:!!__SCENES__.day.cloud.photo})"
 */
import { spawn } from 'node:child_process';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const PORT = 9441;
const scene = process.argv[2] || 'day';
const expr = process.argv[3] || '1';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const url = 'file:///' + path.join(ROOT, scene + '.html').replace(/\\/g, '/') + '?nohud=1';
const proc = spawn(CHROME, ['--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
  '--user-data-dir=' + path.join(ROOT, 'shots', '.profile-inspect-' + Date.now()), '--remote-debugging-port=' + PORT,
  '--window-size=1280,720', '--force-device-scale-factor=1', '--allow-file-access-from-files', url],
  { stdio: 'ignore', windowsHide: true });

let page = null;
for (let i = 0; i < 80 && !page; i++) {
  await sleep(250);
  try { page = (await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json()).find((x) => x.type === 'page'); } catch {}
}
if (!page) { proc.kill(); throw new Error('调试端口未就绪'); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('WS 失败')); });
let id = 0; const pend = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
const send = (method, params) => new Promise((res) => { const i = ++id; pend.set(i, res); ws.send(JSON.stringify({ id: i, method, params: params || {} })); });
await send('Runtime.enable');
for (let i = 0; i < 60; i++) { if (await ev('!!window.__ready')) break; await sleep(250); }
async function ev(e) { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }); return r.result.result.value; }
console.log(typeof (await ev(expr)) === 'string' ? await ev(expr) : JSON.stringify(await ev(expr), null, 1));
ws.close(); proc.kill();
