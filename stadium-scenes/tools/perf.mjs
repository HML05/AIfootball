/* ============================================================================
 * tools/perf.mjs — 逐段计时：找出每个场景每帧的时间花在哪
 *
 *   node tools/perf.mjs night          （默认四个场景都测）
 *
 * 做法：把引擎里各绘制阶段包一层计时器，再连续渲染 24 帧，累计每段耗时。
 * 无头软件渲染（SwiftShader）下的数字是保守上界，真机 GPU 合成会快很多。
 * ==========================================================================*/
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SHOTS = path.join(ROOT, 'shots');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const W = 1280, H = 720;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const scenes = process.argv.slice(2).length ? process.argv.slice(2) : ['day', 'dusk', 'night', 'rain'];
await mkdir(SHOTS, { recursive: true });

const PROBE = `(function(){
  var e = window.__engine;
  if (!e) return JSON.stringify({error:'no engine'});
  var S = e.S;
  var stats = {}, order = [];
  function wrap(obj, name, label) {
    if (!obj || typeof obj[name] !== 'function' || obj['__p_'+name]) return;
    var orig = obj[name];
    obj['__p_'+name] = 1;
    obj[name] = function () {
      var t0 = performance.now();
      var r = orig.apply(this, arguments);
      var d = performance.now() - t0;
      if (!stats[label]) { stats[label] = 0; order.push(label); }
      stats[label] += d;
      return r;
    };
  }
  wrap(e, '_drawSkyPaint', '天空换色');
  if (window.SNight && S.night) {
    wrap(window.SNight, 'drawSky', '星空');
    wrap(window.SNight, 'drawWorld', '城市灯/灯带/光锥/光池');
  }
  if (window.SRain && S.rain) {
    wrap(window.SRain, 'drawWorld', '雨丝/雾/溅落');
    wrap(window.SRain, 'drawFx', '玻璃雨滴+近景雨丝');
  }
  wrap(e, '_drawSun', '光源辉光');
  wrap(e, '_drawClouds', '云层');
  wrap(e, '_drawGroundShadow', '地面云影');
  wrap(e, '_drawShafts', '草皮光带');
  wrap(e, '_drawExposure', '曝光联动');
  wrap(e, '_drawFix', '暗角+颗粒');
  var origRender = e.render;
  var frameMs = 0, n = 0;
  e.render = function (t, dt) {
    var t0 = performance.now();
    origRender.call(this, t, dt);
    if (n > 3) frameMs += performance.now() - t0;
    n++;
  };
  for (var i = 0; i < 28; i++) e.render(9 + i * 0.05, 0.016);
  var frames = Math.max(1, n - 3);
  var out = {};
  for (var k = 0; k < order.length; k++) out[order[k]] = +(stats[order[k]] / frames).toFixed(2);
  e.render = origRender;
  return JSON.stringify({ frames: frames, frameMs: +(frameMs / frames).toFixed(2), stages: out });
})()`;

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

let port = 9470;
for (const scene of scenes) {
  const url = 'file:///' + path.join(ROOT, scene + '.html').replace(/\\/g, '/') + '?t=9&nohud=1' + (process.env.FXOFF ? '&fx=0' : '');
  const proc = spawn(CHROME, [
    '--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
    '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars',
    '--user-data-dir=' + path.join(SHOTS, '.profile-' + scene),
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
    await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    for (let i = 0; i < 60; i++) {
      const r = await send('Runtime.evaluate', { expression: '!!window.__ready', returnByValue: true });
      if (r.result.result.value) break;
      await sleep(250);
    }
    const r = await send('Runtime.evaluate', { expression: PROBE, returnByValue: true });
    const v = r.result.result.value;
    const o = typeof v === 'string' ? JSON.parse(v) : v;
    console.log('\n=== ' + scene + '  平均 ' + o.frameMs + ' ms/帧（' + o.frames + ' 帧）===');
    const rows = Object.entries(o.stages).sort((a, b) => b[1] - a[1]);
    for (const [k, ms] of rows) console.log('   ' + String(ms).padStart(6) + ' ms  ' + k);
    ws.close();
  } catch (e) {
    console.log('✗ ' + scene + ' ' + e.message);
  } finally {
    try { proc.kill(); } catch { /* ignore */ }
  }
  port++;
  await sleep(400);
}
