/* tools/mouse.mjs — 验证白天场景的两件事：
 *   1) rAF 真的在跑（frames 递增）且 mousemove 事件被引擎接收（mouse.sx 变化）
 *   2) 鼠标位置改变后，画面亮度/太阳光斑真的跟着轻微晃动（像素级采样对比）
 * 用法：node tools/mouse.mjs [day]    输出 shots/mouse.json
 */
import { spawn } from 'node:child_process';
import { writeFile, mkdir } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SHOTS = path.join(ROOT, 'shots');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const W = 1280, H = 720, PORT = 9436;
const scene = process.argv[2] || 'day';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function cdp(ws) {
  let id = 0; const pend = new Map();
  ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
  return (method, params) => new Promise((res, rej) => {
    const i = ++id; pend.set(i, (m) => res(m));
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    setTimeout(() => { if (pend.has(i)) { pend.delete(i); rej(new Error('CDP 超时 ' + method)); } }, 30000);
  });
}

await mkdir(SHOTS, { recursive: true });
const profile = path.join(SHOTS, '.profile-mouse');
const url = 'file:///' + path.join(ROOT, scene + '.html').replace(/\\/g, '/') + '?nohud=1';
const proc = spawn(CHROME, ['--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
  '--user-data-dir=' + profile, '--remote-debugging-port=' + PORT, '--window-size=' + W + ',' + H,
  '--force-device-scale-factor=1', '--allow-file-access-from-files', url], { stdio: 'ignore', windowsHide: true });

let page = null;
for (let i = 0; i < 80 && !page; i++) {
  await sleep(250);
  try { page = (await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json()).find((x) => x.type === 'page'); } catch {}
}
if (!page) { proc.kill(); throw new Error('调试端口未就绪'); }
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('WS 失败')); });
const send = cdp(ws);
await send('Runtime.enable');
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
const ev = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result.result.value;

for (let i = 0; i < 60; i++) { if (await ev('!!window.__ready')) break; await sleep(250); }
await ev("(function(){var b=document.getElementById('boot');if(b){b.style.transition='none';b.style.display='none'}})()");
await sleep(300);

/* 采样：整幅 + 右上天空（太阳方向）+ 草坪 */
const SAMPLE = `(function(){var c=document.getElementById('stage'),g=c.getContext('2d');
 function m(x0,y0,x1,y1){var d=g.getImageData(x0,y0,x1-x0,y1-y0).data,s=0,n=0;
 for(var i=0;i<d.length;i+=16){s+=d[i]*.299+d[i+1]*.587+d[i+2]*.114;n++}return +(s/n).toFixed(1)}
 return {all:m(0,0,1280,720),sky:m(922,14,1216,100),pitch:m(384,518,896,684),sun:m(1040,0,1276,96),
  frames:__engine.stats.frames,ms:+__engine.stats.ms.toFixed(2),sunVis:+__engine.state.sunVis.toFixed(3),
  mx:+__engine.mouse.sx.toFixed(3),my:+__engine.mouse.sy.toFixed(3),raw:+__engine.mouse.x.toFixed(3)};})()`;

const out = { scene, url };
const a0 = await ev(SAMPLE);
await sleep(1200);
const a1 = await ev(SAMPLE);
out.rafLive = { frames: [a0.frames, a1.frames], running: a1.frames > a0.frames, ms: a1.ms };

/* 1) 事件通路：真的派发 mousemove（左上角） */
await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: Math.round(0.14 * W), y: Math.round(0.18 * H), buttons: 0 });
await sleep(1500);
out.eventPath = { raw: (await ev(SAMPLE)).raw, expectNear: 0.14 };

/* 2) 视觉响应：把平滑值直接放到两个极端，等画面稳定后比亮度 */
for (const [tag, x, y] of [['left', 0.10, 0.15], ['right', 0.90, 0.85]]) {
  await ev(`__engine.mouse.x=${x};__engine.mouse.y=${y};__engine.mouse.sx=${x};__engine.mouse.sy=${y};`);
  await sleep(1400);
  out[tag] = await ev(SAMPLE);
  if (tag === 'left') await ev("window.__L=(function(){var c=document.getElementById('stage');return Array.prototype.slice.call(c.getContext('2d').getImageData(0,0,1280,720).data)})()");
}
const d = (k) => +(out.right[k] - out.left[k]).toFixed(1);
out.delta = { all: d('all'), sky: d('sky'), sun: d('sun'), pitch: d('pitch') };
/* 3) 整帧逐像素对比：验证"只有光在动、画面不整体位移" */
out.pixDiff = await ev(`(function(){var c=document.getElementById('stage'),R=c.getContext('2d').getImageData(0,0,1280,720).data,L=window.__L;
 var n=0,mx=0,big=0,sum=0,tot=L.length/4;
 for(var i=0;i<L.length;i+=4){var d=Math.abs(L[i]-R[i])+Math.abs(L[i+1]-R[i+1])+Math.abs(L[i+2]-R[i+2]);
  if(d>0)n++; sum+=d; if(d>mx)mx=d; if(d>18)big++;}
 return {changedPct:+(100*n/tot).toFixed(2),meanDelta:+(sum/tot).toFixed(3),maxDelta:mx,strongPct:+(100*big/tot).toFixed(3)};})()`);

await writeFile(path.join(SHOTS, 'mouse.json'), JSON.stringify(out, null, 1));
console.log(JSON.stringify(out, null, 1));
ws.close(); proc.kill();
