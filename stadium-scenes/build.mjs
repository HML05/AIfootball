/* ============================================================================
 * build.mjs — 把 src/ 与球场照片打包成四个"单文件、可直接双击打开"的场景页
 *   node build.mjs              生成 day/dusk/night/rain.html + index.html
 *   输出自包含（照片 base64 内联），file:// 直接打开即可，无需服务器
 * ==========================================================================*/
import { readFile, writeFile, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const ROOT = import.meta.dirname;
const SRC = path.join(ROOT, 'src');

/* 四个场景的元信息（与 src/scenes.js 中的 profile 一一对应）
 * img  : 该场景用的底板（默认黄昏原片；白天用从新图抽出来的"无云底板"）
 * tile : 实拍云层贴图（只有用实拍云层的场景才给） */
const META = [
  { id: 'day', name: '白天 · 阳光充足', short: '白天', accent: '#7ec8ff',
    img: 'assets/stadium-rays.jpg', tile: null,
    tagline: '原片直出，亮度与画面完全一致 · 云静止不动 · 光线随鼠标轻微晃动' },
  { id: 'dusk', name: '黄昏 · 落日余晖', short: '黄昏', accent: '#ff9a5c',
    tagline: '与白天同一套光照逻辑 · 换成黄昏色调渲染 · 余晖随云层忽明忽暗' },
  { id: 'night', name: '黑夜 · 灯火通明', short: '黑夜', accent: '#ffd479',
    tagline: '球场灯全开（光锥 + 草地光池）· 城市高楼全部亮灯 · 云后透着灯火' },
  { id: 'rain', name: '雨天 · 乌云细雨', short: '雨天', accent: '#9fc0d8',
    tagline: '乌云压顶天色昏暗 · 真实雨丝与草坪溅落 · 玻璃上大小不一的雨滴滑落' }
];

const read = (p) => readFile(p, 'utf8');
const [css, util, scenes, weather, rays, engine, boot] = await Promise.all([
  read(path.join(SRC, 'shell.css')),
  read(path.join(SRC, 'util.js')),
  read(path.join(SRC, 'scenes.js')),
  read(path.join(SRC, 'weather.js')),
  read(path.join(SRC, 'rays.js')),
  read(path.join(SRC, 'engine.js')),
  read(path.join(SRC, 'boot.js'))
]);

const jpg = await readFile(path.join(ROOT, 'assets', 'stadium.jpg'));
const dataUri = 'data:image/jpeg;base64,' + jpg.toString('base64');

/* 按场景取素材（缓存，避免同一张图重复读） */
const assetCache = new Map();
async function assetUri(rel) {
  if (!rel) return null;
  if (!assetCache.has(rel)) {
    const buf = await readFile(path.join(ROOT, rel));
    const mime = rel.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';
    assetCache.set(rel, 'data:' + mime + ';base64,' + buf.toString('base64'));
  }
  return assetCache.get(rel);
}

const scenesJson = JSON.stringify(META.map((m, i) => ({
  id: m.id, name: m.name, short: m.short, accent: m.accent,
  file: m.id + '.html', idx: i + 1
})));

const extraControls = {
  rain: `
    <div class="vsep"></div>
    <div class="ctl"><label>雨量</label><input data-ctl="rain" type="range" min="0" max="1.4" step="0.05" value="1"><output></output></div>
    <div class="ctl"><label>玻璃雨滴</label><input data-ctl="glass" type="range" min="0" max="1.5" step="0.05" value="1"><output></output></div>`
};

async function page(meta, idx) {
  const tabs = META.map((m) => `    <a href="${m.id}.html" data-scene="${m.id}">${m.short}</a>`).join('\n');
  const src = await assetUri(meta.img || 'assets/stadium.jpg');
  const tile = await assetUri(meta.tile);
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${meta.name} · 球场四景</title>
<style>
${css}
</style>
</head>
<body>
<canvas id="stage"></canvas>
<canvas id="rays"></canvas>
<canvas id="fx"></canvas>

<!-- 面板全部去掉：只剩画面本身。出错时 #err 才会自动显形（兜底，正常时不可见） -->
<div id="err" class="hud"></div>

<script>
window.__SCENE_ID__ = ${JSON.stringify(meta.id)};
window.__SCENES__ = ${scenesJson};
window.__STADIUM_SRC__ = ${JSON.stringify(src)};
window.__CLOUD_TILE__ = ${JSON.stringify(tile)};
</script>
<script>
${util}
</script>
<script>
${scenes}
</script>
<script>
${weather}
</script>
<script>
${rays}
</script>
<script>
${engine}
</script>
<script>
${boot}
</script>
</body>
</html>
`;
}

for (let i = 0; i < META.length; i++) {
  const meta = META[i];
  const html = await page(meta, i + 1);
  await writeFile(path.join(ROOT, meta.id + '.html'), html, 'utf8');
  console.log('✔ ' + meta.id + '.html  ' + (html.length / 1024).toFixed(0) + ' KB');
}

/* ---------------- index.html：四景入口（有截图就放预览） ---------------- */
/* 优先用 shots/thumbs/<id>.jpg（640 宽缩略图，tools/thumbs.py 生成），避免整页被 4 张全尺寸 PNG 撑到几 MB */
async function thumb(id) {
  const j = path.join(ROOT, 'shots', 'thumbs', id + '.jpg');
  if (existsSync(j)) {
    const buf = await readFile(j);
    return 'data:image/jpeg;base64,' + buf.toString('base64');
  }
  const p = path.join(ROOT, 'shots', id + '.png');
  if (!existsSync(p)) return null;
  const buf = await readFile(p);
  return 'data:image/png;base64,' + buf.toString('base64');
}

const cards = [];
for (const m of META) {
  const t = await thumb(m.id);
  cards.push(`  <a class="card" href="${m.id}.html" style="--accent:${m.accent}">
    <div class="shot">${t ? `<img src="${t}" alt="${m.name}">` : '<span>运行 build 前的预览</span>'}</div>
    <div class="meta"><div class="k">场景 ${m.id.toUpperCase()}</div><h2>${m.name}</h2><p>${m.tagline}</p></div>
  </a>`);
}

const index = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>球场四景 · 场景动画</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 700px at 12% -10%,#16233a,#070a11 60%);color:#eaf2ff;
 font-family:-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",system-ui,sans-serif;padding:44px 34px 60px}
header{max-width:1240px;margin:0 auto 26px}
header .k{font-size:11px;letter-spacing:.22em;color:#7ec8ff;text-transform:uppercase}
header h1{margin:8px 0 8px;font-size:28px;letter-spacing:.02em}
header p{margin:0;color:rgba(226,238,255,.62);font-size:13.5px;line-height:1.7;max-width:820px}
.grid{max-width:1240px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}
.card{display:block;text-decoration:none;color:inherit;border-radius:16px;overflow:hidden;
 background:linear-gradient(165deg,rgba(20,28,44,.9),rgba(12,16,26,.82));
 border:1px solid rgba(255,255,255,.10);transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease}
.card:hover{transform:translateY(-4px);border-color:var(--accent);box-shadow:0 18px 44px -18px var(--accent)}
.shot{aspect-ratio:16/10;background:#0b1220;display:flex;align-items:center;justify-content:center;color:rgba(226,238,255,.35);font-size:12px}
.shot img{width:100%;height:100%;object-fit:cover;display:block}
.meta{padding:14px 16px 17px}
.meta .k{font-size:10.5px;letter-spacing:.2em;color:var(--accent)}
.meta h2{margin:6px 0 5px;font-size:16.5px}
.meta p{margin:0;font-size:12.5px;line-height:1.6;color:rgba(226,238,255,.6)}
footer{max-width:1240px;margin:26px auto 0;color:rgba(226,238,255,.42);font-size:12px;line-height:1.8}
code{color:#9fc0d8}
</style>
</head>
<body>
<header>
  <div class="k">Stadium Scenes · 基于同一张球场实拍</div>
  <h1>球场四景 · 可切换场景动画</h1>
  <p>四个场景各自独立成页（<code>day.html</code> / <code>dusk.html</code> / <code>night.html</code> / <code>rain.html</code>），
  直接双击即可运行，无需服务器。四页的云层都会自然飘动；右上角可在四景之间来回切换。</p>
</header>
<div class="grid">
${cards.join('\n')}
</div>
<footer>键盘：空格 暂停 / 继续 · 1~4 切换场景 · H 隐藏界面　｜　链接参数：<code>?t=12</code> 定格某一秒 · <code>?speed=0.5</code> 云速 · <code>?rain=0.6</code> 雨量 · <code>?glass=0</code> 关闭玻璃雨滴 · <code>?fx=0</code> 关闭暗角颗粒</footer>
</body>
</html>
`;
await writeFile(path.join(ROOT, 'index.html'), index, 'utf8');
console.log('✔ index.html  ' + (index.length / 1024).toFixed(0) + ' KB');
