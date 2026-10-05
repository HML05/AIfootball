"""手机端「确认登录」页面。

PC 上生成二维码 -> 手机扫码打开本页 -> 手机上确认身份 -> PC 轮询拿到会话令牌。

为什么手机上还要输账号密码: 这一版不做短信验证码, 于是「持有手机」本身不能当作
身份凭证 —— 否则任何人捡到手机就能登录你的电脑。所以手机端要么已登录过(本地有
令牌), 一键同意即可; 要么现输一次账号密码。
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#090d0b">
<title>确认登录 · 足球数据分析与 AI 预测系统</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  :root {
    --bg:#090d0b; --panel:#0f1512; --panel-2:#121a16; --line:#1e2a24; --line-2:#27342d;
    --text:#e9f1ec; --text-2:#a0b2a8; --text-3:#7c8e84;
    --accent:#35c98d; --accent-ink:#05130d; --red:#f0685c; --amber:#e6b256;
    --mono:"SF Mono","JetBrains Mono","Source Code Pro",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
    --ease:cubic-bezier(.16,.84,.44,1);
  }
  html, body { margin:0; padding:0; background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
  body::before { content:""; position:fixed; inset:0; pointer-events:none; z-index:0;
    background:
      radial-gradient(680px 380px at 78% -10%, rgba(53,201,141,.08), transparent 60%),
      radial-gradient(520px 340px at -8% 108%, rgba(92,184,240,.05), transparent 62%),
      radial-gradient(rgba(140,175,158,.055) 1px, transparent 1.4px);
    background-size:auto, auto, 22px 22px; background-repeat:no-repeat,no-repeat,repeat; }
  .wrap { position:relative; z-index:1; max-width:520px; margin:0 auto; padding:22px 18px 40px; }
  .brand { display:flex; align-items:center; gap:10px; padding-bottom:16px;
    border-bottom:1px solid var(--line); }
  .brand-mark { width:34px; height:34px; border-radius:10px; background:var(--accent);
    color:var(--accent-ink); display:flex; align-items:center; justify-content:center;
    font-weight:800; font-size:18px; flex:none; }
  .brand-t { font-size:15px; font-weight:700; letter-spacing:.01em; }
  .brand-s { font-size:10px; letter-spacing:.2em; color:var(--text-3); text-transform:uppercase; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:20px 18px; margin-top:18px; position:relative; overflow:hidden; }
  .card::before { content:""; position:absolute; left:0; right:0; top:0; height:1px;
    background:linear-gradient(90deg, var(--accent) 0%, rgba(53,201,141,0) 64%); opacity:.6; }
  h1 { font-size:19px; margin:0 0 6px; font-weight:700; }
  .sub { font-size:12.5px; color:var(--text-2); line-height:1.7; }
  .dev { margin-top:14px; background:var(--panel-2); border:1px solid var(--line);
    border-radius:10px; padding:12px 13px; }
  .dev-label { font-family:var(--mono); font-size:10px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--text-3); }
  .dev-name { font-size:13.5px; margin-top:6px; word-break:break-all; }
  .dev-ip { font-family:var(--mono); font-size:12px; color:var(--text-2); margin-top:4px;
    font-variant-numeric:tabular-nums; }
  label { display:block; font-family:var(--mono); font-size:10px; letter-spacing:.14em;
    text-transform:uppercase; color:var(--text-3); margin:16px 0 7px; }
  input { width:100%; padding:13px 13px; font-size:16px; border-radius:10px;
    background:var(--panel-2); border:1px solid var(--line); color:var(--text);
    transition:border-color .16s var(--ease), box-shadow .16s var(--ease); }
  input:focus { outline:none; border-color:var(--accent);
    box-shadow:0 0 0 3px rgba(53,201,141,.14); }
  button { width:100%; margin-top:18px; padding:14px; font-size:15px; font-weight:700;
    border-radius:10px; border:1px solid var(--accent); background:var(--accent);
    color:var(--accent-ink); transition:background .16s var(--ease); }
  button:active { background:#43db9a; }
  button.ghost { background:transparent; color:var(--text-2); border-color:var(--line-2);
    font-weight:600; margin-top:10px; }
  .hint { font-size:12px; color:var(--text-3); margin-top:14px; line-height:1.7; }
  .msg { margin-top:16px; font-size:13.5px; line-height:1.7; border-radius:10px;
    padding:12px 13px; border:1px solid var(--line); }
  .msg:empty { display:none; }
  .msg.err { border-color:rgba(240,104,92,.4); background:rgba(240,104,92,.08); color:#f7a79e; }
  .msg.ok { border-color:rgba(53,201,141,.4); background:rgba(53,201,141,.10); color:#9beec8; }
  .tick { width:52px; height:52px; border-radius:50%; background:rgba(53,201,141,.12);
    border:1px solid rgba(53,201,141,.4); color:var(--accent); display:flex;
    align-items:center; justify-content:center; font-size:26px; margin:2px 0 14px; }
  .foot { margin-top:20px; font-family:var(--mono); font-size:10.5px; color:var(--text-3);
    letter-spacing:.06em; text-align:center; }
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">
    <div class="brand-mark">⚽</div>
    <div>
      <div class="brand-t">足球数据分析与 AI 预测系统</div>
      <div class="brand-s">Confirm Sign-in</div>
    </div>
  </div>

  <div class="card" id="card">
    __BODY__
  </div>

  <div class="foot">登录状态仅保存在这台手机与本机服务器之间</div>
</div>

<script>
const QID = "__QR_ID__", QK = "__SECRET__", STATUS = "__STATUS__";
const API = location.origin;
const $ = (id) => document.getElementById(id);

function el(tag, cls, html) {
  const d = document.createElement(tag);
  if (cls) d.className = cls;
  if (html !== undefined) d.innerHTML = html;
  return d;
}

async function post(path, body) {
  const r = await fetch(API + path, {method: "POST",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  let j = {};
  try { j = await r.json(); } catch (e) {}
  return {ok: r.ok, status: r.status, data: j};
}

async function approve(payload) {
  const box = $("msg");
  box.className = "msg";
  box.textContent = "正在确认…";
  const r = await post("/api/auth/qr/approve", Object.assign(
        {qr_id: QID, secret: QK}, payload));
  if (r.ok && r.data && r.data.ok) {
    // 电脑那枚令牌由 PC 侧轮询兑换; 这里存的只是「这台手机」的长效登录态。
    if (r.data.phone_token) { try { localStorage.setItem("fauth", JSON.stringify(
        {token: r.data.phone_token, user: r.data.user})); } catch (e) {} }
    box.className = "msg ok";
    box.textContent = "已确认登录 — 可以回到电脑继续了。";
    document.querySelectorAll("button,input").forEach(b => b.disabled = true);
  } else {
    box.className = "msg err";
    box.textContent = (r.data && r.data.detail) || "确认失败, 请重试。";
  }
}

// 手机上已登录过 -> 一键同意
async function tryExistingSession() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("fauth") || "null"); } catch (e) {}
  if (!saved || !saved.token) return false;
  const r = await fetch(API + "/api/auth/me", {headers: {Authorization: "Bearer " + saved.token}});
  if (!r.ok) { try { localStorage.removeItem("fauth"); } catch (e) {} return false; }
  const me = await r.json();
  const u = (me && me.user) || {};
  const card = $("card");
  card.innerHTML = "";
  card.appendChild(el("h1", null, "确认登录"));
  card.appendChild(el("p", "sub", "这台手机已登录为 <b>" + (u.display_name || u.username || "当前账号") +
      "</b>，同意后电脑将直接进入系统。"));
  const dev = el("div", "dev");
  dev.appendChild(el("div", "dev-label", "正在请求登录的设备"));
  dev.appendChild(el("div", "dev-name", "__PC_UA__"));
  dev.appendChild(el("div", "dev-ip", "__PC_IP__"));
  card.appendChild(dev);
  const b = el("button", null, "同意登录");
  b.id = "oneTap";
  b.onclick = () => approve({token: saved.token});
  card.appendChild(b);
  const g = el("button", "ghost", "换一个账号登录");
  g.onclick = () => location.reload();
  card.appendChild(g);
  card.appendChild(el("div", "msg", ""));
  card.lastChild.id = "msg";
  return true;
}

window.addEventListener("DOMContentLoaded", async () => {
  if (STATUS === "expired") return;           // 服务端已渲染过期提示
  if (STATUS === "confirmed" || STATUS === "consumed") return;
  if (await tryExistingSession()) return;
  const form = $("form");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    approve({username: $("u").value.trim(), password: $("p").value});
  });
});
</script>
</body>
</html>
"""


