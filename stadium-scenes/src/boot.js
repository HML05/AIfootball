/* ============================================================================
 * boot.js — 场景页面启动脚本（四个页面共用）
 *   URL 参数：?t=12 定格时间（截图/自检）· nohud=1 只留画面
 *             speed=0.5 云速 · rain=0.6 雨量 · glass=0 关玻璃雨滴
 *   键盘：空格 暂停 · 1~4 切换场景 · H 隐藏界面
 * ==========================================================================*/
(function () {
  'use strict';
  const U = window.SU, SC = window.SCENE_PROFILES, Engine = window.SEngine;
  const ID = window.__SCENE_ID__;
  const SCENES = window.__SCENES__ || [];
  const qs = new URLSearchParams(location.search);
  const num = function (k, d) { const v = parseFloat(qs.get(k)); return isFinite(v) ? v : d; };

  const stageC = document.getElementById('stage');
  const fxC = document.getElementById('fx');
  const raysC = document.getElementById('rays');   // WebGL 体积光层（不支持时引擎自动退回 2D 光柱）
  const diag = document.getElementById('diag');
  const errBox = document.getElementById('err');
  let engine = null, diagTimer = 0;

  function fail(msg) {
    errBox.style.display = 'block';
    errBox.textContent = String(msg).slice(0, 600);
    document.title = '⚠ ' + ID + ' :: ' + String(msg).slice(0, 120);
    window.__error = String(msg);
  }
  window.__onEngineError = function (e) { fail((e && (e.stack || e.message)) || e); };
  window.addEventListener('error', function (e) { fail(e.message); });

  /* ---------------- HUD ---------------- */
  document.documentElement.style.setProperty('--accent', SC[ID].accent);
  document.title = ID + ' · ' + SC[ID].name + ' · 球场四景';
  document.querySelectorAll('#tabs a').forEach(function (a) {
    a.classList.toggle('on', a.dataset.scene === ID);
  });
  // 切换场景时保留"定格时间 / 隐藏界面"这类参数
  (function () {
    const keep = [];
    if (qs.has('t')) keep.push('t=' + qs.get('t'));
    if (qs.get('nohud') === '1') keep.push('nohud=1');
    if (!keep.length) return;
    document.querySelectorAll('#tabs a').forEach(function (a) {
      a.setAttribute('href', a.getAttribute('href').split('?')[0] + '?' + keep.join('&'));
    });
  })();
  if (qs.get('nohud') === '1') {
    document.querySelectorAll('.hud').forEach(function (n) { n.classList.add('hide'); });
    const b0 = document.getElementById('boot');
    if (b0) b0.style.display = 'none';
  }

  function bindRange(el) {
    if (!el) return null;
    const out = el.parentNode.querySelector('output');
    const show = function () { if (out) out.textContent = Number(el.value).toFixed(2).replace(/0$/, ''); };
    el.addEventListener('input', show); show();
    return el;
  }
  const ctlCloud = bindRange(document.querySelector('[data-ctl="cloud"]'));
  const ctlRain = bindRange(document.querySelector('[data-ctl="rain"]'));
  const ctlGlass = bindRange(document.querySelector('[data-ctl="glass"]'));
  const btnPause = document.getElementById('btnPause');
  const btnHud = document.getElementById('btnHud');

  if (btnHud) btnHud.addEventListener('click', function () {
    document.querySelectorAll('.hud').forEach(function (n) { n.classList.toggle('hide'); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.code === 'Space') { e.preventDefault(); togglePause(); }
    else if (e.key === 'h' || e.key === 'H') { document.querySelectorAll('.hud').forEach(function (n) { n.classList.toggle('hide'); }); }
    else if (e.key >= '1' && e.key <= '4') {
      const s = SCENES[parseInt(e.key, 10) - 1];
      if (s) location.href = s.file;
    }
  });
  let paused = false;
  function togglePause() {
    if (!engine) return;
    paused = !paused;
    engine.setPaused(paused);
    if (btnPause) btnPause.textContent = paused ? '▶ 继续' : '❚❚ 暂停';
  }
  if (btnPause) btnPause.addEventListener('click', togglePause);

  /* ---------------- 启动 ---------------- */
  const fixed = qs.has('t') ? num('t', 12) : undefined;
  const tileSrc = window.__CLOUD_TILE__ || null;   // 实拍云层贴图（只有用实拍素材的场景才有）
  Promise.all([
    U.loadImage(window.__STADIUM_SRC__),
    tileSrc ? U.loadImage(tileSrc) : Promise.resolve(null)
  ]).then(function (imgs) {
    const img = imgs[0], tile = imgs[1];
    engine = new Engine({
      mode: ID, image: img, cloudTile: tile, canvas: stageC, fxCanvas: fxC,
      raysCanvas: raysC, raysOff: qs.has('rays') && parseFloat(qs.get('rays')) === 0,
      fixedTime: fixed
    });
    window.__engine = engine;
    if (qs.has('speed')) engine.setCloudSpeed(num('speed', 1));
    if (qs.has('rain')) engine.setRainAmount(num('rain', 1));
    if (qs.has('glass')) engine.setGlassAmount(num('glass', 1));
    // ?fx=0 关掉暗角与胶片颗粒（想省一点算力时用）
    if (qs.has('fx') && parseFloat(qs.get('fx')) === 0) engine.fxOff = true;
    if (ctlCloud) { ctlCloud.value = engine.cloudSpeed; ctlCloud.dispatchEvent(new Event('input')); }
    if (ctlRain) { ctlRain.value = engine.rainAmount; ctlRain.dispatchEvent(new Event('input')); }
    if (ctlGlass) { ctlGlass.value = engine.glassAmount; ctlGlass.dispatchEvent(new Event('input')); }
    if (ctlCloud) ctlCloud.addEventListener('input', function () { engine.setCloudSpeed(parseFloat(ctlCloud.value)); });
    if (ctlRain) ctlRain.addEventListener('input', function () { engine.setRainAmount(parseFloat(ctlRain.value)); });
    if (ctlGlass) ctlGlass.addEventListener('input', function () { engine.setGlassAmount(parseFloat(ctlGlass.value)); });

    engine.renderAt(fixed === undefined ? 0 : fixed);   // 立刻出第一帧（截图不等 rAF）
    engine.start();
    const boot = document.getElementById('boot');
    if (boot) { boot.classList.add('gone'); setTimeout(function () { boot.style.display = 'none'; }, 600); }
    window.__ready = true;
    diagTimer = setInterval(updateDiag, 400);
    updateDiag();
  }).catch(function (e) { fail('背景图加载失败：' + (e && e.message)); });

  /* ---------------- 状态 ---------------- */
  function updateDiag() {
    if (!engine || !diag) return;
    const st = engine.stats, s = engine.state;
    const info = {
      scene: ID, fps: +st.fps.toFixed(1), ms: +st.ms.toFixed(2), frames: st.frames,
      err: engine.errors.length, sunVis: +s.sunVis.toFixed(3), occ: +s.occ.toFixed(3),
      cloudSpeed: engine.cloudSpeed, rain: engine.rainAmount, glass: engine.glassAmount,
      dpr: +engine.dpr.toFixed(2), size: engine.CW + 'x' + engine.CH
    };
    diag.setAttribute('data-diag', JSON.stringify(info));
    window.__diag = info;
    diag.innerHTML = '<b>' + info.fps.toFixed(0) + '</b> fps · <b>' + info.ms.toFixed(1) + '</b> ms'
      + (engine.S.rain ? ' · 雨滴 <b>' + engine.rainCount() + '</b>' : '')
      + ' · 云影 <b>' + Math.round((1 - info.sunVis) * 100) + '%</b>'
      + (info.err ? ' · <b style="color:#ff9b9b">错误 ' + info.err + '</b>' : '');
  }
})();
