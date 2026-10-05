/* ============================================================================
 * scenes.js — 四个场景的"配方"（只有参数，没有逻辑）
 *   同一张黄昏实拍原片 + 不同分级与光效 = 白天 / 黄昏 / 黑夜 / 雨天
 *   分级滤镜与灯带锚点沿用工程内既有的四态天气约定（ui-design/login.html）
 * ==========================================================================*/
(function (global) {
  'use strict';

  /* 云层：低层大团（layer1，同时决定地面云影）+ 高层碎云（layer2） */
  function clouds(o) {
    return {
      layer1: { seed: 7, octaves: 5, period: 3.0, stretchY: 2.5, gain: 0.52, warp: 0.60, contrast: 1.0 },
      // fade：云只在"天际线以上"的天空里（归一化 y 之后淡出），避免云压在城市高楼与看台上
      sprite1: { lo: 0.44, hi: 0.80, lit: o.lit1, shade: o.shade1, lightX: -0.85, lightY: -0.55, shading: 1, fade: [0.20, 0.62] },
      alpha1: o.alpha1,
      layer2: { seed: 31, octaves: 4, period: 6.5, stretchY: 4.0, gain: 0.55, warp: 0.45, contrast: 1.0 },
      sprite2: { lo: 0.42, hi: 0.74, lit: o.lit2, shade: o.shade2, lightX: -0.85, lightY: -0.5, shading: 1, fade: [0.16, 0.56] },
      alpha2: o.alpha2,
      shadow: { seed: 7, octaves: 3, period: 3.0, stretchY: 3.4, gain: 0.5, warp: 0.6, contrast: 1.0 },
      shadowMask: { lo: o.sLo, hi: o.sHi, gamma: o.sGamma || 1 },
      shadowNear: o.shadowNear === undefined ? 0.9 : o.shadowNear,
      shadowScene: { color: o.shadowColor, alpha: o.shadowAlpha },
      occMap: o.occMap,                       // 云量→遮挡度的映射（实拍云层模式用）
      photo: o.photo,                         // 有实拍云层贴图时走这条分支（务必透传，漏了会退回程序化云）
      speed1: o.speed1, speed2: o.speed2, speedShadow: o.speed1
    };
  }

  const P = {};

  /* ───────────────────────────── 白天 ───────────────────────────── */
  /* 素材用的是另一张白天实拍：
   * 用户要求（m01176）：云不动、亮度与原片完全一致、只有"光线"随鼠标轻晃。
   * 做法：底板直接用原片 assets/stadium-day.jpg（云在照片里就是原样，静止），
   * 不叠任何分级/压暗/暗角/颗粒；云层与云影全部关掉；鼠标只驱动"光"（太阳辉光 + 光柱），
   * 不移动镜头、不做视差。 */
  P.day = {
    id: 'day',
    name: '白天 · 阳光充足',
    tagline: '球场灯全关 · 云影扫过草坪 · 光影随鼠标轻微晃动',
    accent: '#7ec8ff',
    /* 换素材后地平线位置变了：草坪上沿在原图 y≈0.678（旧片是 0.605） */
    anchors: { skyTop: 0, skyBot: 0.30, skyPaintBot: 0.30, pitchTop: 0.678 },
    /* 云不画（照片里的云就是原样）→ alpha 归零即可，同时省掉云精灵的构建与绘制 */
    cloud: clouds({
      alpha1: 0, alpha2: 0, speed1: 0, speed2: 0,
      lit1: [253, 253, 251], shade1: [140, 160, 188],
      lit2: [255, 255, 255], shade2: [170, 186, 206],
      sLo: 0.42, sHi: 0.78, sGamma: 1.0,
      shadowColor: [26, 38, 60], shadowAlpha: 0, shadowNear: 0.95
    }),
    /* 底板已经是成片，不再分级、不再叠色 */
    base: { backdrop: '#9dc4e8', filter: null, overlays: [] },
    lampsOff: null,
    skyPaint: null,
    /* 太阳在画面外左上（原片的光就在左上角，斜向右下照：看台顶棚左段最亮、云影落在草皮左中）。
       光晕只在左上角加一点点暖光，随鼠标轻微移动 —— 这就是"光线晃动"的来源；
       不做整体压暗/提亮，保证亮度与原片一致。 */
    sun: {
      x: 0.10, y: -0.12, size: 0.20,
      glowColor: [255, 250, 232], wideColor: [255, 252, 240],
      core: 0.11, strength: 0.14, shadeColor: [146, 166, 196], shadeStrength: 0.0
    },
    shaft: { color: [255, 248, 224], alpha: 0.20, angle: -0.30, sceneAlpha: 0.13, sway: 0.35 },
    /* 不改变亮度：暗角/压暗/提亮全部归零，颗粒只留极淡一点防色带 */
    exposure: { darken: 0, lift: 0, liftColor: [255, 250, 236] },
    vignette: 0, grain: 0,
    /* 鼠标只驱动"光"：镜头不动（cam/camY=0）、云不偏移（sky=0）、曝光不随鼠标变（exposure=0），
       只有太阳辉光（sun/sunY）与光柱（shaft）轻微晃动 */
    mouse: { cam: 0, camY: 0, camS: 1.0, sun: 120, sunY: 60, sky: 0, shaft: 120, exposure: 0, glow: 0.16 },
    /* 看得见的"光"：天空里成扇的日光 + 落在草皮上的阳光斑，两者都只随鼠标动 */
    rays: { count: 11, x: 0.10, y: -0.12, color: [255, 250, 232], alpha: 0.30, spread: 0.135, wide: 0.022,
            len: 0.85, mx: 60, my: 28, rot: 0.20, clip: 0.34 },
    /* 草坪光影带（sunPatch）在本版停用 —— 画面 = 原片 + 左上角体积光，草皮保持原片亮度。
       需要“阳光扫过草皮、影子跟着走”时把它打开即可：
       sunPatch: { x: 0.52, y: 0.86, angle: 0.62, len: 0.85, mid: 0.50, soft: 0.17,
                   alpha: 0.20, shadow: 0.40, color: [255, 240, 196], mx: 0.15, my: 0.05 }, */
    /* 体积光层（WebGL，移植自用户给的 LightRays 组件）：**直接照搬组件示例参数**
       （raysColor #ffffff / raysSpeed 1 / lightSpread 0.5 / rayLength 3 / followMouse / mouseInfluence 0.1 /
        noiseAmount 0 / distortion 0 / pulsating false / fadeDistance 1 / saturation 1），
       只把 raysOrigin 按原片的光位改成 top-left。intensity 是移植时加的总强度旋钮，1.0 = 组件原样。 */
    raysGL: { origin: 'top-left', color: '#ffffff', speed: 1, spread: 0.50, length: 3.0,
              intensity: 2.2, fade: 1, saturation: 1, mouseInfluence: 0.1 }
  };

  /* ───────────────────────────── 黄昏 ───────────────────────────── */
  P.dusk = {
    id: 'dusk',
    name: '黄昏 · 落日余晖',
    tagline: '同一套光照逻辑，换成黄昏色调 · 余晖随云层忽明忽暗',
    accent: '#ff9a5c',
    cloud: clouds({
      lit1: [255, 214, 170], shade1: [130, 112, 136], alpha1: 0.50,
      lit2: [255, 226, 190], shade2: [140, 118, 140], alpha2: 0.34,
      sLo: 0.42, sHi: 0.78, sGamma: 1.0,
      shadowColor: [86, 44, 56], shadowAlpha: 0.34, shadowNear: 0.9,
      speed1: 0.0072, speed2: 0.0165
    }),
    base: {
      backdrop: '#2a1e28',
      filter: 'brightness(1.01) saturate(1.12) contrast(1.10)',
      overlays: [
        {
          blend: 'soft-light', alpha: 1,
          grad: {
            y0: 0, y1: 1, stops: [
              [0, [78, 58, 118], 0.30],
              [0.42, [255, 152, 92], 0.24],
              [1, [255, 194, 124], 0.34]]
          }
        },
        {
          blend: 'screen', alpha: 0.22,
          grad: { y0: 0, y1: 0.55, stops: [[0, [255, 186, 126], 0.42], [1, [255, 150, 90], 0]] }
        }
      ]
    },
    lampsOff: { alpha: 1, color: [46, 46, 54] },
    skyPaint: {
      blend: 'source-over', alpha: 1, stops: [
        [0, [44, 48, 88], 0.58],
        [0.34, [140, 104, 138], 0.40],
        [0.68, [226, 146, 106], 0.26],
        [1.00, [255, 200, 138], 0.0]]
    },
    sun: { x: 0.035, y: 0.205, size: 0.62, glowColor: [255, 206, 140], wideColor: [255, 178, 108], core: 0.58, strength: 1.0, shadeColor: [116, 92, 118] },
    shaft: { color: [255, 198, 132], alpha: 0.34, angle: -0.34, sceneAlpha: 0.38 },
    exposure: {
      darken: 0.34, darkTop: [70, 56, 92], darkMid: [86, 66, 96], darkBot: [98, 74, 104],
      lift: 0.24, liftColor: [255, 198, 142]
    },
    vignette: 0.28, grain: 0.05
  };

  /* ───────────────────────────── 黑夜 ───────────────────────────── */
  P.night = {
    id: 'night',
    name: '黑夜 · 灯火通明',
    tagline: '球场灯全开（光锥 + 草地光池）· 城市高楼全部亮灯 · 星空',
    accent: '#ffd479',
    cloud: clouds({
      lit1: [156, 168, 198], shade1: [44, 52, 80], alpha1: 0.52,
      lit2: [140, 154, 186], shade2: [36, 44, 68], alpha2: 0.34,
      sLo: 0.48, sHi: 0.84, sGamma: 1.1,
      shadowColor: [10, 16, 34], shadowAlpha: 0.16, shadowNear: 0.5,
      speed1: 0.0072, speed2: 0.0165
    }),
    base: {
      backdrop: '#04070e',
      filter: 'brightness(0.80) saturate(0.88) contrast(1.14) hue-rotate(-8deg)',
      overlays: [
        {
          blend: 'multiply', alpha: 1,
          grad: {
            y0: 0, y1: 1, stops: [
              [0.00, [5, 10, 22], 0.94],
              [0.30, [6, 12, 26], 0.90],
              [0.42, [8, 14, 30], 0.80],
              [0.60, [11, 17, 34], 0.48],
              [0.70, [13, 19, 36], 0.24],
              [0.84, [15, 21, 38], 0.08],
              [1.00, [17, 23, 40], 0.03]]
          }
        }
      ]
    },
    lampsOff: null,
    skyPaint: {
      blend: 'source-over', alpha: 1, stops: [
        [0, [3, 7, 16], 0.94],
        [0.38, [6, 12, 26], 0.84],
        [0.72, [10, 18, 34], 0.52],
        [1.00, [14, 24, 42], 0.0]]
    },
    sun: { x: 0.72, y: 0.10, size: 0.24, glowColor: [196, 214, 255], wideColor: [130, 160, 220], core: 0.30, strength: 0.30, shadeColor: [58, 74, 110] },
    shaft: { color: [176, 198, 255], alpha: 0.10, angle: -0.30, sceneAlpha: 0.06 },
    exposure: {
      darken: 0.16, darkTop: [40, 52, 78], darkMid: [44, 56, 82], darkBot: [48, 60, 86],
      lift: 0.10, liftColor: [120, 142, 182]
    },
    vignette: 0.44, grain: 0.07,
    night: {
      lampOn: { glow: 0.62, core: 1.0, flicker: 0.035 },
      beam: { count: 4, alpha: 0.26, color: [255, 236, 194], width: 0.34, height: 0.50, sway: 0.9 },
      pool: { alpha: 0.62, color: [255, 240, 202], wobble: 0.05 },
      city: { alpha: 0.92, bloom: 0.40, twinkle: 0.16, color: [255, 226, 170] },
      stars: { count: 190, alpha: 0.42 },
      cityDome: { alpha: 0.20, color: [255, 186, 118] }
    }
  };

  /* ───────────────────────────── 雨天 ───────────────────────────── */
  P.rain = {
    id: 'rain',
    name: '雨天 · 乌云细雨',
    tagline: '乌云压顶 · 雨丝 + 草坪溅落 + 玻璃上的雨滴滑落',
    accent: '#9fc0d8',
    cloud: clouds({
      lit1: [138, 148, 160], shade1: [40, 46, 56], alpha1: 0.80,
      lit2: [126, 136, 148], shade2: [34, 40, 50], alpha2: 0.55,
      sLo: 0.34, sHi: 0.72, sGamma: 1.0,
      shadowColor: [28, 36, 50], shadowAlpha: 0.16, shadowNear: 0.9,
      speed1: 0.0135, speed2: 0.0270
    }),
    base: {
      backdrop: '#2b3138',
      filter: 'brightness(0.70) saturate(0.50) contrast(1.14)',
      overlays: [
        { blend: 'multiply', alpha: 0.34, color: [46, 54, 66] },
        {
          blend: 'screen', alpha: 0.16,
          grad: {
            y0: 0.28, y1: 0.78, stops: [
              [0, [140, 152, 168], 0.0],
              [0.42, [156, 168, 184], 0.9],
              [1, [176, 186, 200], 0.2]]
          }
        },
        { blend: 'multiply', alpha: 0.22, grad: { y0: 0, y1: 0.34, stops: [[0, [30, 36, 46], 0.9], [1, [40, 46, 56], 0]] } }
      ]
    },
    lampsOff: { alpha: 1, color: [40, 44, 52] },
    skyPaint: {
      blend: 'source-over', alpha: 1, stops: [
        [0, [44, 52, 64], 0.90],
        [0.38, [58, 66, 78], 0.66],
        [0.74, [76, 84, 96], 0.34],
        [1.00, [90, 98, 110], 0.0]]
    },
    sun: { x: 0.035, y: 0.185, size: 0.30, glowColor: [186, 196, 208], wideColor: [150, 162, 180], core: 0.06, strength: 0.14, shadeColor: [96, 106, 122] },
    shaft: { color: [180, 190, 205], alpha: 0.08, angle: -0.30, sceneAlpha: 0.05 },
    exposure: {
      darken: 0.20, darkTop: [54, 62, 76], darkMid: [58, 66, 80], darkBot: [62, 70, 84],
      lift: 0.08, liftColor: [176, 188, 202]
    },
    vignette: 0.40, grain: 0.09,
    rain: {
      count: 2600,
      far: { share: 0.55, slant: -0.26, speed: 0.62, len: 0.032, width: 0.9, alpha: 0.34, color: [206, 220, 236] },
      mid: { share: 0.30, slant: -0.24, speed: 0.95, len: 0.050, width: 1.7, alpha: 0.44, color: [216, 228, 242] },
      near: { share: 0.15, slant: -0.22, speed: 1.45, len: 0.090, width: 2.8, alpha: 0.36, color: [232, 240, 250] },
      splash: { max: 150, life: 0.42, color: [224, 236, 248], ring: 0.9, drops: 0.55 },
      mist: { alpha: 0.22, color: [176, 188, 202] },
      wet: { alpha: 0.20, color: [188, 206, 224], sheen: 0.14 },
      glass: { count: 30, minR: 4.5, maxR: 30, blur: 0.7, trail: 0.55, slide: 1.0 }
    }
  };

  global.SCENE_PROFILES = P;
})(window);