def render(*, qr_id: str, secret: str, status: str, pc_ua: str = "",
           pc_ip: str = "") -> str:
    """按票据状态渲染手机端页面。"""
    if status == "expired":
        body = (
            '<h1>二维码已过期</h1>'
            '<p class="sub">这个二维码超过有效期了。回到电脑上点击「刷新二维码」，'
            '重新扫一次即可。</p>'
            '<div class="msg err">二维码 {ttl} 秒内有效，过期后需要重新生成。</div>'
        )
    elif status in ("confirmed", "consumed"):
        body = (
            '<div class="tick">✓</div>'
            '<h1>已确认登录</h1>'
            '<p class="sub">电脑端已经登录成功，可以关掉这个页面了。</p>'
            '<div class="msg ok">本次扫码登录已完成。</div>'
        )
    elif status == "scanned":
        body = (
            '<h1>确认登录</h1>'
            '<p class="sub">电脑正在等待你的确认。输入账号密码后点下面的按钮，'
            '电脑就会自动登录。</p>'
            + _device_block(pc_ua, pc_ip) +
            _form_block()
        )
    else:  # pending
        body = (
            '<h1>确认登录</h1>'
            '<p class="sub">你正在用手机确认一台电脑的登录请求。'
            '输入你的账号密码，确认后电脑端会自动登录。</p>'
            + _device_block(pc_ua, pc_ip) +
            _form_block()
        )
    html = (TEMPLATE
            .replace("__BODY__", body)
            .replace("__QR_ID__", qr_id)
            .replace("__SECRET__", secret)
            .replace("__STATUS__", status)
            .replace("__PC_UA__", pc_ua or "未知设备")
            .replace("__PC_IP__", pc_ip or "—")
            .replace("{ttl}", "120"))
    return html


def _device_block(pc_ua: str, pc_ip: str) -> str:
    return (
        '<div class="dev">'
        '<div class="dev-label">正在请求登录的设备</div>'
        f'<div class="dev-name">{pc_ua or "未知设备"}</div>'
        f'<div class="dev-ip">{pc_ip or "—"}</div>'
        '</div>'
    )


def _form_block() -> str:
    return (
        '<form id="form" autocomplete="on">'
        '<label for="u">账号</label>'
        '<input id="u" name="username" type="text" autocomplete="username" '
        'placeholder="请输入账号" required>'
        '<label for="p">密码</label>'
        '<input id="p" name="password" type="password" autocomplete="current-password" '
        'placeholder="请输入密码" required>'
        '<button type="submit">同意登录</button>'
        '</form>'
        '<div class="msg" id="msg">确认后电脑端会自动进入系统。</div>'
    )
