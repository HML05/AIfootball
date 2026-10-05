/* ============================================================================
 * engine.js — 场景引擎（与场景无关的部分）
 *   · 单张实拍球场照片 → 分层合成：分级底板 / 天空换色 / 可平铺云场 /
 *     云的投影（落在草皮上，与云同步移动）/ 太阳光晕与光柱 / 曝光联动 /
 *     暗角与颗粒；黑夜与雨天的专有图层由 weather.js 提供。
 *   · 全部按"时间参数化"渲染：任意时刻 t 一帧即可还原，便于定格与截图。
 * ==========================================================================*/
(function (global) {
  'use strict';
  const U = global.SU;

  /* ---------- 照片锚点（归一化坐标，取自原片与既有 ui-design 约定） ---------- */
  const A = {
    skyTop: 0.000,
    skyBot: 0.440,
    skyPaintBot: 0.300,
    cityTop: 0.150,
    cityBot: 0.400,
    lampBands: [
      { x0: 0.050, x1: 0.330, y0: 0.342, y1: 0.442 },
      { x0: 0.525, x1: 0.950, y0: 0.350, y1: 0.448 }
    ],
    lampGlows: [0.115, 0.235, 0.320, 0.585, 0.700, 0.845, 0.930],
    beamFrom: [0.130, 0.300, 0.620, 0.880],
    pitchTop: 0.605,
    pitchBot: 1.000,
    sun: { x: 0.035, y: 0.185 }
  };

  function setB(ctx, mode, alpha) {
    ctx.globalCompositeOperation = mode || 'source-over';
    ctx.globalAlpha = alpha === undefined ? 1 : alpha;
  }
  function resetCtx(ctx) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    ctx.globalAlpha = 1;
  }
  /** 梯形透视预畸变（近处更宽），一次性生成 */
  function trapezoid(src, bottomScale, fadeStops) {
    const w = src.width, h = src.height;
    const out = U.makeCanvas(Math.round(w * bottomScale), h);
    const c = out.getContext('2d');
    const N = 32;
    for (let i = 0; i < N; i++) {
      const t0 = i / N, t1 = (i + 1) / N;
      const y0 = h * t0, y1 = h * t1;
      const s0 = 1 + (bottomScale - 1) * t0, s1 = 1 + (bottomScale - 1) * t1;
      c.drawImage(src, 0, y0, w, y1 - y0, (out.width - w * s0) / 2, y0, w * s0, (y1 - y0) + 1);
    }
    if (fadeStops) {
      c.globalCompositeOperation = 'destination-in';
      const g = c.createLinearGradient(0, 0, 0, h);
      fadeStops.forEach(function (s) { g.addColorStop(s[0], 'rgba(0,0,0,' + s[1] + ')'); });
      c.fillStyle = g;
      c.fillRect(0, 0, out.width, h);
      c.globalCompositeOperation = 'source-over';
    }
    return out;
  }

  /* ==========================================================================
   * Engine
   * ========================================================================*/
  function Engine(cfg) {
    this.cfg = cfg || {};
    this.mode = this.cfg.mode || 'day';
    this.S = global.SCENE_PROFILES[this.mode];
    // 锚点：默认走公共锚点，场景可以用 S.anchors 覆盖（换素材后地面/天空位置会变）
    this.A = Object.assign({}, A, this.S.anchors || {});
    this.img = this.cfg.image;
    this.cloudTile = this.cfg.cloudTile || null;      // 从实拍图里抠出来的云层贴图（可平铺）
    this.canvas = this.cfg.canvas;
    this.fxCanvas = this.cfg.fxCanvas;
    this.ctx = this.canvas.getContext('2d');
    this.fxCtx = this.fxCanvas ? this.fxCanvas.getContext('2d') : null;
    // 体积光层（WebGL，移植自用户给的 LightRays 组件）；不支持 WebGL 时退回 canvas2d 的 _drawRays
    this.raysGL = (global.SRays && this.cfg.raysCanvas && !this.cfg.raysOff && this.S.raysGL)
      ? global.SRays.create(this.cfg.raysCanvas, this.S.raysGL) : null;

    this.W = 800; this.H = 600; this.dpr = 1;
    this.CW = 0; this.CH = 0;
    this.imgRect = { x: 0, y: 0, w: 800, h: 600 };

    this.t = 0;
    this.paused = false;
    this.cloudSpeed = 1;
    this.rainAmount = 1;
    this.glassAmount = 1;
    this.speedScale = 1;
    this.stats = { fps: 0, ms: 0, frames: 0 };
    this.errors = [];
    this.time = 0;

    this.mouse = { x: 0.5, y: 0.5, sx: 0.5, sy: 0.5, active: false };
    this.state = { sunVis: 1, occ: 0, cloudOff1: 0, cloudOff2: 0, cloudOffS: 0 };

    this._buildTextures();
    this.resize();
    this._bind();
  }

  Engine.prototype.px = function (nx) { return this.imgRect.x + nx * this.imgRect.w; };
  Engine.prototype.py = function (ny) { return this.imgRect.y + ny * this.imgRect.h; };

  /* ---------------- 纹理（只生成一次，与画布尺寸无关） ---------------- */
  Engine.prototype._buildTextures = function () {
    const S = this.S;
    const CW = 1024, CHh = 256;

    // 实拍云层模式、或云全关（alpha 都是 0）时都不需要程序化云精灵，省掉这部分构建开销
    const cloudsOn = (S.cloud.alpha1 > 0) || (S.cloud.alpha2 > 0);
    if (cloudsOn && !(S.cloud.photo && this.cloudTile)) {
      this.grid1 = U.cloudGrid(CW, CHh, S.cloud.layer1);
      this.cloud1 = U.cloudSprite(CW, CHh, this.grid1, S.cloud.sprite1);
      this.grid2 = U.cloudGrid(CW, CHh, S.cloud.layer2);
      this.cloud2 = U.cloudSprite(CW, CHh, this.grid2, S.cloud.sprite2);
    }

    // 云的投影：低频大块 + 透视梯形 + 竖向渐变 → 一次性上色
    // 实拍云层模式下，网格直接从云层贴图的 alpha 降采样得到 → 云影形状和天上的云一致
    const photo = S.cloud.photo;
    const GW = 512, GH = photo ? 80 : 256;
    if (photo && this.cloudTile) {
      this.shadowGrid = U.gridFromAlpha(this.cloudTile, GW, GH, { gamma: photo.gamma });
    } else {
      this.shadowGrid = U.cloudGrid(GW, GH, S.cloud.shadow);
    }
    this.shadowW = GW; this.shadowH = GH;
    const mask = U.gridToMask(GW, GH, this.shadowGrid,
      photo ? { lo: photo.shadowLo === undefined ? 0.10 : photo.shadowLo, hi: 0.62, gamma: 1.1 } : S.cloud.shadowMask);
    const cs = S.cloud.shadowScene;
    const warped = trapezoid(mask, 1.30, [
      [0.00, 0], [0.16, S.cloud.shadowNear], [0.72, 1], [1.00, 0.5]
    ]);
    const wc = warped.getContext('2d');
    wc.globalCompositeOperation = 'source-in';
    wc.fillStyle = U.rgb(cs.color, 1);
    wc.fillRect(0, 0, warped.width, warped.height);
    wc.globalCompositeOperation = 'source-over';
    // 柔化：原版梯形遮罩边缘偏硬、上草皮后会显斑驳，这里整体模糊一遍
    this.shadowSprite = U.blurredCopy(warped, 0.34, 2);

    this.glowWarm = U.glowSprite(512, 512, S.sun.glowColor, 1.0);
    this.glowWide = U.glowSprite(512, 256, S.sun.wideColor || S.sun.glowColor, 1.35);
    this.grain = U.grainSprite(256, 1);
    this.shafts = this._buildShafts();
    this.vignette = null;
  };

  /* 草皮上被云影切开的斜向光带 */
  Engine.prototype._buildShafts = function () {
    const w = 768, h = 512;
    const cv = U.makeCanvas(w, h);
    const c = cv.getContext('2d');
    const col = this.S.shaft.color;
    for (let i = 0; i < 5; i++) {
      const x = w * (0.08 + i * 0.21) + (i % 2 ? 30 : -18);
      const bw = w * (0.075 + (i % 3) * 0.028);
      const g = c.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, U.rgb(col, 0));
      g.addColorStop(0.35, U.rgb(col, this.S.shaft.alpha * (0.7 + (i % 3) * 0.15)));
      g.addColorStop(1, U.rgb(col, 0));
      c.save();
      c.translate(x, 0);
      c.rotate(this.S.shaft.angle);
      c.fillStyle = g;
      c.filter = 'blur(10px)';
      c.fillRect(-bw / 2, 0, bw, h);
      c.restore();
    }
    c.filter = 'none';
    c.globalCompositeOperation = 'destination-in';
    const g2 = c.createLinearGradient(0, 0, 0, h);
    g2.addColorStop(0, 'rgba(255,255,255,0)');
    g2.addColorStop(0.22, 'rgba(255,255,255,1)');
    g2.addColorStop(0.72, 'rgba(255,255,255,0.9)');
    g2.addColorStop(1, 'rgba(255,255,255,0)');
    c.fillStyle = g2; c.fillRect(0, 0, w, h);
    c.globalCompositeOperation = 'source-over';
    return cv;
  };

  /* ---------------- 尺寸 / 底板 ---------------- */
  Engine.prototype.resize = function () {
    const w = Math.max(320, global.innerWidth || 1280);
    const h = Math.max(240, global.innerHeight || 720);
    let dpr = Math.min(global.devicePixelRatio || 1, 1.5);
    const maxPix = 2.9e6;
    if (w * h * dpr * dpr > maxPix) dpr = Math.sqrt(maxPix / (w * h));
    dpr = Math.max(0.6, Math.min(dpr, 1.5));

    this.W = w; this.H = h; this.dpr = dpr;
    const CW = Math.round(w * dpr), CH = Math.round(h * dpr);
    if (CW === this.CW && CH === this.CH && this.base) return;
    this.CW = CW; this.CH = CH;

    [this.canvas, this.fxCanvas].forEach(function (cv) {
      if (!cv) return;
      cv.width = CW; cv.height = CH;
      cv.style.width = w + 'px';
      cv.style.height = h + 'px';
    });
    if (this.raysGL) {
      const rcv = this.cfg.raysCanvas;
      rcv.style.width = w + 'px'; rcv.style.height = h + 'px';
      this.raysGL.resize(w, h, dpr);
    }

    // cover 贴合：偏向上缘，裁掉的是画面下缘（保住天空与城市）
    const ar = this.img.width / this.img.height;
    const car = CW / CH;
    let iw, ih, ix, iy;
    if (car > ar) { iw = CW; ih = CW / ar; ix = 0; iy = Math.min(0, (CH - ih) * 0.30); }
    else { ih = CH; iw = CH * ar; ix = (CW - iw) / 2; iy = 0; }
    this.imgRect = { x: ix, y: iy, w: iw, h: ih };

    this.stage = U.makeCanvas(CW, CH);
    this.stageCtx = this.stage.getContext('2d');
    this._buildBase();
    this._buildVignette();
    if (global.SNight && this.S.night) global.SNight.build(this);
    if (global.SRain && this.S.rain) global.SRain.build(this);
  };

  Engine.prototype._buildBase = function () {
    const S = this.S, CW = this.CW, CH = this.CH, R = this.imgRect;
    const cv = U.makeCanvas(CW, CH);
    const c = cv.getContext('2d');
    c.fillStyle = S.base.backdrop || '#0a0f18';
    c.fillRect(0, 0, CW, CH);
    if ('filter' in c && S.base.filter) c.filter = S.base.filter;
    c.drawImage(this.img, R.x, R.y, R.w, R.h);
    c.filter = 'none';

    (S.base.overlays || []).forEach(function (ov) {
      setB(c, ov.blend, ov.alpha);
      if (ov.grad) {
        const g = c.createLinearGradient(0, CH * (ov.grad.y0 || 0), 0, CH * (ov.grad.y1 === undefined ? 1 : ov.grad.y1));
        ov.grad.stops.forEach(function (st) { g.addColorStop(st[0], U.rgb(st[1], st[2])); });
        c.fillStyle = g;
      } else { c.fillStyle = U.rgb(ov.color, 1); }
      if (ov.rect) c.fillRect(CW * ov.rect[0], CH * ov.rect[1], CW * ov.rect[2], CH * ov.rect[3]);
      else c.fillRect(0, 0, CW, CH);
    });
    resetCtx(c);

    // 白天/黄昏/雨天：球场灯是关着的 —— 把灯带压暗
    if (S.lampsOff) {
      setB(c, 'multiply', S.lampsOff.alpha);
      this.A.lampBands.forEach(function (b) {
        const x = R.x + b.x0 * R.w, y = R.y + b.y0 * R.h;
        const w = (b.x1 - b.x0) * R.w, h = (b.y1 - b.y0) * R.h;
        const g = c.createLinearGradient(0, y, 0, y + h);
        g.addColorStop(0, U.rgb(S.lampsOff.color, 0.10));
        g.addColorStop(0.5, U.rgb(S.lampsOff.color, 1));
        g.addColorStop(1, U.rgb(S.lampsOff.color, 0.10));
        c.fillStyle = g;
        c.fillRect(x, y, w, h);
      });
      resetCtx(c);
    }
    this.base = cv;
  };

  Engine.prototype._buildVignette = function () {
    const CW = this.CW, CH = this.CH;
    const cv = U.makeCanvas(CW, CH);
    const c = cv.getContext('2d');
    const g = c.createRadialGradient(CW * 0.5, CH * 0.46, Math.min(CW, CH) * 0.30,
      CW * 0.5, CH * 0.5, Math.max(CW, CH) * 0.78);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(0.62, 'rgba(0,0,0,0.10)');
    g.addColorStop(1, 'rgba(0,0,0,0.62)');
    c.fillStyle = g; c.fillRect(0, 0, CW, CH);
    this.vignette = cv;
  };

  /* ---------------- 输入 ---------------- */
  Engine.prototype._bind = function () {
    const self = this;
    this._onResize = function () { self.resize(); };
    global.addEventListener('resize', this._onResize);
    this._onMove = function (e) {
      const p = e.touches ? e.touches[0] : e;
      self.mouse.x = U.clamp(p.clientX / self.W, 0, 1);
      self.mouse.y = U.clamp(p.clientY / self.H, 0, 1);
      self.mouse.active = true;
    };
    global.addEventListener('mousemove', this._onMove, { passive: true });
    global.addEventListener('touchmove', this._onMove, { passive: true });
  };

  /* ---------------- 云遮日：采样云影密度 ---------------- */
  Engine.prototype._sampleOcclusion = function (off) {
    const GW = this.shadowW, GH = this.shadowH, g = this.shadowGrid;
    // 云全关（alpha1/alpha2 都是 0，例如"云静止不动"的白天场景）：永远不遮挡 → sunVis 恒为 1
    if (!(this.S.cloud.alpha1 > 0) && !(this.S.cloud.alpha2 > 0)) return 0;
    // 实拍云层：直接按"太阳所在的那一列"取（太阳在画面外右上，光就是从那来的）
    const sunCol = this.S.cloud.photo ? this.S.sun.x : (this.S.sun.x * 0.35 + 0.06);
    const sx = ((sunCol * GW - off) % GW + GW) % GW;
    let sum = 0, cnt = 0, mx = 0;
    const rows = this.S.cloud.photo ? [0.06, 0.26, 0.50, 0.78] : [0.12, 0.23, 0.34, 0.45, 0.56];
    const span = this.S.cloud.photo ? 8 : 1;
    const step = this.S.cloud.photo ? 0.025 : 0.05;
    for (let r = 0; r < rows.length; r++) {
      const yy = Math.min(GH - 1, Math.round(GH * rows[r]));
      for (let d = -span; d <= span; d++) {
        const xx = ((Math.round(sx + d * GW * step) % GW) + GW) % GW;
        sum += g[yy * GW + xx];
        if (g[yy * GW + xx] > mx) mx = g[yy * GW + xx];
        cnt++;
      }
    }
    const om = this.S.cloud.occMap || [0.34, 0.76];
    // 实拍云层：稀疏的云要靠"窗口内最大值"来判断太阳有没有被挡住，只取均值会长期贴着 0
    const v = this.S.cloud.photo ? (mx * 0.65 + (sum / cnt) * 0.35) : (sum / cnt);
    return U.clamp((v - om[0]) / (om[1] - om[0]), 0, 1);
  };

  Engine.prototype.rainCount = function () {
    if (!this.S.rain) return 0;
    return Math.round(this.S.rain.count * U.clamp(this.rainAmount, 0, 1.4));
  };

  /* ---------------- 单帧 ---------------- */
  Engine.prototype.render = function (t, dt) {
    const S = this.S, ctx = this.stageCtx;
    this.t = t;

    this.mouse.sx = U.approach(this.mouse.sx, this.mouse.x, dt, 0.35);
    this.mouse.sy = U.approach(this.mouse.sy, this.mouse.y, dt, 0.35);
    const mx = (this.mouse.sx - 0.5), my = (this.mouse.sy - 0.5);

    const spd = this.cloudSpeed;
    const off1 = ((t * S.cloud.speed1 * spd) % 1) * 1024;
    const off2 = ((t * S.cloud.speed2 * spd) % 1) * 1024;
    const offS = ((t * S.cloud.speedShadow * spd) % 1) * this.shadowW;
    this.state.cloudOff1 = off1; this.state.cloudOff2 = off2; this.state.cloudOffS = offS;

    const occ = this._sampleOcclusion(offS);
    this.state.occ = occ;
    this.state.sunVis = U.approach(this.state.sunVis, 1 - occ, dt, 0.55);
    const sunVis = this.state.sunVis;

    resetCtx(ctx);
    ctx.save();
    const MB = S.mouse || {};
    const camS = MB.camS === undefined ? 1.024 : MB.camS;
    const camX = -mx * (MB.cam === undefined ? 17 : MB.cam) * this.dpr;
    const camY = -my * (MB.camY === undefined ? 10 : MB.camY) * this.dpr;
    ctx.translate(this.CW / 2, this.CH / 2);
    ctx.scale(camS, camS);
    ctx.translate(-this.CW / 2 + camX, -this.CH / 2 + camY);

    ctx.drawImage(this.base, 0, 0);

    this._drawSkyPaint(ctx, mx, my);
    if (global.SNight && S.night) global.SNight.drawSky(this, ctx, t, sunVis);
    this._drawSun(ctx, mx, my, sunVis, true);          // 光源本体（会被云遮住）
    this._drawClouds(ctx, off1, off2, mx, my, sunVis); // 云在光源之上
    this._drawSun(ctx, mx, my, sunVis, false);         // 云后的透光 + 被遮时的压暗
    this._drawGroundShadow(ctx, offS, sunVis);
    if (S.shaft) this._drawShafts(ctx, t, mx, sunVis);
    if (!this.raysGL) this._drawRays(ctx, mx, my, sunVis);   // 天空里成扇的日光（WebGL 不可用时的 2D 兜底）
    this._drawSunPatch(ctx, mx, my, sunVis);  // 落在草皮上的阳光斑（随鼠标平移）

    if (global.SNight && S.night) global.SNight.drawWorld(this, ctx, t, sunVis);
    if (global.SRain && S.rain) global.SRain.drawWorld(this, ctx, t, sunVis);

    this._drawExposure(ctx, sunVis, my);
    this._drawFix(ctx, t);

    ctx.restore();

    // ---- 前景（雨丝 / 玻璃雨滴）：只有雨天用它，其余场景连清屏都省掉 ----
    const fx = this.fxCtx;
    const hasFx = !!(global.SRain && S.rain);
    if (fx && hasFx) {
      resetCtx(fx);
      fx.clearRect(0, 0, this.CW, this.CH);
      fx.save();
      fx.translate(this.CW / 2, this.CH / 2);
      fx.scale(camS, camS);
      fx.translate(-this.CW / 2 + camX, -this.CH / 2 + camY);
      global.SRain.drawFx(this, fx, t, sunVis);
      fx.restore();
      resetCtx(fx);
    }

    // 体积光层：WebGL 渲染到独立画布，由 CSS mix-blend-mode: screen 叠加显示
    if (this.raysGL) {
      try { this.raysGL.render(t, this.mouse.sx, this.mouse.sy); }
      catch (e) { this.raysGL = null; }
    }

    const c2 = this.ctx;    resetCtx(c2);
    c2.drawImage(this.stage, 0, 0);
  };

  /* ---------------- 天空换色 ---------------- */
  Engine.prototype._drawSkyPaint = function (ctx, mx, my) {
    const S = this.S, R = this.imgRect, A = this.A;
    if (!S.skyPaint) return;
    const y0 = this.py(0), y1 = this.py(A.skyPaintBot);
    const g = ctx.createLinearGradient(0, y0, 0, y1);
    S.skyPaint.stops.forEach(function (s) { g.addColorStop(s[0], U.rgb(s[1], s[2])); });
    setB(ctx, S.skyPaint.blend, S.skyPaint.alpha);
    ctx.save();
    ctx.translate(-mx * 6 * this.dpr, -my * 3 * this.dpr);
    ctx.fillStyle = g;
    ctx.fillRect(R.x - 60, y0 - 60, R.w + 120, (y1 - y0) + 120);
    ctx.restore();
    resetCtx(ctx);
  };

  /* ---------------- 云（两层，各自平铺横移） ---------------- */
  Engine.prototype._drawClouds = function (ctx, off1, off2, mx, my, sunVis) {
    const S = this.S, R = this.imgRect, A = this.A;
    // 云全关（alpha 都是 0）：不画云，也不做云后透光——画面里的云只来自底板本身
    if (!(S.cloud.alpha1 > 0) && !(S.cloud.alpha2 > 0)) return;
    const photo = S.cloud.photo;
    if (photo && this.cloudTile) {
      this._drawPhotoClouds(ctx, off1, off2, mx, my, sunVis);
      return;
    }
    const y0 = this.py(A.skyTop), hgt = (A.skyBot - A.skyTop) * R.h;
    const w = R.w;
    const layers = [
      { spr: this.cloud2, off: off2, alpha: S.cloud.alpha2 * (0.62 + 0.38 * sunVis), par: 0.45, sc: 1.06, y: 0.02 },
      { spr: this.cloud1, off: off1, alpha: S.cloud.alpha1 * (0.55 + 0.45 * sunVis), par: 1.0, sc: 1.0, y: 0.0 }
    ];
    for (let li = 0; li < layers.length; li++) {
      const L = layers[li];
      const px = -((L.off % 1024) / 1024) * w + R.x - mx * 14 * L.par * this.dpr;
      const py = y0 + L.y * hgt - my * 5 * L.par * this.dpr;
      const ph = hgt * L.sc;
      // 精灵下部（纵向淡出之后）本来就是空的，只画有内容的上段：省掉约四成填充面积
      const crop = 0.62;
      setB(ctx, 'source-over', L.alpha);
      ctx.drawImage(L.spr, 0, 0, L.spr.width, L.spr.height * crop, px, py, w, ph * crop);
      ctx.drawImage(L.spr, 0, 0, L.spr.width, L.spr.height * crop, px + w, py, w, ph * crop);
      if (px > R.x) ctx.drawImage(L.spr, 0, 0, L.spr.width, L.spr.height * crop, px - w, py, w, ph * crop);
    }
    resetCtx(ctx);
  };

  /**
   * 实拍云层：把从照片里抠出来的云贴图横向平铺、按不同速度漂移。
   * 第二层用镜像 + 放大，避免和第一层"同一朵云出现两次"的重复感。
   */
  Engine.prototype._drawPhotoClouds = function (ctx, off1, off2, mx, my, sunVis) {
    const S = this.S, R = this.imgRect, tp = S.cloud.photo;
    const band = tp.band || 0.235;
    const layers = [
      { off: off2, sc: tp.scale2 || 1.45, alpha: tp.alpha2, dy: tp.dy2 || 0.004, par: 0.45, mirror: true },
      { off: off1, sc: tp.scale1 || 1.00, alpha: tp.alpha1, dy: 0, par: 1.0, mirror: false }
    ];
    const x0 = R.x - 40, x1 = R.x + R.w + 40;
    for (let li = 0; li < layers.length; li++) {
      const L = layers[li];
      const bw = R.w * L.sc;
      const bh = R.h * band * L.sc;
      const py = R.y + L.dy * R.h - my * 5 * L.par * this.dpr;
      const phase = ((L.off % 1024) / 1024) * bw;
      let px = x0 - phase - mx * 14 * L.par * this.dpr;
      px = x0 - ((phase + mx * 14 * L.par * this.dpr) % bw);
      setB(ctx, 'source-over', L.alpha);
      const i0 = Math.floor((x0 - px) / bw), i1 = Math.ceil((x1 - px) / bw);
      for (let i = i0; i <= i1; i++) {
        const x = px + i * bw;
        // 镜像平铺：相邻两块互为镜像 → 边界天然连续，没有硬接缝
        const flip = (L.mirror ? 1 : 0) !== (((i % 2) + 2) % 2);
        if (flip) {
          ctx.save();
          ctx.translate(x + bw, py);
          ctx.scale(-1, 1);
          ctx.drawImage(this.cloudTile, 0, 0, bw, bh);
          ctx.restore();
        } else {
          ctx.drawImage(this.cloudTile, x, py, bw, bh);
        }
      }
    }
    resetCtx(ctx);
  };

  /* ---------------- 云的投影扫过草皮 ---------------- */
  Engine.prototype._drawGroundShadow = function (ctx, offS, sunVis) {
    const S = this.S, R = this.imgRect, A = this.A;
    const cs = S.cloud.shadowScene;
    if (!cs || !this.shadowSprite || !(cs.alpha > 0)) return;
    const y0 = this.py(A.pitchTop - 0.03);
    const hgt = this.py(1.0) - y0 + 12;
    const sw = this.shadowSprite.width / this.shadowW;   // 梯形加宽系数
    const w = R.w * sw;
    const px = -((offS % this.shadowW) / this.shadowW) * R.w + R.x - (w - R.w) / 2;
    setB(ctx, 'multiply', cs.alpha * (0.5 + 0.5 * sunVis));
    ctx.drawImage(this.shadowSprite, px, y0, w, hgt);
    ctx.drawImage(this.shadowSprite, px + R.w, y0, w, hgt);
    if (px > R.x - R.w) ctx.drawImage(this.shadowSprite, px - R.w, y0, w, hgt);
    resetCtx(ctx);
  };

  /* ---------------- 太阳 / 光源 ---------------- */
  Engine.prototype._drawSun = function (ctx, mx, my, sunVis, pre) {
    const S = this.S, R = this.imgRect;
    const MB = S.mouse || {};
    const cx = this.px(S.sun.x) + mx * this.dpr * (MB.sun === undefined ? 58 : MB.sun) + (1 - sunVis) * 8;
    const cy = this.py(S.sun.y) + my * this.dpr * (MB.sunY === undefined ? 30 : MB.sunY);
    const tweak = 1 + my * (MB.glow === undefined ? 0.12 : MB.glow);   // 鼠标上下：光的强弱轻微起伏
    if (pre) {
      const sz = R.w * S.sun.size;
      setB(ctx, 'screen', S.sun.strength * (0.35 + 0.65 * sunVis) * tweak);
      ctx.drawImage(this.glowWide, cx - sz * 1.5, cy - sz * 0.75, sz * 3, sz * 1.5);
      setB(ctx, 'screen', S.sun.core * (0.4 + 0.6 * sunVis) * tweak);
      ctx.drawImage(this.glowWarm, cx - sz * 0.5, cy - sz * 0.5, sz, sz);
    } else {
      // 云缝里透出来的那一小团光
      const sz2 = R.w * S.sun.size * 0.34;
      setB(ctx, 'screen', S.sun.core * 0.5 * (0.25 + 0.75 * sunVis));
      ctx.drawImage(this.glowWarm, cx - sz2 * 0.5, cy - sz2 * 0.5, sz2, sz2);
      if (sunVis < 0.92) {
        setB(ctx, 'multiply', (0.92 - sunVis) * (S.sun.shadeStrength || 1.0));
        ctx.fillStyle = U.rgb(S.sun.shadeColor || [120, 138, 168], 1);
        ctx.fillRect(0, 0, this.CW, this.CH);
      }
    }
    resetCtx(ctx);
  };

  /* ---------------- 草皮上的斜向光带 ---------------- */
  Engine.prototype._drawShafts = function (ctx, t, mx, sunVis) {
    const S = this.S, R = this.imgRect, A = this.A;
    const y0 = this.py(A.pitchTop - 0.06);
    const hgt = this.py(1.0) - y0 + 20;
    const w = R.w * 1.12;
    const MB = S.mouse || {};
    const swayK = S.shaft.sway === undefined ? 1 : S.shaft.sway;
    const sway = Math.sin(t * 0.11) * 0.012 * swayK;
    setB(ctx, 'screen', S.shaft.sceneAlpha * (0.10 + 0.90 * sunVis));
    ctx.save();
    ctx.translate(R.x - (w - R.w) / 2 + mx * this.dpr * (MB.shaft === undefined ? 18 : MB.shaft) + sway * R.w, y0 + (1 - sunVis) * 6);
    ctx.drawImage(this.shafts, 0, 0, w, hgt);
    ctx.restore();
    resetCtx(ctx);
  };

  /* ---------------- 天空里成扇的日光（随鼠标轻转，只在天空带内） ---------------- */
  Engine.prototype._drawRays = function (ctx, mx, my, sunVis) {
    const S = this.S, cfg = S.rays;
    if (!cfg || !(cfg.alpha > 0)) return;
    const R = this.imgRect;
    const ox = this.px(cfg.x === undefined ? S.sun.x : cfg.x) + mx * this.dpr * (cfg.mx || 0);
    const oy = this.py(cfg.y === undefined ? S.sun.y : cfg.y) + my * this.dpr * (cfg.my || 0);
    const N = cfg.count || 7, w = cfg.wide || 0.045, sp = cfg.spread || 0.16;
    const len = this.CH * (cfg.len || 0.45);
    const rot = mx * (cfg.rot || 0);   // mx 已是以画面中心为 0 的偏移
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, this.CW, this.py(cfg.clip === undefined ? 0.44 : cfg.clip));
    ctx.clip();
    ctx.globalCompositeOperation = 'screen';
    ctx.globalAlpha = cfg.alpha * (0.35 + 0.65 * sunVis);
    for (let i = 0; i < N; i++) {
      const a = Math.PI / 2 + (i - (N - 1) / 2) * sp + rot;
      const g = ctx.createLinearGradient(ox, oy, ox + Math.cos(a) * len, oy + Math.sin(a) * len);
      g.addColorStop(0, U.rgb(cfg.color, 0.95));
      g.addColorStop(0.35, U.rgb(cfg.color, 0.42));
      g.addColorStop(1, U.rgb(cfg.color, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(ox + Math.cos(a - w) * len, oy + Math.sin(a - w) * len);
      ctx.lineTo(ox + Math.cos(a + w) * len, oy + Math.sin(a + w) * len);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
    resetCtx(ctx);
  };

  /* ---------------- 草坪上的光带与影子（鼠标移动光源 → 光与影实时联动） ----------------
     做法：在草皮矩形内画一对互补的平行渐变带 —— 用 screen 加亮"受光侧"、用 multiply 压暗"背光侧"，
     两条带共用同一条渐变轴与同一组分界 stop，所以明暗交界永远吻合，鼠标一动整条光影边界就跟着平移。 */
  Engine.prototype._drawSunPatch = function (ctx, mx, my, sunVis) {
    const S = this.S, cfg = S.sunPatch;
    if (!cfg || !(cfg.alpha > 0 || cfg.shadow > 0)) return;
    const R = this.imgRect, A = this.A;
    const y0 = this.py(A.pitchTop), y1 = this.py(A.pitchBot);
    if (!(y1 > y0)) return;

    const shift = mx * (cfg.mx || 0) * R.w;                  // 鼠标左右 → 光/影边界整体平移
    const rise = my * (cfg.my || 0) * R.h;                   // 鼠标上下 → 边界轻微上下浮动
    const th = cfg.angle === undefined ? 0.60 : cfg.angle;   // 明暗边界的方向（与光的方向一致：左上→右下）
    const ax = Math.sin(th), ay = -Math.cos(th);             // 垂直于边界：从受光侧指向背光侧
    const cx = this.px(cfg.x) + shift;
    const cy = (y0 + y1) * 0.5 + rise;
    const L = R.w * (cfg.len === undefined ? 0.80 : cfg.len);
    const gx0 = cx - ax * L, gy0 = cy - ay * L, gx1 = cx + ax * L, gy1 = cy + ay * L;
    const mid = cfg.mid === undefined ? 0.50 : cfg.mid;      // 分界在渐变轴上的位置
    const soft = cfg.soft === undefined ? 0.16 : cfg.soft;   // 过渡带宽度
    const lit = cfg.color || [255, 246, 222];

    ctx.save();
    ctx.beginPath();
    ctx.rect(R.x, y0, R.w, y1 - y0);
    ctx.clip();

    // ① 影子：背光侧 multiply 压暗（白 = 不动，暗色 = 压暗）
    if (cfg.shadow > 0) {
      const g = ctx.createLinearGradient(gx0, gy0, gx1, gy1);
      g.addColorStop(0, 'rgba(255,255,255,1)');
      g.addColorStop(Math.max(0, mid - soft), 'rgba(255,255,255,1)');
      g.addColorStop(Math.min(1, mid + soft), 'rgba(54,68,94,1)');
      g.addColorStop(1, 'rgba(44,58,84,1)');
      ctx.globalCompositeOperation = 'multiply';
      ctx.globalAlpha = cfg.shadow * (0.55 + 0.45 * sunVis);
      ctx.fillStyle = g;
      ctx.fillRect(R.x, y0, R.w, y1 - y0);
    }

    // ② 阳光：受光侧 screen 加亮（黑 = 不动，暖白 = 加光）
    if (cfg.alpha > 0) {
      const g2 = ctx.createLinearGradient(gx0, gy0, gx1, gy1);
      g2.addColorStop(0, 'rgba(' + lit[0] + ',' + lit[1] + ',' + lit[2] + ',1)');
      g2.addColorStop(Math.max(0, mid - soft), 'rgba(' + lit[0] + ',' + lit[1] + ',' + lit[2] + ',1)');
      g2.addColorStop(Math.min(1, mid + soft), 'rgba(0,0,0,1)');
      g2.addColorStop(1, 'rgba(0,0,0,1)');
      ctx.globalCompositeOperation = 'screen';
      ctx.globalAlpha = cfg.alpha * (0.45 + 0.55 * sunVis) * (1 + my * 0.18);
      ctx.fillStyle = g2;
      ctx.fillRect(R.x, y0, R.w, y1 - y0);
    }

    ctx.restore();
    resetCtx(ctx);
  };

  /* ---------------- 曝光（云遮日的整体明暗） ---------------- */
  Engine.prototype._drawExposure = function (ctx, sunVis, my) {
    const ex = this.S.exposure, MB = this.S.mouse || {};
    if (!(ex.darken > 0) && !(ex.lift > 0)) return;   // 不改变亮度：整段跳过
    const mt = (my || 0) * (MB.exposure === undefined ? 1 : MB.exposure);   // 鼠标上下：整体曝光轻微起伏
    const dark = (1 - sunVis) * ex.darken * (1 - mt * 0.55);
    if (dark > 0.002) {
      setB(ctx, 'multiply', dark);
      const g = ctx.createLinearGradient(0, 0, 0, this.CH);
      g.addColorStop(0, U.rgb(ex.darkTop, 1));
      g.addColorStop(0.55, U.rgb(ex.darkMid, 1));
      g.addColorStop(1, U.rgb(ex.darkBot, 1));
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, this.CW, this.CH);
    }
    const lift = (sunVis - 0.72) * ex.lift + mt * 0.14;
    if (lift > 0.002) {
      setB(ctx, 'screen', Math.min(lift, 0.20));
      ctx.fillStyle = U.rgb(ex.liftColor, 1);
      ctx.fillRect(0, 0, this.CW, this.CH);
    }
    resetCtx(ctx);
  };

  /* ---------------- 暗角 + 颗粒 ---------------- */
  Engine.prototype._drawFix = function (ctx, t) {
    const S = this.S;
    if (this.fxOff) return;          // ?fx=0：跳过暗角与颗粒
    if (this.vignette) {
      setB(ctx, 'source-over', S.vignette);
      ctx.drawImage(this.vignette, 0, 0);
    }
    if (S.grain > 0 && this.grain) {
      setB(ctx, 'overlay', S.grain);
      const off = (Math.floor(t * 12) * 97) % 256;
      if (!this._grainPat) this._grainPat = ctx.createPattern(this.grain, 'repeat');
      if (this._grainPat) {
        // 一次填充代替四次整屏平铺：overlay 合成成本与覆盖面积成正比
        ctx.save();
        ctx.translate(-off, -off);
        ctx.fillStyle = this._grainPat;
        ctx.fillRect(0, 0, this.CW + 256, this.CH + 256);
        ctx.restore();
      } else {
        ctx.drawImage(this.grain, -off, -off);
        ctx.drawImage(this.grain, -off + 256, -off);
        ctx.drawImage(this.grain, -off, -off + 256);
        ctx.drawImage(this.grain, -off + 256, -off + 256);
      }
    }
    resetCtx(ctx);
  };

  /* ---------------- 主循环 ---------------- */
  Engine.prototype.start = function () {
    const self = this;
    const fixed = this.cfg.fixedTime;
    let last = performance.now();
    let acc = 0, accN = 0;
    function frame(now) {
      const real = (now - last) / 1000;
      last = now;
      const dt = Math.min(0.05, Math.max(0.0005, real));
      if (!self.paused && fixed === undefined) self.time += dt;
      const t = fixed !== undefined ? fixed : self.time;
      const t0 = performance.now();
      try {
        self.render(t, dt);
      } catch (e) {
        self.errors.push(String((e && e.stack) || e));
        if (global.__onEngineError) global.__onEngineError(e);
        throw e;
      }
      const ms = performance.now() - t0;
      acc += ms; accN++;
      if (accN >= 20) { self.stats.ms = acc / accN; self.stats.fps = 1000 / Math.max(0.01, acc / accN); acc = 0; accN = 0; }
      self.stats.frames++;
      if (fixed === undefined) global.requestAnimationFrame(frame);
    }
    global.requestAnimationFrame(frame);
    return this;
  };

  /** 定格渲染一帧（截图 / 自检用） */
  Engine.prototype.renderAt = function (t) {
    this.time = t;
    this.state.sunVis = 1 - this._sampleOcclusion(((t * this.S.cloud.speedShadow * this.cloudSpeed) % 1) * this.shadowW);
    this.render(t, 0.016);
    return this;
  };

  /** 世界坐标 → 草皮落点（透视：远端窄、近端宽） */
  Engine.prototype.pitchPoint = function (u, v) {
    const A = this.A;
    const spread = 0.52 + 0.62 * v;
    const nx = 0.5 + (u - 0.5) * spread * 1.55;
    const ny = A.pitchTop + v * (1.0 - A.pitchTop);
    return { x: this.px(nx), y: this.py(ny), v: v };
  };

  Engine.prototype.setCloudSpeed = function (v) { this.cloudSpeed = U.clamp(v, 0, 3); };
  Engine.prototype.setRainAmount = function (v) { this.rainAmount = U.clamp(v, 0, 1.4); };
  Engine.prototype.setGlassAmount = function (v) { this.glassAmount = U.clamp(v, 0, 1.6); };
  Engine.prototype.setPaused = function (p) { this.paused = !!p; };
  Engine.prototype.destroy = function () {
    global.removeEventListener('resize', this._onResize);
    global.removeEventListener('mousemove', this._onMove);
    global.removeEventListener('touchmove', this._onMove);
  };

  global.SEngine = Engine;
  global.SANCHORS = A;
})(window);
