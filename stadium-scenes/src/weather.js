/* ============================================================================
 * weather.js — 黑夜与雨天两个场景的专有图层
 *   黑夜：球场灯（灯带辉光 / 光锥 / 草地光池）+ 城市高楼亮灯 + 星空
 *   雨天：乌云压顶的雾带 + 三层雨丝 + 草坪溅落 + 湿草反光 + 玻璃雨滴滑落
 *   全部按时间参数化，任意 t 都能定格出同一帧。
 * ==========================================================================*/
(function (global) {
  'use strict';
  const U = global.SU;
  /* 注意：SANCHORS 由 engine.js 挂载，本文件在加载时只保存"取用方式"，
     不能在这里直接取值（脚本顺序可能早于 engine.js）。 */
  const an = function () { return global.SANCHORS; };

  /* ==========================================================================
   * 黑夜
   * ========================================================================*/
  const SNight = {
    build: function (eng) {
      const S = eng.S.night, R = eng.imgRect, A = an();
      const raw = U.makeCanvas(eng.CW, eng.CH);
      const rc = raw.getContext('2d');
      rc.drawImage(eng.img, R.x, R.y, R.w, R.h);

      // 1) 原片里本来就亮着的窗（暖色像素）
      const cityY = eng.py(A.cityTop), cityH = (A.cityBot - A.cityTop) * R.h;
      const realLit = U.lightMask(raw, { x: R.x, y: cityY, w: R.w, h: cityH }, {
        threshold: 168, gain: 2.0, tint: [255, 224, 168], tintMix: 0.42, warm: true
      });

      // 2) 楼体遮罩 → 合成"整城亮灯"的窗点（原片黄昏时楼是暗的，窗户必须生成）
      const wins = this._buildWindows(eng, raw, cityY, cityH);
      this.wins = wins;
      const city = U.makeCanvas(eng.CW, eng.CH);
      const cc = city.getContext('2d');
      cc.drawImage(wins, 0, cityY);
      cc.globalCompositeOperation = 'lighter';
      cc.drawImage(realLit, 0, cityY);
      cc.globalCompositeOperation = 'source-over';
      this.cityLights = city;
      this.cityBloom = U.blurredCopy(city, 0.2, 2);

      // 3) 灯带本体
      const lamps = U.makeCanvas(eng.CW, eng.CH);
      const lc = lamps.getContext('2d');
      A.lampBands.forEach(function (b) {
        const bx = R.x + b.x0 * R.w, by = R.y + b.y0 * R.h;
        const bw = (b.x1 - b.x0) * R.w, bh = (b.y1 - b.y0) * R.h;
        const m = U.lightMask(raw, { x: bx, y: by, w: bw, h: bh }, {
          threshold: 178, gain: 2.4, tint: [255, 246, 220], tintMix: 0.5
        });
        lc.drawImage(m, bx, by);
      });
      this.lampLights = lamps;
      this.lampBloom = U.blurredCopy(lamps, 0.16, 2);

      // 4) 复用的精灵
      this.beamSprite = U.beamSprite(256, 512, S.beam.color);
      this.poolSprite = U.glowSprite(512, 256, S.pool.color, 1.0);
      this.lampGlow = U.glowSprite(256, 128, [255, 240, 206], 0.9);

      // 5) 星空（在云之前绘制，云自然遮挡；只留在天际线以上的天空带里）
      this.stars = [];
      for (let i = 0; i < S.stars.count; i++) {
        this.stars.push({
          x: U.hash1(i, 101), y: 0.012 + U.hash1(i, 202) * 0.175,
          r: 0.5 + U.hash1(i, 303) * 1.5,
          ph: U.hash1(i, 404) * 6.28,
          sp: 0.6 + U.hash1(i, 505) * 2.2
        });
      }
      this.lampFlickerPhase = U.hash1(3, 77) * 6.28;
    },

    /* 楼体遮罩内生成窗点：一栋楼一层层亮着，越靠下越密 */
    _buildWindows: function (eng, raw, cityY, cityH) {
      const R = eng.imgRect, dpr = eng.dpr;
      const out = U.makeCanvas(eng.CW, eng.CH);
      const oc = out.getContext('2d');
      const sx = Math.max(0, Math.round(R.x)), sy = Math.max(0, Math.round(cityY));
      const sw = Math.min(raw.width - sx, Math.round(R.w));
      const sh = Math.min(raw.height - sy, Math.round(cityH));
      if (sw <= 8 || sh <= 8) return out;
      let data;
      const tmp = U.makeCanvas(sw, sh);
      const tc = tmp.getContext('2d');
      tc.drawImage(raw, sx, sy, sw, sh, 0, 0, sw, sh);
      try { data = tc.getImageData(0, 0, sw, sh).data; } catch (e) { return out; }

      const step = Math.max(2, Math.round(2.6 * dpr));
      const cellH = Math.max(2, Math.round(3.2 * dpr));
      const twinkle = [];
      let n = 0;
      for (let y = 0; y < sh - cellH; y += cellH) {
        const vNorm = y / sh;                       // 0 = 天际线附近, 1 = 楼底
        const density = 0.16 + 0.42 * vNorm;        // 近处的楼更密
        for (let x = 0; x < sw - step; x += step) {
          const k = ((y + (sy - Math.round(cityY))) * sw + x) * 4;
          const lum = 0.2126 * data[k] + 0.7152 * data[k + 1] + 0.0722 * data[k + 2];
          if (lum > 132) continue;                  // 不是楼体（天空/亮部）
          const h1 = U.hash2(x, y, 11);
          if (h1 > density) continue;
          const warm = U.hash2(x, y, 23);
          const a = 0.35 + 0.65 * U.hash2(x, y, 37);
          const col = warm > 0.72 ? [214, 226, 245] : (warm > 0.3 ? [255, 216, 150] : [255, 232, 190]);
          oc.fillStyle = U.rgb(col, a);
          const ww = Math.max(1, Math.round(step * (0.30 + 0.34 * U.hash2(x, y, 51))));
          const hh = Math.max(1, Math.round(cellH * 0.34));
          oc.fillRect(sx + x, (sy - Math.round(cityY)) + y, ww, hh);
          // 少量"会闪的窗"：整城观感靠它们活起来（避免用切片错相造成竖向接缝）
          if (twinkle.length < 160 && U.hash2(x, y, 61) > 0.86) {
            twinkle.push({
              x: sx + x, y: (sy - Math.round(cityY)) + y, w: ww, h: hh,
              col: col, a: a, ph: U.hash2(x, y, 71) * 6.28,
              sp: 0.5 + U.hash2(x, y, 83) * 2.6
            });
          }
          n++;
        }
      }
      out.__count = n;
      out.__twinkle = twinkle;
      return out;
    },

    drawSky: function (eng, ctx, t, sunVis) {
      const S = eng.S.night, R = eng.imgRect;
      const H = eng.CH;
      for (let i = 0; i < this.stars.length; i++) {
        const s = this.stars[i];
        const tw = 0.55 + 0.45 * Math.sin(t * s.sp + s.ph);
        const a = S.stars.alpha * tw * U.smoothstep(0.36, 0.0, s.y);
        if (a <= 0.01) continue;
        ctx.fillStyle = U.rgb([235, 242, 255], a);
        ctx.beginPath();
        ctx.arc(R.x + s.x * R.w, eng.py(s.y), s.r * eng.dpr, 0, 6.283);
        ctx.fill();
      }
    },

    drawWorld: function (eng, ctx, t, sunVis) {
      const S = eng.S.night, R = eng.imgRect, A = an();
      const flick = 1 - S.lampOn.flicker * (0.5 + 0.5 * Math.sin(t * 1.7 + this.lampFlickerPhase))
        * (0.6 + 0.4 * Math.sin(t * 5.3));

      // ── 城市灯：泛光 + 灯点（裁剪到城市带，省掉整屏合成）
      const cy0 = eng.py(A.cityTop) - 6, cy1 = eng.py(A.cityBot) + 8;
      ctx.save();
      ctx.beginPath(); ctx.rect(R.x, cy0, R.w, cy1 - cy0); ctx.clip();
      setB(ctx, 'screen', S.city.alpha * 0.5 * flick);
      ctx.drawImage(this.cityBloom, 0, 0);
      setB(ctx, 'screen', S.city.alpha * (0.96 + 0.04 * Math.sin(t * 0.9)) * flick);
      ctx.drawImage(this.cityLights, 0, 0);
      // 会闪的窗：逐点亮灭，让"整城灯火"看起来是活的
      const tw = this.wins.__twinkle || [];
      for (let i = 0; i < tw.length; i++) {
        const w0 = tw[i];
        const f = 0.5 + 0.5 * Math.sin(t * w0.sp + w0.ph);
        if (f < 0.55) continue;
        ctx.fillStyle = U.rgb(w0.col, U.clamp((f - 0.55) / 0.45, 0, 1) * w0.a * 0.9);
        ctx.fillRect(w0.x, w0.y, w0.w, w0.h);
      }
      ctx.restore();
      // 城区上空的热雾：把云底照亮
      const dome = ctx.createLinearGradient(0, eng.py(0.02), 0, eng.py(0.44));
      dome.addColorStop(0, U.rgb(S.cityDome.color, 0));
      dome.addColorStop(0.62, U.rgb(S.cityDome.color, S.cityDome.alpha * 0.5));
      dome.addColorStop(1, U.rgb(S.cityDome.color, S.cityDome.alpha));
      setB(ctx, 'screen', 0.75);
      ctx.fillStyle = dome;
      ctx.fillRect(R.x, eng.py(0.02), R.w, eng.py(0.44) - eng.py(0.02));

      // ── 灯带：本体 + 泛光 + 每盏灯的球状辉光（裁剪到看台顶棚一带）
      const ly0 = eng.py(0.30), ly1 = eng.py(0.47);
      ctx.save();
      ctx.beginPath(); ctx.rect(R.x, ly0, R.w, ly1 - ly0); ctx.clip();
      setB(ctx, 'screen', S.lampOn.glow * flick * 0.62);
      ctx.drawImage(this.lampBloom, 0, 0);
      setB(ctx, 'screen', S.lampOn.core * flick);
      ctx.drawImage(this.lampLights, 0, 0);
      ctx.restore();
      const gy = eng.py(0.398), gw = R.w * 0.15, gh = gw * 0.5;
      for (let i = 0; i < A.lampGlows.length; i++) {
        const gx = eng.px(A.lampGlows[i]);
        const a = S.lampOn.glow * flick * (0.5 + 0.45 * Math.sin(t * 3.1 + i));
        setB(ctx, 'screen', a);
        ctx.drawImage(this.lampGlow, gx - gw / 2, gy - gh / 2, gw, gh);
      }

      // ── 光锥：从灯带斜插到草坪，带缓慢摇曳
      const B = S.beam;
      const bh = R.h * B.height;
      const bw = R.w * B.width;
      for (let i = 0; i < A.beamFrom.length; i++) {
        const bx = eng.px(A.beamFrom[i]);
        const sway = B.sway * Math.sin(t * 0.55 + i * 1.7) * 0.02;
        const a = B.alpha * flick * (0.82 + 0.18 * Math.sin(t * 0.9 + i * 2.3));
        ctx.save();
        ctx.translate(bx, eng.py(0.40));
        ctx.rotate(sway + (i < 2 ? -0.10 : 0.10));
        setB(ctx, 'screen', a);
        ctx.drawImage(this.beamSprite, -bw / 2, 0, bw, bh);
        ctx.restore();
      }

      // ── 草地光池：球场灯打在草皮上的一块块亮斑
      const P = S.pool;
      for (let i = 0; i < 5; i++) {
        const u = 0.14 + i * 0.18, v = 0.18 + (i % 2) * 0.22;
        const p = eng.pitchPoint(u, v);
        const w = R.w * (0.30 + 0.06 * (i % 3)), h = w * 0.30;
        const a = P.alpha * flick * (1 - P.wobble + P.wobble * Math.sin(t * 1.3 + i * 1.9));
        setB(ctx, 'screen', a);
        ctx.drawImage(this.poolSprite, p.x - w / 2, p.y - h / 2, w, h);
      }
      // 远端底线一带的整体亮带
      const band = ctx.createLinearGradient(0, eng.py(0.60), 0, eng.py(0.86));
      band.addColorStop(0, U.rgb([255, 238, 198], 0.22 * flick));
      band.addColorStop(0.5, U.rgb([255, 240, 206], 0.10 * flick));
      band.addColorStop(1, U.rgb([255, 240, 206], 0));
      setB(ctx, 'screen', 1);
      ctx.fillStyle = band;
      ctx.fillRect(R.x, eng.py(0.60), R.w, eng.py(0.86) - eng.py(0.60));
      reset(ctx);
    }
  };

  /* ==========================================================================
   * 雨天
   * ========================================================================*/
  const SRain = {
    build: function (eng) {
      const S = eng.S.rain;
      // 雨滴：归一化的落地坐标 + 相位，全部由哈希决定 → 时间参数化
      this.parts = new Float32Array(S.count * 6);
      for (let i = 0; i < S.count; i++) {
        const k = i * 6;
        const r1 = U.hash1(i, 1), r2 = U.hash1(i, 2), r3 = U.hash1(i, 3);
        const group = i % 100;
        let layer = 0;
        if (group < S.far.share * 100) layer = 0;
        else if (group < (S.far.share + S.mid.share) * 100) layer = 1;
        else layer = 2;
        this.parts[k] = 0.06 + r1 * 0.92;          // u（横向）
        this.parts[k + 1] = Math.pow(r2, 0.75);    // v（纵深，越靠前越多）
        this.parts[k + 2] = r3;                    // 相位
        this.parts[k + 3] = 0.75 + U.hash1(i, 4) * 0.55;  // 速度抖动
        this.parts[k + 4] = layer;
        this.parts[k + 5] = U.hash1(i, 5);         // 溅落抽签
      }
      // 草地溅落候选（前 N 个满足条件的粒子）
      const cand = [];
      for (let i = 0; i < S.count && cand.length < S.splash.max * 3; i += 7) {
        if (this.parts[i * 6 + 5] > 0.34) cand.push(i);
      }
      this.splashIdx = cand.slice(0, S.splash.max);

      // 玻璃雨滴：大小不一，各自有"停留 → 滑落 → 蒸发"的周期
      this.drops = [];
      for (let i = 0; i < S.glass.count; i++) {
        const r = S.glass.minR + Math.pow(U.hash1(i, 21), 1.6) * (S.glass.maxR - S.glass.minR);
        this.drops.push({
          x: 0.05 + U.hash1(i, 22) * 0.90,
          y: 0.06 + U.hash1(i, 23) * 0.80,
          r: r,
          cycle: 7 + U.hash1(i, 24) * 9,
          phase: U.hash1(i, 25) * 20,
          sit: 1.6 + U.hash1(i, 26) * 3.4,          // 静止时长
          slide: 2.2 + U.hash1(i, 27) * 3.6,        // 滑落时长
          dist: 0.10 + U.hash1(i, 28) * 0.42,       // 滑落距离（占屏高）
          wob: U.hash1(i, 29) * 2 - 1,
          slides: U.hash1(i, 30) > 0.32              // 约七成会滑落
        });
      }

      // 雾带 / 湿草反光（与尺寸无关，绘制时拉伸）
      this.mistGrad = makeVGrad(8, 256, [
        [0, [176, 188, 202], 0], [0.45, [182, 194, 208], 1],
        [0.75, [190, 200, 214], 0.7], [1, [196, 206, 220], 0]
      ]);
      this.wetGrad = makeVGrad(8, 256, [
        [0, [200, 216, 234], 0.85], [0.35, [188, 206, 226], 0.55],
        [0.75, [180, 198, 220], 0.22], [1, [176, 194, 216], 0.05]
      ]);
    },

    drawWorld: function (eng, ctx, t, sunVis) {
      const S = eng.S.rain, R = eng.imgRect, A = an();
      const P = this.parts, N = eng.rainCount();

      // ── 雨幕后的雾带（城市与看台之间）
      setB(ctx, 'screen', S.mist.alpha);
      ctx.drawImage(this.mistGrad, R.x, eng.py(0.30), R.w, eng.py(0.62) - eng.py(0.30));

      // ── 雨丝：按层 × 3 档透明度一次性描边（性能友好）
      const layers = [S.far, S.mid, S.near];
      for (let li = 0; li < 3; li++) {
        if (li === 2) continue;                    // 最近一层放到前景画布上（更锐利）
        const L = layers[li];
        for (let b = 0; b < 3; b++) {
          const aScale = 0.6 + b * 0.35;
          setB(ctx, 'source-over', L.alpha * aScale);
          ctx.strokeStyle = U.rgb(L.color, 1);
          ctx.lineWidth = L.width * eng.dpr * (0.8 + b * 0.2);
          ctx.lineCap = 'round';
          ctx.beginPath();
          strokeLayer(ctx, eng, P, N, li, b, L.speed, L, t);
          ctx.stroke();
        }
      }
      reset(ctx);

      // ── 草坪溅落
      this._drawSplashes(eng, ctx, t);

      // ── 湿草：压暗 + 反光
      const W = S.wet;
      setB(ctx, 'multiply', 0.22);
      ctx.fillStyle = U.rgb([34, 46, 60], 1);
      ctx.fillRect(R.x, eng.py(A.pitchTop - 0.01), R.w, eng.py(1.0) - eng.py(A.pitchTop - 0.01));
      setB(ctx, 'screen', W.alpha * 0.9);
      ctx.drawImage(this.wetGrad, R.x, eng.py(A.pitchTop - 0.01), R.w, eng.py(1.0) - eng.py(A.pitchTop - 0.01));
      // 缓慢流动的水光
      const sh = ctx.createLinearGradient(R.x, 0, R.x + R.w, 0);
      const o = (t * 0.045) % 1;
      sh.addColorStop(Math.max(0, o - 0.18), U.rgb(W.color, 0));
      sh.addColorStop(o, U.rgb(W.color, W.sheen));
      sh.addColorStop(Math.min(1, o + 0.18), U.rgb(W.color, 0));
      setB(ctx, 'screen', 0.8);
      ctx.fillStyle = sh;
      ctx.fillRect(R.x, eng.py(A.pitchTop - 0.01), R.w, eng.py(1.0) - eng.py(A.pitchTop - 0.01));
      reset(ctx);

      // ── 远处极淡的闪电（乌云场景的自然点缀，强度很低）
      const fl = flash(t);
      if (fl > 0.01) {
        setB(ctx, 'screen', fl * 0.10);
        ctx.fillStyle = U.rgb([190, 206, 236], 1);
        ctx.fillRect(0, 0, eng.CW, eng.CH);
        setB(ctx, 'screen', fl * 0.09);
        ctx.drawImage(eng.glowWide, eng.px(0.62) - R.w * 0.5, eng.py(0.02) - R.h * 0.2, R.w, R.h * 0.5);
        reset(ctx);
      }
    },

    _drawSplashes: function (eng, ctx, t) {
      const S = eng.S.rain.splash;
      const RR = eng.S.rain;
      const speeds = [RR.far.speed, RR.mid.speed, RR.near.speed];
      const P = this.parts;
      const dpr = eng.dpr;
      for (let n = 0; n < this.splashIdx.length; n++) {
        const i = this.splashIdx[n];
        const k = i * 6;
        const layer = P[k + 4] | 0;
        const rate = speeds[layer] * P[k + 3];
        const cyc = (P[k + 2] + t * rate) % 1.2;
        if (cyc < 1) continue;                     // 还在空中
        const cycleDur = 1.2 / rate;
        const age = (cyc - 1) * cycleDur;
        const fr = age / S.life;
        if (fr >= 1 || fr < 0) continue;
        const g = eng.pitchPoint(P[k], P[k + 1]);
        const depth = 0.35 + 0.75 * P[k + 1];
        const R0 = (1.6 + 8 * Math.sqrt(fr)) * depth * dpr;
        const a = Math.pow(1 - fr, 1.7) * 0.75;
        ctx.save();
        setB(ctx, 'screen', a * S.ring);
        ctx.strokeStyle = U.rgb(S.color, 1);
        ctx.lineWidth = Math.max(0.6, 1.5 * depth * dpr);
        ctx.beginPath();
        ctx.ellipse(g.x, g.y, R0, R0 * 0.34, 0, 0, 6.283);
        ctx.stroke();
        if (fr < 0.45) {
          setB(ctx, 'screen', a * 0.5 * (1 - fr / 0.45));
          ctx.fillStyle = U.rgb(S.color, 1);
          ctx.beginPath();
          ctx.ellipse(g.x, g.y, R0 * 0.5, R0 * 0.2, 0, 0, 6.283);
          ctx.fill();
        }
        // 溅起的小水珠
        setB(ctx, 'screen', a * S.drops);
        ctx.fillStyle = U.rgb(S.color, 1);
        for (let q = 0; q < 3; q++) {
          const ang = (q / 3) * 6.283 + i;
          const v0 = (26 + 22 * U.hash1(i, 40 + q)) * depth * dpr;
          const hy = v0 * age - 0.5 * 320 * depth * dpr * age * age;
          if (hy < 0) continue;
          const hx = g.x + Math.cos(ang) * v0 * age * 0.45;
          ctx.beginPath();
          ctx.arc(hx, g.y - hy * 0.5, Math.max(0.5, 1.3 * depth * dpr), 0, 6.283);
          ctx.fill();
        }
        ctx.restore();
        reset(ctx);
      }
    },

    /* 前景层：近处雨丝（跟随镜头）+ 贴在"玻璃"上的雨滴（不跟随镜头） */
    drawFx: function (eng, fx, t, sunVis) {
      const S = eng.S.rain, R = eng.imgRect;
      const P = this.parts, N = eng.rainCount === undefined ? S.count : eng.rainCount;
      const L = S.near;

      for (let b = 0; b < 3; b++) {
        setB(fx, 'source-over', L.alpha * (0.55 + b * 0.4));
        fx.strokeStyle = U.rgb(L.color, 1);
        fx.lineWidth = L.width * eng.dpr * (0.8 + b * 0.25);
        fx.lineCap = 'round';
        fx.beginPath();
        strokeLayer(fx, eng, P, N, 2, b, L.speed, L, t);
        fx.stroke();
      }
      reset(fx);

      // 之后的一切都贴在镜头上，用屏幕坐标
      fx.setTransform(1, 0, 0, 1, 0, 0);
      fx.globalCompositeOperation = 'source-over';
      this._drawGlass(eng, fx, t, sunVis);
      reset(fx);
    },

    _drawGlass: function (eng, fx, t, sunVis) {
      const S = eng.S.rain.glass;
      const CW = eng.CW, CH = eng.CH, stage = eng.stage;
      const scale = CH / 900;
      const ga = eng.glassAmount === undefined ? 1 : eng.glassAmount;
      if (ga <= 0.01) return;
      for (let i = 0; i < this.drops.length; i++) {
        const d = this.drops[i];
        if (!d.slides && (i % 3 !== 0)) continue;          // 关闭部分"只挂不落"的雨滴
        const cyc = ((t * S.slide + d.phase) % d.cycle + d.cycle) % d.cycle;
        const r = Math.max(3, d.r * scale);
        const popIn = U.smoothstep(0, 0.18, cyc);
        const dead = cyc > d.sit + d.slide;
        const life = d.cycle - (d.sit + d.slide);
        const fade = dead ? U.clamp(1 - (cyc - d.sit - d.slide) / Math.max(0.4, life * 0.55), 0, 1) : 1;
        if (fade <= 0.01) continue;

        let prog = 0, sliding = false;
        if (cyc > d.sit && d.slides) {
          const sp = U.clamp((cyc - d.sit) / d.slide, 0, 1);
          prog = sp * sp * (3 - 2 * sp) * d.dist;
          sliding = sp < 1;
        }
        const x = d.x * CW + Math.sin(t * 0.5 + i) * 0.6 * scale;
        const y = (d.y + prog) * CH;
        const rNow = r * (0.55 + 0.45 * popIn);
        const alpha = fade * popIn * ga;

        // 滑落痕迹：一道湿痕 + 沿途残留的细小水珠（竖向拉长，不是小圆圈）
        if (prog > 0.004 && S.trail > 0) {
          const yTop = d.y * CH;
          const g = fx.createLinearGradient(0, yTop, 0, y);
          g.addColorStop(0, 'rgba(226,238,250,0)');
          g.addColorStop(0.55, U.rgb([226, 238, 250], 0.05 * alpha * S.trail * 4));
          g.addColorStop(1, U.rgb([236, 246, 255], 0.20 * alpha * S.trail * 2));
          fx.strokeStyle = g;
          fx.lineWidth = Math.max(1, rNow * 0.5);
          fx.lineCap = 'round';
          fx.beginPath();
          fx.moveTo(x, yTop);
          fx.lineTo(x + d.wob * 2 * scale, (yTop + y) / 2);
          fx.lineTo(x, y - rNow * 0.4);
          fx.stroke();
          for (let q = 1; q <= 4; q++) {
            const tt = q / 5;
            const ty = yTop + (y - yTop) * tt;
            const bx = x + Math.sin(q * 2.3 + i) * rNow * 0.34;
            const br = Math.max(0.5, rNow * (0.07 + 0.05 * (q % 2)));
            fx.fillStyle = U.rgb([236, 246, 255], 0.15 * alpha * (0.4 + 0.6 * tt));
            fx.beginPath();
            fx.ellipse(bx, ty, br, br * 1.9, 0, 0, 6.283);
            fx.fill();
            fx.fillStyle = 'rgba(12,20,32,' + (0.10 * alpha) + ')';
            fx.beginPath();
            fx.ellipse(bx, ty + br * 1.6, br * 0.9, br * 0.7, 0, 0, 6.283);
            fx.fill();
          }
        }

        // 雨滴本体：画进一张小离屏画布 → 透镜折射 + 柔边羽化 → 贴上来
        // （真实的水滴是"透亮"的：边缘柔、内部能看到身后景物被透镜扭一下，
        //   所以不做硬圆边、不做厚暗环，避免变成肥皂泡）
        const elong = sliding ? 1 + Math.min(0.26, prog * 0.6) : 1;
        const rx = rNow, ry = rNow * elong;
        const S2 = Math.ceil(rx * 2.2) + 6;
        if (!this._dropCv || this._dropS < S2) {
          this._dropCv = U.makeCanvas(Math.max(24, S2), Math.max(24, S2));
          this._dropS = Math.max(24, S2);
        }
        const sc = this._dropCv.getContext('2d');
        const C = this._dropS / 2;
        sc.setTransform(1, 0, 0, 1, 0, 0);
        sc.clearRect(0, 0, this._dropS, this._dropS);
        sc.save();
        sc.translate(C, C);
        sc.beginPath();
        sc.ellipse(0, 0, rx, ry, 0, 0, 6.283);
        sc.clip();
        // 凸透镜：把身后景物放大 1.7 倍并倒转、以半透明叠上来（水是透的，底子要透出来）
        const k = 1.7;
        sc.save();
        sc.rotate(Math.PI);
        sc.globalAlpha = 0.70;
        try {
          sc.drawImage(stage, x - rx / k, y - ry / k, rx * 2 / k, ry * 2 / k,
            -rx, -ry, rx * 2, ry * 2);
        } catch (e) { /* 忽略个别取景越界 */ }
        sc.restore();
        // 聚光：中心一点点提亮
        const lg = sc.createRadialGradient(-rx * 0.22, -ry * 0.28, rx * 0.06, 0, 0, rx);
        lg.addColorStop(0, 'rgba(255,255,255,' + (0.18 * alpha) + ')');
        lg.addColorStop(0.55, 'rgba(255,255,255,' + (0.02 * alpha) + ')');
        lg.addColorStop(1, 'rgba(255,255,255,0)');
        sc.fillStyle = lg;
        sc.fillRect(-rx, -ry, rx * 2, ry * 2);
        // 底部焦散亮弧（细、短，不绕满一圈）
        sc.strokeStyle = 'rgba(255,255,255,' + (0.24 * alpha) + ')';
        sc.lineWidth = Math.max(0.6, rx * 0.055);
        sc.beginPath();
        sc.ellipse(0, 0, rx * 0.72, ry * 0.72, 0, 0.80, 2.36);
        sc.stroke();
        // 上缘内侧的一道细暗边（透镜把暗部折进来的那一线）
        sc.strokeStyle = 'rgba(10,18,30,' + (0.20 * alpha) + ')';
        sc.lineWidth = Math.max(0.6, rx * 0.08);
        sc.beginPath();
        sc.ellipse(0, 0, rx * 0.90, ry * 0.90, 0, 3.45, 5.95);
        sc.stroke();
        // 高光：一大一小两点
        sc.fillStyle = 'rgba(255,255,255,' + (0.80 * alpha) + ')';
        sc.beginPath();
        sc.ellipse(-rx * 0.32, -ry * 0.38, rx * 0.15, ry * 0.10, -0.55, 0, 6.283);
        sc.fill();
        sc.fillStyle = 'rgba(255,255,255,' + (0.45 * alpha) + ')';
        sc.beginPath();
        sc.arc(rx * 0.30, ry * 0.26, Math.max(0.5, rx * 0.055), 0, 6.283);
        sc.fill();
        sc.restore();
        // 柔边：把圆边羽化掉，水滴才像"透亮"而不是一颗球
        sc.globalCompositeOperation = 'destination-in';
        const fg = sc.createRadialGradient(C, C, 0, C, C, rx);
        fg.addColorStop(0, 'rgba(0,0,0,1)');
        fg.addColorStop(0.78, 'rgba(0,0,0,1)');
        fg.addColorStop(1, 'rgba(0,0,0,0)');
        sc.fillStyle = fg;
        sc.fillRect(0, 0, this._dropS, this._dropS);
        sc.globalCompositeOperation = 'source-over';
        // 落点接触阴影：水滴贴在玻璃上的那一点点暗（柔、偏下、收在珠体内）
        fx.fillStyle = 'rgba(8,14,24,' + (0.12 * alpha) + ')';
        fx.beginPath();
        fx.ellipse(x + rx * 0.05, y + ry * 0.30, rx * 0.78, ry * 0.66, 0, 0, 6.283);
        fx.fill();
        fx.drawImage(this._dropCv, x - C, y - C);
      }
    }
  };

  /* ---------------- 小工具 ---------------- */
  function setB(ctx, mode, a) { ctx.globalCompositeOperation = mode; ctx.globalAlpha = a; }
  function reset(ctx) { ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1; }

  /** 某一层的某档透明度：把所有粒子攒进一条路径，一次描边 */
  function strokeLayer(ctx, eng, P, N, layer, bucket, rate, L, t) {
    const R = eng.imgRect, CH = eng.CH;
    const startY = -0.15 * CH;
    const len = L.len * CH;
    const startIdx = Math.floor(N * (layer === 0 ? 0 : (layer === 1 ? eng.S.rain.far.share : eng.S.rain.far.share + eng.S.rain.mid.share)));
    const endIdx = layer === 0 ? Math.floor(N * eng.S.rain.far.share)
      : (layer === 1 ? Math.floor(N * (eng.S.rain.far.share + eng.S.rain.mid.share)) : N);
    const nrm = Math.sqrt(1 + L.slant * L.slant);
    for (let i = startIdx; i < endIdx; i++) {
      const k = i * 6;
      if (P[k + 4] !== layer) continue;
      if ((i % 3) !== bucket) continue;
      const sp = rate * P[k + 3];
      const cyc = (P[k + 2] + t * sp) % 1.2;
      if (cyc >= 1) continue;                    // 已落地，交给溅落
      const g = eng.pitchPoint(P[k], P[k + 1]);
      const y = startY + (g.y - startY) * cyc;
      const x = g.x - L.slant * (g.y - y);
      ctx.moveTo(x, y);
      ctx.lineTo(x - L.slant / nrm * len, y - len / nrm);
    }
  }

  function makeVGrad(w, h, stops) {
    const cv = U.makeCanvas(w, h);
    const c = cv.getContext('2d');
    const g = c.createLinearGradient(0, 0, 0, h);
    stops.forEach(function (s) { g.addColorStop(s[0], U.rgb(s[1], s[2])); });
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
    return cv;
  }

  /** 远处闪电：解析式双闪，强度很低 */
  function flash(t) {
    const T = 12.5;
    const k = Math.floor(t / T);
    if (U.hash1(k, 9) < 0.42) return 0;
    const local = t - k * T;
    const p1 = Math.exp(-Math.pow((local - 0.5) / 0.11, 2));
    const p2 = 0.55 * Math.exp(-Math.pow((local - 1.05) / 0.20, 2));
    return U.clamp((p1 + p2) * (0.45 + 0.55 * U.hash1(k, 5)), 0, 1);
  }

  global.SNight = SNight;
  global.SRain = SRain;
})(window);
