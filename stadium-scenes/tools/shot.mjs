/* ============================================================================
 * tools/shot.mjs — 用 Chrome DevTools 协议给四个场景截图 + 抓运行时诊断
 *
 *   node tools/shot.mjs                         拍 day/dusk/night/rain 各两帧（t=9、t=39）
 *   node tools/shot.mjs rain:9,24,60            指定场景与时间点
 *
 * 说明：无头环境里 requestAnimationFrame 不一定会持续触发，所以这里不依赖
 *       rAF —— 直接调用 engine.renderAt(t) 同步渲染一帧后再截图，结果完全确定。
 *       同时用 30 帧的平均耗时衡量渲染性能（软件渲染，属保守上界）。
 * 输出：shots/<name>.png、shots/diag.json
 * ==========================================================================*/
import { spawn } from 'node:child_process';
import { writeFile, mkdir, rm } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const SHOTS = path.join(ROOT, 'shots');
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const W = 1280, H = 720;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const argv = process.argv.slice(2);
const jobs = (argv.length ? argv : ['day:9,39', 'dusk:9,39', 'night:9,39', 'rain:9,39'])
  .map((s) => {
    const [scene, ts] = s.split(':');
    return { scene, times: (ts || '9').split(',').map(Number) };
  });

await mkdir(SHOTS, { recursive: true });

function cdp(ws) {
  let id = 0;
  const pend = new Map();
  const events = [];
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
    else if (m.method) events.push(m);
  };
  const send = (method, params) => new Promise((res, rej) => {
    const i = ++id;
    pend.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
    setTimeout(() => { if (pend.has(i)) { pend.delete(i); rej(new Error('CDP 超时: ' + method)); } }, 60000);
  });
  return { send, events };
}

async function launch(url, port, profile) {
  const args = [
    '--headless=new', '--disable-crash-reporter', '--disable-gpu', '--no-first-run',
    '--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader',
    '--no-default-browser-check', '--disable-extensions', '--hide-scrollbars',
    '--user-data-dir=' + profile, '--remote-debugging-port=' + port,
    '--window-size=' + W + ',' + H, '--force-device-scale-factor=1',
    '--allow-file-access-from-files', url
  ];
  const proc = spawn(CHROME, args, { stdio: 'ignore', windowsHide: true });
  for (let i = 0; i < 100; i++) {
    await sleep(200);
    try {
      const r = await fetch('http://127.0.0.1:' + port + '/json/list');
      const list = await r.json();
      const page = list.find((x) => x.type === 'page' && x.webSocketDebuggerUrl);
      if (page) return { proc, page };
    } catch { /* 端口还没起来 */ }
  }
  throw new Error('Chrome 调试端口未就绪（' + port + '）');
}

const report = [];
let port = 9422;

for (const job of jobs) {
  const profile = path.join(SHOTS, '.profile-' + job.scene);
  const url = 'file:///' + path.join(ROOT, job.scene + '.html').replace(/\\/g, '/') + '?t=' + job.times[0] + '&nohud=1';
  let proc;
  try {
    const l = await launch(url, port, profile);
    proc = l.proc;
    const ws = new WebSocket(l.page.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('WS 连接失败')); });
    const { send, events } = cdp(ws);
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Emulation.setDeviceMetricsOverride', {
      width: W, height: H, deviceScaleFactor: 1, mobile: false
    });

    const ev = async (expr) => {
      const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.result && r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.text);
      return r.result.result.value;
    };

    // 等待场景就绪
    let ready = false, diag0 = null, err0 = null;
    for (let i = 0; i < 60; i++) {
      const raw = await ev('JSON.stringify({ready:!!window.__ready,diag:window.__diag||null,error:window.__error||null,title:document.title})');
      const st = JSON.parse(raw || '{}');
      diag0 = st.diag; err0 = st.error;
      if (st.ready) { ready = true; break; }
      await sleep(250);
    }
    if (!ready) throw new Error('页面未就绪（__ready 未置位）; error=' + err0);
    // 截图前确保没有遮罩挡住画面
    await ev("(function(){var b=document.getElementById('boot');if(b){b.style.transition='none';b.style.display='none';}" +
      "document.querySelectorAll('.hud').forEach(function(n){n.classList.add('hide');});return 1;})()");
    await sleep(300);

    // 逐时间点：同步渲染一帧 → 截图
    for (const t of job.times) {
      const info = await ev(`(function(){
        var e = window.__engine;
        e.renderAt(${t});
        var s = e.state;
        return JSON.stringify({t:${t}, sunVis:+s.sunVis.toFixed(3), occ:+s.occ.toFixed(3),
          off1:+s.cloudOff1.toFixed(2), off2:+s.cloudOff2.toFixed(2), offS:+s.cloudOffS.toFixed(2),
          errors:e.errors.length, size:e.CW+'x'+e.CH});
      })()`);
      const shot = await send('Page.captureScreenshot', { format: 'png' });
      const buf = Buffer.from(shot.result.data, 'base64');
      const name = job.scene + (t === 9 ? '' : '_t' + t);
      await writeFile(path.join(SHOTS, name + '.png'), buf);
      report.push({ name, scene: job.scene, t, bytes: buf.length, info: JSON.parse(info) });
      console.log('✔ ' + (name + '.png').padEnd(16) + (buf.length / 1024).toFixed(0).padStart(5) + ' KB   ' + info);
    }

    // 性能：连续 30 帧的平均耗时（软件渲染，保守上界）
    const perf = await ev(`(function(){
      var e = window.__engine, t0 = performance.now(), N = 30;
      for (var i = 0; i < N; i++) e.render(${job.times[0]} + i * 0.05, 0.016);
      var ms = (performance.now() - t0) / N;
      return JSON.stringify({msPerFrame:+ms.toFixed(2), fps:+ (1000/ms).toFixed(1), errors:e.errors.length, dpr:e.dpr, size:e.CW+'x'+e.CH});
    })()`);
    report.push({ scene: job.scene, perf: JSON.parse(perf), error: err0 });
    console.log('⚡ ' + job.scene.padEnd(6) + ' ' + perf);

    const exc = events.filter((e) => e.method === 'Runtime.exceptionThrown')
      .map((e) => (e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text || '').slice(0, 300));
    if (exc.length) console.log('  异常: ' + JSON.stringify(exc.slice(0, 2)));
    ws.close();
  } catch (e) {
    report.push({ scene: job.scene, fatal: String(e && e.message) });
    console.log('✘ ' + job.scene + ' — ' + (e && e.message));
  } finally {
    if (proc) proc.kill();
    await sleep(300);
    await rm(profile, { recursive: true, force: true }).catch(() => {});
  }
  port++;
}

await writeFile(path.join(SHOTS, 'diag.json'), JSON.stringify(report, null, 2), 'utf8');
console.log('诊断写入 shots/diag.json');
