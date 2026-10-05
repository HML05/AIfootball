# -*- coding: utf-8 -*-
"""参照稿渲染层: 严格按 `templates/dashboard_ref.html` 输出(用户 m07333 「严格按照这个」)。

为什么用模板文件而不是用 Python 拼 HTML?
    参照稿是一份完整页面(液态玻璃统一配方 --lg-*、固定大外框 .frame、钉死的背景 .stage、
    侧栏静止 + 内容区内部滚动、顶部导航、KPI/焦点/覆盖率/右列/下方四个滚动面板、三主题切换 JS)。
    用 Python 逐条重写一定会走样; 直接把原稿当模板, 复刻阶段就是"一字不改"。

两阶段:
    复刻阶段  render()                  -> 模板原样渲染(参照稿自带示例数据), 先给用户看
    数据阶段  render(data={...})        -> 用 {{key}} 占位符把真数据替换进去(用户确认后再做)
"""
import re
from pathlib import Path

import streamlit.components.v1 as components

TPL = Path(__file__).parent / "templates" / "dashboard_ref.html"

# 三个主题的内部键 -> 参照稿 body class
THEME_CLASS = {"light": "theme-day", "dark": "theme-sunset", "night": "theme-night"}


# 参照稿侧栏菜单 -> 系统真实页面 slug(点一下就切页)
MENU_SLUGS = {
    "首页概览": "home", "联赛数据": "leagues", "球队分析": "teams", "球员分析": "players",
    "比赛详情": "match", "比赛预测": "predict", "AI智能分析": "agent", "实时比分": "live",
    "数据概览": "overview", "数据浏览": "browse", "API接口测试": "api",
    "数据库管理": "database", "数据更新控制": "update", "模型管理": "models",
}

# 注意: 这段脚本是附加层(参照稿本身的 CSS/结构一字未改), 只做三件事:
#   1) 管理员登录时把 6 个后台页面补进侧栏菜单(参照稿只画了 8 个前端页);
#   2) 把侧栏菜单接到系统真实页面(点击 -> 父窗口 ?page=<slug>);
#   3) 给当前页打上 active 高亮。
_ADMIN_ITEMS = [("数据概览", "📋"), ("数据浏览", "🗂️"), ("API接口测试", "🔌"),
                ("数据库管理", "🗄️"), ("数据更新控制", "🔄"), ("模型管理", "🧠")]

_NAV_JS = """
<script>
(function(){
  var MAP = __MAP__, CUR = "__CUR__", ADMIN = __ADMIN__;
  function labelOf(a){
    var c = a.cloneNode(true);
    c.querySelectorAll('.mi,.chev').forEach(function(n){ n.remove(); });
    return (c.textContent || '').replace(/\\s/g, '');
  }
  var menu = document.querySelector('.menu');
  if(ADMIN && menu){
    __ADMIN_ITEMS__.forEach(function(it){
      if([].some.call(menu.querySelectorAll('a'), function(a){ return labelOf(a) === it[0]; })) return;
      var a = document.createElement('a');
      a.innerHTML = '<span class="mi">' + it[1] + '</span>' + it[0] + '<span class="chev">▾</span>';
      menu.appendChild(a);
    });
  }
  document.querySelectorAll('.menu a, .menu-top').forEach(function(a){
    var lab = labelOf(a), slug = MAP[lab];
    if(!slug){ for(var k in MAP){ if(lab.indexOf(k) >= 0){ slug = MAP[k]; break; } } }
    if(slug === CUR){ a.classList.add('active'); } else if(a.classList.contains('active') && slug){ a.classList.remove('active'); }
    if(slug){
      a.style.cursor = 'pointer';
      a.addEventListener('click', function(ev){
        ev.preventDefault();
        try { window.parent.location.href = '?page=' + slug; } catch(e) { location.href = '?page=' + slug; }
      });
    }
  });
})();
</script>
"""

