/* ============================================================================
 * tools/videoframe.mjs — 从本地 mp4 里抓几帧 PNG（用无头 Chrome 解码，无需 ffmpeg）
 *
 *   node tools/videoframe.mjs "<mp4 绝对路径>" 1,3,5 shots/_demo
 *
 * 用于把"用户给的演示视频"变成可以直接看的静帧，好照着调光效。
 * ==========================================================================*/
import { spawn } from 'node:child_process';
import { writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [video, timesArg, outPrefix] = process.argv.slice(2);
if (!video || !timesArg || !outPrefix) {
  console.error('用法: node tools/videoframe.mjs <mp4> <秒,秒,...> <输出前缀>');
  process.exit(2);
}
const times = timesArg.split(',').map((s) => Number(s));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await mkdir(path.join(ROOT, 'shots'), { recursive: true });

const html = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:#000">
<video id="v" src=${JSON.stringify('file:///' + video.replace(/\\/g, '/'))} muted playsinline></video>
<canvas id="c"></canvas>
<script>
window.__err = '';
window.__readyV = false;
const v = document.getElementById('v'), c = document.getElementById('c'), x = c.getContext('2d');
v.onloadeddata = function () { window.__readyV = true; };
v.onerror = function () { window.__err = 'video error ' + (v.error && v.error.code); };
window.__meta = function () { return { w: v.videoWidth, h: v.videoHeight, d: v.duration, ready: window.__readyV, err: window.__err }; };
window.__grab = function (t) {
  return new Promise(function (res) {
    v.currentTime = t;
    const done = function () {
      c.width = v.videoWidth; c.height = v.videoHeight;
      x.drawImage(v, 0, 0, c.width, c.height);
      res(c.toDataURL('image/png'));
    };
    if (Math.abs(v.currentTime - t) < 0.05 && v.readyState >= 2) { done(); return; }
    v.onseeked = done;
    setTimeout(done, 3000);
  });
};
</script></body>`;
const htmlPath = path.join(ROOT, 'shots', '_vf.html');
await writeFile(htmlPath, html);

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

const port = 9501;
const proc = spawn(CHROME, [
  '--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
  '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars', '--mute-audio',
  '--user-data-dir=' + path.join(ROOT, 'shots', '.profile-vf'),
  '--remote-debugging-port=' + port, '--window-size=1280,720',
  '--force-device-scale-factor=1', '--allow-file-access-from-files',
  'file:///' + htmlPath.replace(/\\/g, '/')
], { stdio: 'ignore', windowsHide: true });

try {
  let page = null;
  for (let i = 0; i < 100 && !page; i++) {
    await sleep(200);
    try {
      const list = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
      page = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
    } catch { /* 端口还没起来 */ }
  }
  if (!page) throw new Error('调试端口未就绪');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('WS 失败')); });
  const send = cdp(ws);
  await send('Runtime.enable');
  await sleep(2500);
  const meta = await send('Runtime.evaluate', { expression: 'JSON.stringify(window.__meta())', returnByValue: true });
  console.log('元信息 ' + meta.result.result.value);
  for (const t of times) {
    const r = await send('Runtime.evaluate', {
      expression: 'window.__grab(' + t + ')', awaitPromise: true, returnByValue: true
    });
    const url = r.result.result.value;
    if (typeof url !== 'string' || url.indexOf('base64,') < 0) { console.error('✗ t=' + t + ' 抓帧失败'); continue; }
    const buf = Buffer.from(url.split('base64,')[1], 'base64');
    const out = outPrefix + '_t' + t + '.png';
    await writeFile(path.resolve(ROOT, out), buf);
    console.log('✔ ' + out + '  ' + (buf.length / 1024).toFixed(0) + ' KB');
  }
  ws.close();
} catch (e) {
  console.error('✗ ' + e.message);
  process.exitCode = 1;
} finally {
  try { proc.kill(); } catch { /* ignore */ }
}
