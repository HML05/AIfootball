/* ============================================================================
 * tools/live.mjs — 验证 rAF 动画循环真的在跑（不是只靠 renderAt 定格出来的帧）
 *
 *   node tools/live.mjs            四个场景都测
 *   node tools/live.mjs rain       只测某个场景
 *
 * 做法：正常加载页面（不注入任何定格脚本），静置 3 秒后读 engine.stats.frames
 *       与 state（云相位/云遮日），再等 2 秒读第二次，比较相位是否在变。
 * 输出：控制台表格 + shots/live.json
 * ==========================================================================*/
import { spawn } from 'node:child_process';
import { writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SHOTS = path.join(ROOT, 'shots');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const W = 1280, H = 720;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const scenes = process.argv.slice(2).length ? process.argv.slice(2) : ['day', 'dusk', 'night', 'rain'];
await mkdir(SHOTS, { recursive: true });

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

const READ = `(function(){var e=window.__engine;if(!e)return JSON.stringify({error:'no engine'});
 return JSON.stringify({frames:e.stats.frames,ms:+(e.stats.ms).toFixed(2),fps:+(e.stats.fps).toFixed(1),
  t:+(e._t||0).toFixed(2),sunVis:+(e.state.sunVis||0).toFixed(3),occ:+(e.state.occ||0).toFixed(3),
  off1:+(e.state.cloudOff1||0).toFixed(1),off2:+(e.state.cloudOff2||0).toFixed(1),
  err:(e.errors||[]).length});})()`;

const out = {};
let port = 9510;
for (const scene of scenes) {
  const url = 'file:///' + path.join(ROOT, scene + '.html').replace(/\\/g, '/');
  const proc = spawn(CHROME, [
    '--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
    '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars',
    '--user-data-dir=' + path.join(SHOTS, '.profile-live-' + scene),
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
    for (let i = 0; i < 60; i++) {
      const r = await send('Runtime.evaluate', { expression: '!!window.__ready', returnByValue: true });
      if (r.result.result.value) break;
      await sleep(250);
    }
    const read = async () => {
      const r = await send('Runtime.evaluate', { expression: READ, returnByValue: true });
      const v = r.result.result.value;
      return typeof v === 'string' ? JSON.parse(v) : v;
    };
    await sleep(3000);
    const a = await read();
    await sleep(2000);
    const b = await read();
    out[scene] = { a, b };
    const moved = Math.abs(b.off1 - a.off1) + Math.abs(b.off2 - a.off2) > 0.5;
    console.log(scene.padEnd(6) +
      ' frames ' + a.frames + '→' + b.frames +
      '  fps≈' + (b.frames > a.frames ? ((b.frames - a.frames) / 2).toFixed(1) : '0') +
      '  ' + a.ms + 'ms/帧' +
      '  云相位 ' + a.off1 + '/' + a.off2 + ' → ' + b.off1 + '/' + b.off2 +
      '  sunVis ' + a.sunVis + '→' + b.sunVis +
      (moved ? '  ✔ 在动' : '  ⚠ 未动') +
      (b.err ? '  ⚠ errors=' + b.err : ''));
    ws.close();
  } catch (e) {
    console.log('✗ ' + scene + ' ' + e.message);
  } finally {
    try { proc.kill(); } catch { /* ignore */ }
  }
  port++;
  await sleep(400);
}
await writeFile(path.join(SHOTS, 'live.json'), JSON.stringify(out, null, 2), 'utf8');
console.log('诊断写入 shots/live.json');