# 数据注入层(附加脚本): 把参照稿里的示例数字换成库里真值。
# 参照稿模板一字不改 —— 用 DOM 补丁的方式改写文本/宽度/圆环, 主题变量与结构保持原样。
_DATA_JS = """
<style>
/* 附加层的少量贴合修正(模板文件未改): 真数据的中文标签比示例长, 让它们不折行 */
.bars .bl{font-size:11.5px;white-space:nowrap}
.bars .bar{flex:1 1 auto;min-width:60px}
.kpi .trend{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .num{white-space:nowrap}
.side-foot{font-size:10.5px;line-height:1.7}
</style>
<script>
(function(){
  var D = __DATA__;
  function q(s, r){ return (r || document).querySelector(s); }
  function qa(s, r){ return [].slice.call((r || document).querySelectorAll(s)); }
  function txt(el, s){ if(el && s !== undefined && s !== null) el.textContent = s; }
  function box(el, pct){ if(!el) return; var i = q('.bar > i', el); if(i) i.style.width = (pct || 0) + '%'; }

  if(D.kpis){
    qa('.kpis .kpi').forEach(function(card, i){
      var k = D.kpis[i]; if(!k) return;
      var tag = q('.tag', card);
      if(tag) tag.innerHTML = '<i></i>' + (k.tag || '');
      txt(q('.num', card), k.num);
      txt(q('.trend', card), k.trend);
      var plus = q('.plus', card);
      if(k.plus && !plus){ var b = document.createElement('button'); b.className = 'plus'; b.textContent = '+'; card.appendChild(b); }
      if(!k.plus && plus) plus.remove();
    });
  }
  if(D.focus){
    var f = q('.focus'); var F = D.focus;
    var h3 = q('h3', f);
    if(h3 && F.title) h3.innerHTML = F.title.replace(/</g,'&lt;') + ' <span class="chev">▾</span>';
    qa('.odd', f).forEach(function(o, i){
      var k = (F.odds || [])[i]; if(!k) return;
      txt(q('.k', o), k.k); txt(q('.v', o), k.v); txt(q('.s', o), k.s);
    });
    var dn = q('.donut', f);
    if(dn && F.ring !== undefined && F.ring !== null){
      dn.style.background = 'conic-gradient(var(--ring2) 0 ' + F.ring + '%, var(--ring1) ' + F.ring + '% 100%)';
    }
    qa('.mini-stats > div', f).forEach(function(d, i){
      var k = (F.mini || [])[i]; if(!k) return;
      txt(q('.k', d), k.k); txt(q('.v', d), k.v);
    });
  }
  if(D.bars){
    qa('.bars .brow').forEach(function(r, i){
      var k = D.bars[i]; if(!k) return;
      var bl = q('.bl', r); if(bl) bl.innerHTML = '<i></i>' + (k.label || '');
      box(r, k.pct); txt(q('.bp', r), (k.pct || 0).toFixed ? k.pct + '%' : k.pct);
    });
  }
  if(D.right){
    var R = D.right;
    if(R.slim){
      var uc = q('.rightcol .user-card');
      txt(q('.lbl', uc), R.slim.label); box(uc, R.slim.pct);
    }
    qa('.rightcol .stat').forEach(function(c, i){
      var k = (R.stats || [])[i]; if(!k) return;
      if(k.icon) txt(q('.sq', c), k.icon);
      txt(q('.pct', c), k.pct);
      box(c, k.pctNum !== undefined ? k.pctNum : parseFloat(k.pct));
    });
    if(R.todo){
      var td = q('.rightcol .todo');
      var h = q('h3', td);
      if(h) h.innerHTML = (R.todo.title || '') + ' <a href="#">' + (R.todo.link || '') + '</a>';
      var ul = q('ul', td);
      if(ul && R.todo.items) ul.innerHTML = R.todo.items.map(function(it){
        return '<li class="' + (it.tone || 'g') + '">' + it.text + '</li>'; }).join('');
    }
  }
  if(D.foot){
    var sf = q('.side-foot');
    if(sf) sf.innerHTML = D.foot.map(function(s){ return s; }).join('<br>');
  }
  // ---- 主区下方(需滚动)的面板 ----
  var rows = qa('.panel-row');
  function panel(idx, sub){
    var pr = rows[idx]; if(!pr) return null;
    return qa('.g.pad', pr)[sub] || null;
  }
  function title(el, s){ var h = q('h3', el); if(h && s) h.innerHTML = s + ' <span class="chev">▾</span>'; }
  var P = D.panels || {};
  if(P.standings){
    var el = panel(0, 0);
    if(el){ title(el, P.standings.title);
      qa('.lb-row', el).forEach(function(r, i){
        var k = P.standings.rows[i]; if(!k) return;
        txt(q('.rk', r), k.rank); txt(q('b', r), k.name);
        box(r, k.pct); txt(q('em', r), k.val);
      });
    }
  }
  if(P.scorers){
    var el2 = panel(0, 1);
    if(el2){ title(el2, P.scorers.title);
      qa('.lb-row', el2).forEach(function(r, i){
        var k = P.scorers.rows[i]; if(!k) return;
        txt(q('.rk', r), k.rank); txt(q('b', r), k.name);
        box(r, k.pct); txt(q('em', r), k.val);
      });
    }
  }
  if(P.recent){
    var el3 = panel(1, 0);
    if(el3){ title(el3, P.recent.title);
      qa('.m-row', el3).forEach(function(r, i){
        var k = P.recent.rows[i]; if(!k) return;
        var ts = qa('.t', r); txt(ts[0], k.home); txt(ts[1], k.away);
        txt(q('.sc', r), k.score);
        var st = q('.st', r); if(st){ st.textContent = k.status; st.className = 'st ' + (k.cls || 'end'); }
      });
    }
  }
  if(P.ai){
    var el4 = panel(1, 1);
    if(el4){ title(el4, P.ai.title);
      var big = q('.ai-big', el4);
      if(big) big.innerHTML = P.ai.big + '<b>' + P.ai.bigPct + '</b>';
      var tags = q('.ai-tags', el4);
      if(tags) tags.innerHTML = (P.ai.tags || []).map(function(t, i){
        return '<span class="' + (i === 0 ? 'hot' : '') + '">' + t + '</span>'; }).join('');
      txt(q('.ai-tip', el4), P.ai.tip);
    }
  }
  if(P.hot){
    var el5 = panel(2, 0);
    if(el5){ title(el5, P.hot.title);
      var g = q('.hot-grid', el5);
      if(g) g.innerHTML = (P.hot.rows || []).map(function(k){
        return '<div class="hot"><div class="hn">⚽ ' + k.name + '</div><div class="hp">' + k.pct +
               '%</div><div class="bar"><i style="width:' + k.pct + '%"></i></div></div>'; }).join('');
    }
  }
})();
</script>
"""

