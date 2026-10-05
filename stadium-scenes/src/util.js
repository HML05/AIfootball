/* ============================================================================
 * util.js — 噪声 / 云场纹理 / 画布工具
 * 无依赖，浏览器原生 Canvas 2D。所有纹理一次生成、逐帧复用。
 * ==========================================================================*/
(function (global) {
  'use strict';

  const U = {};

  /* ---------------- 数学 ---------------- */
  U.clamp = function (v, a, b) { return v < a ? a : (v > b ? b : v); };
  U.lerp = function (a, b, t) { return a + (b - a) * t; };
  U.smoothstep = function (e0, e1, x) {
    const t = U.clamp((x - e0) / (e1 - e0 || 1e-6), 0, 1);
    return t * t * (3 - 2 * t);
  };
  // 帧率无关的指数平滑
  U.approach = function (cur, target, dt, halfLife) {
    if (halfLife <= 0) return target;
    const k = 1 - Math.pow(0.5, dt / halfLife);
    return cur + (target - cur) * k;
  };
  U.mixColor = function (c1, c2, t) {
    return [U.lerp(c1[0], c2[0], t), U.lerp(c1[1], c2[1], t), U.lerp(c1[2], c2[2], t)];
  };
  U.rgb = function (c, a) {
    a = (a === undefined) ? 1 : a;
    return 'rgba(' + (c[0] | 0) + ',' + (c[1] | 0) + ',' + (c[2] | 0) + ',' + a + ')';
  };

  /* ---------------- 哈希（确定性，便于用 ?t= 定格截图） ---------------- */
  U.hash1 = function (i, seed) {
    let n = Math.imul(i | 0, 374761393) ^ Math.imul((seed | 0) + 1, 668265263);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  };
  function hash2(x, y, seed) {
    let n = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(seed | 0, 2246822519);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  }
  U.hash2 = hash2;

  /* ---------------- 可平铺值噪声 + fBm ----------------
   * x 方向周期为 px（保证左右无缝，云可以无限横移），y 方向不循环。 */
  function vnoise(x, y, px, seed) {
    const xi = Math.floor(x), yi = Math.floor(y);
    let xf = x - xi, yf = y - yi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    const x0 = ((xi % px) + px) % px, x1 = ((xi + 1) % px + px) % px;
    const y0 = yi, y1 = yi + 1;
    const a = hash2(x0, y0, seed), b = hash2(x1, y0, seed);
    const c = hash2(x0, y1, seed), d = hash2(x1, y1, seed);
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v;
  }
  U.vnoise = vnoise;

  /**
   * 生成一块可横向平铺的 fBm 云密度场。
   * @returns {Float32Array} 长度 w*h，值域约 [0,1]
   */
  U.cloudGrid = function (w, h, opt) {
    opt = opt || {};
    const seed = opt.seed === undefined ? 1 : opt.seed;
    const octaves = opt.octaves || 5;
    const period = opt.period || 3;      // 基础横向周期数（越大云越碎）
    const stretchY = opt.stretchY || 2.4; // 云被横向拉长
    const gain = opt.gain || 0.5;
    const lac = opt.lacunarity || 2.0;
    const warp = opt.warp === undefined ? 0.55 : opt.warp;
    const contrast = opt.contrast === undefined ? 1 : opt.contrast;
    const grid = new Float32Array(w * h);
    for (let j = 0; j < h; j++) {
      const jn = j / h;
      for (let i = 0; i < w; i++) {
        const inorm = i / w;
        // 域扭曲：让云有翻卷的团块感，而不是纯噪声
        const wx = (vnoise(inorm * 2, jn * 3, 2, seed + 977) - 0.5) * warp;
        const wy = (vnoise(inorm * 2 + 11.3, jn * 3 + 5.1, 2, seed + 613) - 0.5) * warp * 0.6;
        let amp = 1, sum = 0, norm = 0, per = period, fy = stretchY;
        for (let o = 0; o < octaves; o++) {
          sum += amp * vnoise((inorm + wx) * per, (jn + wy) * fy, per, seed + o * 131);
          norm += amp;
          amp *= gain; per *= lac; fy *= lac;
        }
        let n = sum / norm;
        n = U.clamp(0.5 + (n - 0.5) * contrast, 0, 1);
        grid[j * w + i] = n;
      }
    }
    return grid;
  };

  U.makeCanvas = function (w, h) {
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(w));
    c.height = Math.max(1, Math.round(h));
    return c;
  };

  /**
   * 把密度场渲染成一张"自带明暗"的云精灵（可横向平铺）。
   * alpha 由密度阈值切出，rgb 按密度梯度上光，得到体积感。
   */
  U.cloudSprite = function (w, h, grid, opt) {
    opt = opt || {};
    const lo = opt.lo === undefined ? 0.42 : opt.lo;
    const hi = opt.hi === undefined ? 0.78 : opt.hi;
    const alphaMax = opt.alphaMax === undefined ? 1 : opt.alphaMax;
    const lit = opt.lit || [255, 255, 255];
    const shade = opt.shade || [150, 160, 180];
    const lx = opt.lightX === undefined ? -0.8 : opt.lightX; // 受光方向（-1 = 左上）
    const ly = opt.lightY === undefined ? -0.6 : opt.lightY;
    const shading = opt.shading === undefined ? 1 : opt.shading;
    // fade: [f0, f1] —— 精灵纵向淡出（归一化 y），让云只留在天际线以上的天空里
    const fade = opt.fade || null;
    const cv = U.makeCanvas(w, h);
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(w, h);
    const d = img.data;
    const at = (x, y) => grid[(((y % h) + h) % h) * w + (((x % w) + w) % w)];
    for (let j = 0; j < h; j++) {
      const fv = fade ? 1 - U.smoothstep(fade[0], fade[1], j / h) : 1;
      if (fv <= 0.002) continue;
      for (let i = 0; i < w; i++) {
        const n = grid[j * w + i];
        let a = U.smoothstep(lo, hi, n) * alphaMax * fv;
        if (a <= 0.002) continue;
        // 密度梯度 → 受光面
        const gx = at(i + 1, j) - at(i - 1, j);
        const gy = at(i, j + 1) - at(i, j - 1);
        const litF = U.clamp(0.5 + 0.5 * (gx * lx + gy * ly) * 26 * shading, 0, 1);
        const c = U.mixColor(shade, lit, litF);
        const k = (j * w + i) * 4;
        d[k] = c[0]; d[k + 1] = c[1]; d[k + 2] = c[2]; d[k + 3] = a * 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    return cv;
  };

  /** 密度场 → 单通道 alpha 遮罩（用于地面云影，纯灰度，靠混合模式上色） */
  U.gridToMask = function (w, h, grid, opt) {
    opt = opt || {};
    const lo = opt.lo === undefined ? 0.40 : opt.lo;
    const hi = opt.hi === undefined ? 0.72 : opt.hi;
    const gamma = opt.gamma === undefined ? 1 : opt.gamma;
    const cv = U.makeCanvas(w, h);
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(w, h);
    const d = img.data;
    for (let i = 0, n = w * h; i < n; i++) {
      let a = U.smoothstep(lo, hi, grid[i]);
      a = Math.pow(a, gamma);
      const k = i * 4;
      d[k] = 255; d[k + 1] = 255; d[k + 2] = 255; d[k + 3] = a * 255;
    }
    ctx.putImageData(img, 0, 0);
    return cv;
  };

  /** 生成一张软光斑精灵（椭圆径向渐变），用于光池 / 辉光 / 光锥落点 */
  U.glowSprite = function (w, h, color, power) {
    const cv = U.makeCanvas(w, h);
    const ctx = cv.getContext('2d');
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) / 2);
    power = power || 1;
    for (let i = 0; i <= 10; i++) {
      const t = i / 10;
      const a = Math.pow(1 - t, 2.2 * power);
      g.addColorStop(t, U.rgb(color, a));
    }
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    return cv;
  };

  /** 光锥精灵：从顶部顶点向下张开的柔光楔形 */
  U.beamSprite = function (w, h, color) {
    const cv = U.makeCanvas(w, h);
    const ctx = cv.getContext('2d');
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, U.rgb(color, 0.55));
    g.addColorStop(0.35, U.rgb(color, 0.22));
    g.addColorStop(1, U.rgb(color, 0));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(w * 0.42, 0);
    ctx.lineTo(w * 0.58, 0);
    ctx.lineTo(w, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fill();
    // 横向羽化
    ctx.globalCompositeOperation = 'destination-in';
    const g2 = ctx.createLinearGradient(0, 0, w, 0);
    g2.addColorStop(0, U.rgb([255, 255, 255], 0));
    g2.addColorStop(0.28, U.rgb([255, 255, 255], 1));
    g2.addColorStop(0.72, U.rgb([255, 255, 255], 1));
    g2.addColorStop(1, U.rgb([255, 255, 255], 0));
    ctx.fillStyle = g2;
    ctx.fillRect(0, 0, w, h);
    return cv;
  };

  /** 低对比噪点，给画面加一点点颗粒，避免色带 */
  U.grainSprite = function (size, strength) {
    const cv = U.makeCanvas(size, size);
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(size, size);
    const d = img.data;
    for (let i = 0, n = size * size; i < n; i++) {
      const v = 128 + (U.hash1(i, 7) - 0.5) * 255 * (strength || 0.5);
      const k = i * 4;
      d[k] = d[k + 1] = d[k + 2] = v;
      d[k + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    return cv;
  };

  /**
   * 把一张"云层贴图"的 alpha 降采样成粗略的云量网格（0~1 Float32Array）。
   * 用来做云影投影与"云遮日"采样：网格本身就是可横向循环的，所以云影能跟着云一起走。
   * 贴图没有 alpha 通道时退回用亮度当云量。
   */
  U.gridFromAlpha = function (img, gw, gh, opt) {
    opt = opt || {};
    const gamma = opt.gamma === undefined ? 1.0 : opt.gamma;
    const out = new Float32Array(gw * gh);
    const cv = U.makeCanvas(gw, gh);
    const c = cv.getContext('2d');
    c.imageSmoothingEnabled = true;
    try { c.drawImage(img, 0, 0, gw, gh); } catch (e) { return out; }
    let data;
    try { data = c.getImageData(0, 0, gw, gh).data; }
    catch (e) { return out; }
    for (let i = 0, n = gw * gh; i < n; i++) {
      const k = i * 4;
      const a = data[k + 3] / 255;
      const lum = (0.2126 * data[k] + 0.7152 * data[k + 1] + 0.0722 * data[k + 2]) / 255;
      const v = a > 0.02 ? a : Math.max(0, (lum - 0.86) / 0.14) * 0.6;
      out[i] = Math.pow(U.clamp(v, 0, 1), gamma);
    }
    return out;
  };

  /** 把画布内容整体模糊一份（用缩放降采样近似，避免依赖 ctx.filter 的性能波动） */
  U.blurredCopy = function (src, scale, passes) {
    scale = scale || 0.25;
    passes = passes || 2;
    let cur = src;
    for (let p = 0; p < passes; p++) {
      const w = Math.max(2, Math.round(cur.width * scale));
      const h = Math.max(2, Math.round(cur.height * scale));
      const small = U.makeCanvas(w, h);
      const sc = small.getContext('2d');
      sc.imageSmoothingEnabled = true;
      sc.drawImage(cur, 0, 0, w, h);
      const back = U.makeCanvas(cur.width, cur.height);
      const bc = back.getContext('2d');
      bc.imageSmoothingEnabled = true;
      bc.drawImage(small, 0, 0, back.width, back.height);
      cur = back;
    }
    return cur;
  };

  /** 取亮度阈值以上的像素，做"城市亮灯 / 灯带"用的自发光图层 */
  U.lightMask = function (src, rect, opt) {
    opt = opt || {};
    const thr = opt.threshold === undefined ? 150 : opt.threshold;
    const gain = opt.gain === undefined ? 1.6 : opt.gain;
    const tint = opt.tint || [255, 240, 205];
    const mixAmt = opt.tintMix === undefined ? 0.35 : opt.tintMix;
    const warm = opt.warm ? 1 : 0;   // 只认暖色亮部（黄昏原片里的窗户）
    const w = Math.max(1, Math.round(rect.w)), h = Math.max(1, Math.round(rect.h));
    const sx = Math.max(0, Math.round(rect.x)), sy = Math.max(0, Math.round(rect.y));
    const sw = Math.min(src.width - sx, w), sh = Math.min(src.height - sy, h);
    const out = U.makeCanvas(w, h);
    const oc = out.getContext('2d');
    if (sw <= 0 || sh <= 0) return out;
    const tmp = U.makeCanvas(sw, sh);
    const tc = tmp.getContext('2d');
    tc.drawImage(src, sx, sy, sw, sh, 0, 0, sw, sh);
    let data;
    try { data = tc.getImageData(0, 0, sw, sh); }
    catch (e) { return out; }   // 万一跨域污染，静默退回空图层
    const d = data.data;
    for (let i = 0, n = sw * sh; i < n; i++) {
      const k = i * 4;
      const lum = 0.2126 * d[k] + 0.7152 * d[k + 1] + 0.0722 * d[k + 2];
      let a = U.smoothstep(thr, thr + 70, lum);
      a = Math.pow(a, 1.35);
      if (warm) a *= U.smoothstep(3, 32, d[k] - d[k + 2]);   // 偏暖才算灯
      d[k] = U.clamp(U.lerp(d[k], tint[0], mixAmt) * gain, 0, 255);
      d[k + 1] = U.clamp(U.lerp(d[k + 1], tint[1], mixAmt) * gain, 0, 255);
      d[k + 2] = U.clamp(U.lerp(d[k + 2], tint[2], mixAmt) * gain, 0, 255);
      d[k + 3] = a * 255;
    }
    oc.putImageData(data, 0, 0);
    return out;
  };

  U.loadImage = function (src) {
    return new Promise(function (res, rej) {
      const im = new Image();
      im.onload = function () { res(im); };
      im.onerror = function () { rej(new Error('背景图加载失败')); };
      im.src = src;
    });
  };

  global.SU = U;
})(window);
