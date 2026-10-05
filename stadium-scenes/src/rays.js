/* rays.js — WebGL 体积光（移植自用户提供的 LightRays 组件）
   全局：window.SRays.create(canvas, opts) → { render(t, mx, my), resize(), ok, dispose() } | null
   与 LightRays 组件同源：同一个 fragment shader（rayStrength 双采样 + 鼠标方向混合 + 亮度渐变），
   不依赖 ogl/react，直接用原生 WebGL 画一张全屏三角形，靠 CSS mix-blend-mode:screen 叠加到画面上。 */
(function (global) {
  'use strict';
  if (!global.SRays) global.SRays = {};
  var SRays = global.SRays;

  var VERT = 'attribute vec2 position;' +
    'varying vec2 vUv;' +
    'void main(){ vUv = position * 0.5 + 0.5; gl_Position = vec4(position, 0.0, 1.0); }';

  // 与组件 frag 一致；额外加 intensity（整体强度）与 raysAlpha 无关，其余语义相同
  var FRAG = [
    'precision highp float;',
    'uniform float iTime;',
    'uniform vec2  iResolution;',
    'uniform vec2  rayPos;',
    'uniform vec2  rayDir;',
    'uniform vec3  raysColor;',
    'uniform float raysSpeed;',
    'uniform float lightSpread;',
    'uniform float rayLength;',
    'uniform float pulsating;',
    'uniform float fadeDistance;',
    'uniform float saturation;',
    'uniform vec2  mousePos;',
    'uniform float mouseInfluence;',
    'uniform float noiseAmount;',
    'uniform float distortion;',
    'uniform float intensity;',
    'varying vec2 vUv;',
    'float noise(vec2 st){ return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123); }',
    'float rayStrength(vec2 raySource, vec2 rayRefDirection, vec2 coord, float seedA, float seedB, float speed){',
    '  vec2 sourceToCoord = coord - raySource;',
    '  vec2 dirNorm = normalize(sourceToCoord);',
    '  float cosAngle = dot(dirNorm, rayRefDirection);',
    '  float distortedAngle = cosAngle + distortion * sin(iTime * 2.0 + length(sourceToCoord) * 0.01) * 0.2;',
    '  float spreadFactor = pow(max(distortedAngle, 0.0), 1.0 / max(lightSpread, 0.001));',
    '  float distance = length(sourceToCoord);',
    '  float maxDistance = iResolution.x * rayLength;',
    '  float lengthFalloff = clamp((maxDistance - distance) / maxDistance, 0.0, 1.0);',
    '  float fadeFalloff = clamp((iResolution.x * fadeDistance - distance) / (iResolution.x * fadeDistance), 0.5, 1.0);',
    '  float pulse = pulsating > 0.5 ? (0.8 + 0.2 * sin(iTime * speed * 3.0)) : 1.0;',
    '  float baseStrength = clamp((0.45 + 0.15 * sin(distortedAngle * seedA + iTime * speed)) +',
    '                             (0.3 + 0.2 * cos(-distortedAngle * seedB + iTime * speed)), 0.0, 1.0);',
    '  return baseStrength * lengthFalloff * fadeFalloff * spreadFactor * pulse;',
    '}',
    'void main(){',
    '  vec2 fragCoord = gl_FragCoord.xy;',
    '  vec2 coord = vec2(fragCoord.x, iResolution.y - fragCoord.y);',
    '  vec2 finalRayDir = rayDir;',
    '  if (mouseInfluence > 0.0) {',
    '    vec2 mouseScreenPos = mousePos * iResolution.xy;',
    '    vec2 mouseDirection = normalize(mouseScreenPos - rayPos);',
    '    finalRayDir = normalize(mix(rayDir, mouseDirection, mouseInfluence));',
    '  }',
    '  vec4 rays1 = vec4(1.0) * rayStrength(rayPos, finalRayDir, coord, 36.2214, 21.11349, 1.5 * raysSpeed);',
    '  vec4 rays2 = vec4(1.0) * rayStrength(rayPos, finalRayDir, coord, 22.3991, 18.0234, 1.1 * raysSpeed);',
    '  vec4 fragColor = rays1 * 0.5 + rays2 * 0.4;',
    '  if (noiseAmount > 0.0) {',
    '    float n = noise(coord * 0.01 + iTime * 0.1);',
    '    fragColor.rgb *= (1.0 - noiseAmount + noiseAmount * n);',
    '  }',
    '  float brightness = 1.0 - (coord.y / iResolution.y);',
    '  fragColor.x *= 0.1 + brightness * 0.8;',
    '  fragColor.y *= 0.3 + brightness * 0.6;',
    '  fragColor.z *= 0.5 + brightness * 0.5;',
    '  if (saturation != 1.0) {',
    '    float gray = dot(fragColor.rgb, vec3(0.299, 0.587, 0.114));',
    '    fragColor.rgb = mix(vec3(gray), fragColor.rgb, saturation);',
    '  }',
    '  fragColor.rgb *= raysColor;',
    '  fragColor.rgb *= intensity;',
    '  fragColor.a = clamp(max(fragColor.r, max(fragColor.g, fragColor.b)), 0.0, 1.0);',   // 预乘：rgb == a
    '  gl_FragColor = vec4(fragColor.rgb, fragColor.a);',
    '}'
  ].join('\n');

  function hexToRgb(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || '');
    return m ? [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255] : [1, 1, 1];
  }

  // 与组件 getAnchorAndDir 相同；outside=0.2，坐标系为「y 向下」
  function anchorAndDir(origin, w, h) {
    var o = 0.2;
    switch (origin) {
      case 'top-left': return { anchor: [0, -o * h], dir: [0, 1] };
      case 'top-right': return { anchor: [w, -o * h], dir: [0, 1] };
      case 'left': return { anchor: [-o * w, 0.5 * h], dir: [1, 0] };
      case 'right': return { anchor: [(1 + o) * w, 0.5 * h], dir: [-1, 0] };
      case 'bottom-left': return { anchor: [0, (1 + o) * h], dir: [0, -1] };
      case 'bottom-right': return { anchor: [w, (1 + o) * h], dir: [0, -1] };
      default: return { anchor: [0.5 * w, -o * h], dir: [0, 1] };
    }
  }

  SRays.create = function (canvas, opts) {
    if (!canvas) return null;
    var o = opts || {};
    var gl = null;
    try {
      gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: true, depth: false, stencil: false, antialias: false })
        || canvas.getContext('experimental-webgl', { alpha: true, premultipliedAlpha: true, depth: false, stencil: false, antialias: false });
    } catch (e) { gl = null; }
    if (!gl) { canvas.style.display = 'none'; return null; }

    function sh(type, src) {
      var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { return null; }
      return s;
    }
    var vs = sh(gl.VERTEX_SHADER, VERT), fs = sh(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) { canvas.style.display = 'none'; return null; }
    var prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { canvas.style.display = 'none'; return null; }
    gl.useProgram(prog);

    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'position');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    function u(name) { return gl.getUniformLocation(prog, name); }
    var U = {
      iTime: u('iTime'), iResolution: u('iResolution'), rayPos: u('rayPos'), rayDir: u('rayDir'),
      raysColor: u('raysColor'), raysSpeed: u('raysSpeed'), lightSpread: u('lightSpread'), rayLength: u('rayLength'),
      pulsating: u('pulsating'), fadeDistance: u('fadeDistance'), saturation: u('saturation'),
      mousePos: u('mousePos'), mouseInfluence: u('mouseInfluence'), noiseAmount: u('noiseAmount'),
      distortion: u('distortion'), intensity: u('intensity')
    };

    var api = {
      ok: true,
      canvas: canvas,
      origin: o.origin || 'top-left',
      speed: o.speed === undefined ? 1 : o.speed,
      spread: o.spread === undefined ? 0.5 : o.spread,
      length: o.length === undefined ? 3 : o.length,
      intensity: o.intensity === undefined ? 0.55 : o.intensity,
      fade: o.fade === undefined ? 1 : o.fade,
      saturation: o.saturation === undefined ? 1 : o.saturation,
      mouseInfluence: o.mouseInfluence === undefined ? 0.1 : o.mouseInfluence,
      color: hexToRgb(o.color || '#ffffff'),
      dpr: 1, w: 1, h: 1,
      mx: 0.5, my: 0.5, smx: 0.5, smy: 0.5
    };

    api.resize = function (cssW, cssH, dpr) {
      api.dpr = Math.min(dpr || 1, 2);
      var w = Math.max(2, Math.round(cssW * api.dpr)), h = Math.max(2, Math.round(cssH * api.dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      api.w = w; api.h = h;
      var ad = anchorAndDir(api.origin, w, h);
      gl.viewport(0, 0, w, h);
      gl.uniform2f(U.iResolution, w, h);
      gl.uniform2f(U.rayPos, ad.anchor[0], ad.anchor[1]);
      gl.uniform2f(U.rayDir, ad.dir[0], ad.dir[1]);
    };

    api.render = function (t, mouseNx, mouseNy) {
      if (mouseNx !== undefined && mouseNx !== null) { api.mx = mouseNx; api.my = mouseNy; }
      var s = 0.92;                                     // 与组件同：鼠标位置做 0.92 指数平滑
      api.smx = api.smx * s + api.mx * (1 - s);
      api.smy = api.smy * s + api.my * (1 - s);
      gl.useProgram(prog);
      gl.disable(gl.BLEND);
      gl.uniform1f(U.iTime, t);
      gl.uniform3f(U.raysColor, api.color[0], api.color[1], api.color[2]);
      gl.uniform1f(U.raysSpeed, api.speed);
      gl.uniform1f(U.lightSpread, api.spread);
      gl.uniform1f(U.rayLength, api.length);
      gl.uniform1f(U.pulsating, 0);
      gl.uniform1f(U.fadeDistance, api.fade);
      gl.uniform1f(U.saturation, api.saturation);
      gl.uniform2f(U.mousePos, api.smx, api.smy);
      gl.uniform1f(U.mouseInfluence, api.mouseInfluence);
      gl.uniform1f(U.noiseAmount, 0);
      gl.uniform1f(U.distortion, 0);
      gl.uniform1f(U.intensity, api.intensity);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    api.dispose = function () {
      try {
        var ext = gl.getExtension('WEBGL_lose_context');
        if (ext) ext.loseContext();
      } catch (e) { /* ignore */ }
    };

    return api;
  };
})(typeof window !== 'undefined' ? window : this);