# 交互层(附加脚本): 顶栏三颗胶囊不再是死按钮。
_UX_JS = """
<script>
(function(){
  var U = __USER__;
  function go(url){ try { window.parent.location.href = url; } catch(e) { location.href = url; } }
  var pills = [].slice.call(document.querySelectorAll('.nav-right .pill'));
  function mkPanel(html){
    var p = document.createElement('div');
    p.className = 'ux-pop';
    p.style.cssText = 'position:absolute;z-index:50;min-width:250px;max-width:330px;padding:12px 14px;' +
      'border-radius:18px;background:var(--lg-bg);border:1.5px solid var(--lg-bd);' +
      'backdrop-filter:var(--lg-blur);-webkit-backdrop-filter:var(--lg-blur);' +
      'box-shadow:var(--lg-out),var(--lg-inn);font-size:12.5px;color:var(--sub);line-height:1.75';
    p.innerHTML = html;
    return p;
  }
  function attach(btn, html){
    if(!btn) return;
    btn.addEventListener('click', function(ev){
      ev.preventDefault(); ev.stopPropagation();
      var open = document.querySelector('.ux-pop');
      if(open) open.remove();
      var p = mkPanel(html);
      var r = btn.getBoundingClientRect(), fr = document.querySelector('.frame').getBoundingClientRect();
      p.style.left = Math.max(8, Math.min(r.left - fr.left - 120, fr.width - 340)) + 'px';
      p.style.top = (r.bottom - fr.top + 8) + 'px';
      document.querySelector('.frame').appendChild(p);
      if(!U.guest){
        var out = document.createElement('a');
        out.href = '#'; out.textContent = '退出登录 →';
        out.style.cssText = 'display:inline-block;margin-top:8px;color:var(--acc-s);font-weight:700;text-decoration:none';
        out.addEventListener('click', function(e){ e.preventDefault(); go('?logout=1'); });
        p.appendChild(out);
      }
    });
  }
  document.addEventListener('click', function(){ var p = document.querySelector('.ux-pop'); if(p) p.remove(); });
  attach(pills[0], (U.notices || []).map(function(n){
      return '<div style="display:flex;gap:8px;align-items:flex-start"><span style="width:8px;height:8px;margin-top:6px;border-radius:50%;flex:none;background:' +
        (n.tone === 'warn' ? '#f0a13c' : (n.tone === 'ok' ? '#3ec46d' : '#5a9df8')) + '"></span><span><b style="color:var(--text)">' +
        n.title + '</b> · ' + n.value + '</span></div>';
    }).join('') || '暂无消息');
  attach(pills[1], '<b style="color:var(--text)">' + (U.name || '未登录') + '</b> · ' + (U.role || '') +
      '<br>语言 ' + (U.lang || '中文') + ' · 主题 ' + (U.theme || '日场'));
  if(pills[2]) pills[2].addEventListener('click', function(ev){ ev.preventDefault(); go('?logout=1'); });
})();
</script>
"""



def source() -> str:
    """模板原文(带 mtime 缓存, 便于改模板后自动生效)。"""
    key = ("_ref_tpl",)
    cache = source.__dict__
    try:
        mtime = TPL.stat().st_mtime
    except OSError:
        return ""
    if cache.get(key[0], (None, None))[0] != mtime:
        cache[key[0]] = (mtime, TPL.read_text(encoding="utf-8"))
    return cache[key[0]][1]


def html(*, theme="light", data=None, force_class=None, slug="home", nav=True,
         admin=False, user=None) -> str:
    """模板 + 数据注入层 + 交互层(模板本身一字不改)。"""
    s = source()
    if not s:
        return "<!DOCTYPE html><p style='font:14px sans-serif;padding:20px'>找不到参照稿模板: {}</p>".format(
            TPL)
    if data:
        for k, v in data.items():
            s = s.replace("{{%s}}" % k, str(v))
    cls = force_class or THEME_CLASS.get(theme, "theme-day")
    # 参照稿的 JS 会在加载时按 localStorage 覆盖 class; 复刻阶段先尊重当前主题
    s = re.sub(r'<body class="[^"]*">', '<body class="%s">' % cls, s, count=1)
    s = s.replace("localStorage.getItem('fx-theme')||'theme-day'", "'%s'" % cls)
    tail = ""
    if nav:
        import json as _json
        js = (_NAV_JS.replace("__MAP__", _json.dumps(MENU_SLUGS, ensure_ascii=False))
              .replace("__CUR__", str(slug or ""))
              .replace("__ADMIN__", "true" if admin else "false")
              .replace("__ADMIN_ITEMS__",
                       _json.dumps([[n, i] for n, i in _ADMIN_ITEMS], ensure_ascii=False)))
        tail += js
        ux = _UX_JS.replace("__USER__", _json.dumps(user or {}, ensure_ascii=False))
        tail += ux
    if data is not None:
        import json as _json
        tail += _DATA_JS.replace("__DATA__", _json.dumps(data, ensure_ascii=False))
    if tail:
        s = s.replace("</body>", tail + "</body>")
    return s


def render(*, theme="light", data=None, height=980, scrolling=False, slug="home",
           nav=True, admin=False, user=None) -> None:
    """在 Streamlit 里渲染参照稿。height 保留兼容, 无壳模式的 CSS 会把它拉成 100vh。"""
    import streamlit as st
    with st.container(key="refpage"):        # 供主题 CSS 精确定位: .st-key-refpage
        components.html(html(theme=theme, data=data, slug=slug, nav=nav,
                             admin=admin, user=user),
                        height=int(height), scrolling=scrolling)
