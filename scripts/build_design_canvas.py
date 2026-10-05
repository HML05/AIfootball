# -*- coding: utf-8 -*-
"""构建 Design 画布内的「可交互项目演示」页。

与截图版的区别：本页把**真实数据库数据**内联为 JSON，图表与表格由页面内 JS 现算现画，
因此画布里是一个可点击、可筛选、可排序的系统界面，而不是图片。

用法: python scripts/build_design_canvas.py
输出: design/<sessionId>/index.html  (+ manifest.json / brief.json 元信息)
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "database" / "football.db"
SESSION_ID = "session-44479104-ef22-437f-91d0-bcfe1c8db1c9"
OUTDIR = ROOT / "design" / SESSION_ID

# 与 docs/模型评估报告.md 6.3 节一致（同一批测试比赛的配对检验）
MCNEMAR = [
    ("2024-08-01", "DL-MLP vs XGB-v2", 370, 255, "<0.001", True),
    ("2024-08-01", "DL-GRU vs XGB-v2", 351, 234, "<0.001", True),
    ("2025-02-01", "DL-MLP vs XGB-v2", 429, 227, "<0.001", True),
    ("2025-02-01", "DL-GRU vs XGB-v2", 395, 210, "<0.001", True),
    ("2025-08-01", "DL-MLP vs XGB-v2", 176, 138, "0.037", True),
    ("2025-08-01", "DL-MLP vs XGB-v7", 162, 118, "0.010", True),
    ("2025-08-01", "DL-GRU vs XGB-v2", 156, 129, "0.123", False),
]

RADAR_DIMS = ["进攻", "防守", "压制", "纪律", "身价", "经验", "稳定性"]
RADAR_KEYS = ["s_attack", "s_defense", "s_dominance", "s_discipline",
              "s_value", "s_experience", "s_stability"]


def one(con, sql, args=()):
    return con.execute(sql, args).fetchone()


def build_data() -> dict:
    con = sqlite3.connect(str(DB))
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---------- 概览 KPI ----------
    kpi = {
        "matches": one(con, "SELECT COUNT(*) FROM matches")[0],
        "finished": one(con, "SELECT COUNT(*) FROM matches WHERE status='FT'")[0],
        "leagues": one(con, "SELECT COUNT(*) FROM leagues")[0],
        "teams": one(con, "SELECT COUNT(*) FROM teams")[0],
        "players": one(con, "SELECT COUNT(*) FROM players")[0],
        "xg": one(con, "SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL")[0],
        "transfers": one(con, "SELECT COUNT(*) FROM transfers")[0],
        "injuries": one(con, "SELECT COUNT(*) FROM tm_player_injuries")[0],
        "valuations": one(con, "SELECT COUNT(*) FROM tm_player_market_value")[0],
        "preds": one(con, "SELECT COUNT(*) FROM predictions")[0],
        "predsBacktest": one(con, "SELECT COUNT(*) FROM predictions WHERE is_backtest=1")[0],
        "predHits": one(con, "SELECT SUM(hit) FROM predictions WHERE is_backtest=1")[0] or 0,
    }

    # ---------- 各赛事场次 ----------
    tournaments = [
        {"k": r[0], "v": r[1]}
        for r in con.execute("""
            SELECT l.name, COUNT(*) AS n FROM matches m JOIN leagues l ON l.league_id=m.league_id
            GROUP BY l.name ORDER BY n DESC""")
    ]

    # ---------- 月度分布 ----------
    monthly = [
        {"k": r[0], "v": r[1]}
        for r in con.execute("""
            SELECT substr(date,1,7) AS ym, COUNT(*) FROM matches
            WHERE date IS NOT NULL GROUP BY ym ORDER BY ym""")
    ]

    # ---------- 联赛技术风格 ----------
    league_stats = [
        {"league": r[0], "season": r[1], "matches": r[2], "goals_pg": r[3],
         "xg_pg": r[4], "home": r[5], "draw": r[6], "away": r[7]}
        for r in con.execute("""
            SELECT league, season, matches, goals_pg, xg_pg, home_win_pct, draw_pct, away_win_pct
            FROM league_stats ORDER BY matches DESC""")
    ]

    # ---------- 联赛 / 积分榜 ----------
    leagues = [{"id": r[0], "name": r[1], "season": r[2]}
               for r in con.execute("SELECT league_id, name, season FROM leagues ORDER BY league_id")]
    standings = defaultdict(list)
    for lid, season, rank, tname, p, w, d, l, gf, ga, gd, pts, form in con.execute("""
            SELECT s.league_id, s.season, s.rank, t.name, s.played, s.won, s.draw, s.lost,
                   s.goals_for, s.goals_against, s.goal_diff, s.points, s.form
            FROM standings s JOIN teams t ON t.team_id = s.team_id
            WHERE s.season = (SELECT MAX(season) FROM standings
                              WHERE league_id = s.league_id)
            ORDER BY s.league_id, s.rank"""):
        standings[str(lid)].append([rank, tname, p, w, d, l, gf, ga, gd, pts, form or ""])

    # ---------- 球队雷达（真实 7 维评分） ----------
    team_radar = [
        {"id": r[0], "team": r[1], "league": r[2], "elo": r[3], "matches": r[4],
         "dims": [r[5], r[6], r[7], r[8], r[9], r[10], r[11]],
         "stats": {"goals_pg": r[12], "conceded_pg": r[13], "xg_pg": r[14], "xga_pg": r[15],
                   "ppg": r[16], "cards_pg": r[17], "avg_age": r[18], "squad_value": r[19]}}
        for r in con.execute("""
            SELECT tr.team_id, tr.team, l.name, t.elo_rating, tr.matches,
                   tr.s_attack, tr.s_defense, tr.s_dominance, tr.s_discipline,
                   tr.s_value, tr.s_experience, tr.s_stability,
                   tr.goals_pg, tr.conceded_pg, tr.xg_pg, tr.xga_pg, tr.ppg, tr.cards_pg,
                   tr.avg_age, tr.squad_value
            FROM team_radar tr
            JOIN teams t ON t.team_id = tr.team_id
            LEFT JOIN leagues l ON l.league_id = tr.league_id
            ORDER BY tr.team""")
    ]
    elo_by_league = defaultdict(list)
    for t in team_radar:
        if t["elo"]:
            elo_by_league[t["league"] or "其他"].append({"k": t["team"], "v": round(t["elo"], 1)})
    for v in elo_by_league.values():
        v.sort(key=lambda x: -x["v"])

    # ---------- 球员（真实百分位：同位置组内百分位） ----------
    raw = con.execute("""
        SELECT pr.name, COALESCE(NULLIF(p.name_en,''), NULLIF(pr.name_en,''), pr.name),
               t.name, l.name, pr.pos_group, pr.age, pr.market_value,
               pr.apps, pr.minutes, pr.goals, pr.assists, pr.cards,
               pr.goals_p90, pr.assists_p90, pr.involve_p90, pr.minutes_share, pr.cards_p90
        FROM player_radar pr
        LEFT JOIN players p ON p.player_id = pr.player_id
        LEFT JOIN teams t ON t.team_id = pr.team_id
        LEFT JOIN leagues l ON l.league_id = t.league_id
    """).fetchall()

    buckets = defaultdict(list)
    for i, r in enumerate(raw):
        buckets[r[4]].append(i)

    def pctiles(idx_list, key):
        vals = sorted((raw[i][key] or 0) for i in idx_list)
        n = len(vals)

        def rank(v):
            v = v or 0
            lo = sum(1 for x in vals if x < v)
            hi = sum(1 for x in vals if x <= v)
            return round(100.0 * (lo + hi) / 2 / n) if n else 0
        return rank

    funcs = {k: {pg: pctiles(buckets[pg], k) for pg in buckets} for k in (12, 13, 14, 15, 16)}
    mv_rank = pctiles([i for i in range(len(raw))], 6)  # 身价按全体球员
    cards_fn = funcs[16]

    players = []
    for i, r in enumerate(raw):
        pg = r[4]
        players.append([
            r[0], "" if r[1] == r[0] else (r[1] or ""), r[2] or "", r[3] or "", pg or "",
            int(r[5]) if r[5] else 0,
            round((r[6] or 0) / 10000),                     # 身价(万€)
            int(r[7] or 0), int(r[8] or 0), int(r[9] or 0), int(r[10] or 0), int(r[11] or 0),
            funcs[12][pg](r[12]), funcs[13][pg](r[13]), funcs[14][pg](r[14]),
            funcs[15][pg](r[15]), mv_rank(r[6]), 100 - cards_fn[pg](r[16]),
        ])
    players.sort(key=lambda p: -p[6])

    # ---------- 模型评估 ----------
    model_metrics = [
        {"model": r[0], "acc": r[1], "f1": r[2], "logloss": r[3], "draw_recall": r[4], "n": r[5]}
        for r in con.execute("SELECT model, acc, f1_macro, logloss, draw_recall, test_n "
                             "FROM model_metrics ORDER BY acc DESC")
    ]
    confusion = [[r[0], r[1], r[2]] for r in
                 con.execute("SELECT actual, predicted, count FROM model_confusion")]
    calibration = [[r[0], r[1], r[2], r[3]] for r in
                   con.execute("SELECT outcome, predicted, actual, n FROM model_calibration "
                               "ORDER BY predicted")]
    features = [{"k": f, "v": round(v, 4)} for f, v in con.execute(
        "SELECT feature, importance FROM feature_importance ORDER BY importance DESC LIMIT 15")]

    # ---------- 预测复盘 ----------
    preds = [[r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]] for r in con.execute("""
        SELECT m.date, th.name, ta.name, p.model_version, p.pred_result, p.actual_result,
               p.hit, ROUND(MAX(p.pred_home_win, p.pred_draw, p.pred_away_win)*100, 1)
        FROM predictions p
        JOIN matches m ON m.match_id = p.match_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        ORDER BY m.date DESC LIMIT 40""")]

    con.close()

    dl = json.loads((ROOT / "models" / "dl_robustness.json").read_text(encoding="utf-8"))
    model_files = sorted(
        ({"name": p.name, "mb": round(p.stat().st_size / 1048576, 2)}
         for p in (ROOT / "models").glob("*") if p.is_file()),
        key=lambda x: -x["mb"])

    return {
        "gen": gen,
        "kpi": kpi,
        "tournaments": tournaments,
        "monthly": monthly,
        "leagueStats": league_stats,
        "leagues": leagues,
        "standings": dict(standings),
        "teamRadar": team_radar,
        "radarDims": RADAR_DIMS,
        "eloByLeague": dict(elo_by_league),
        "players": players,
        "modelMetrics": model_metrics,
        "confusion": confusion,
        "calibration": calibration,
        "features": features,
        "preds": preds,
        "dl": {"cutoffs": dl["cutoffs"], "seeds": dl["seeds"], "epochs": dl["epochs"],
               "summary": dl["summary"], "leakage": dl.get("leakage_test")},
        "mcnemar": MCNEMAR,
        "modelFiles": model_files,
    }


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>足球数据分析与 AI 预测系统 · 交互演示</title>
<!-- 兜底令牌：画布以 srcdoc 渲染时，相对路径的 design-tokens.css 可能解析不到，
     故在链接之前先声明同一套令牌值；链接加载成功后由 design-tokens.css 覆盖。 -->
<style>
:root{
  --ipw-color-bg:#07130d; --ipw-color-surface:#0d1b14; --ipw-color-text:#e8f5ec;
  --ipw-color-muted:#8fa79a; --ipw-color-border:#1e3529; --ipw-color-primary:#2ebd85;
  --ipw-color-secondary:#17402f; --ipw-color-accent:#d9a441;
  --ipw-font-display:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  --ipw-font-body:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
  --ipw-content-width:1180px; --ipw-page-padding:40px; --ipw-section-space:64px;
  --ipw-card-bg:#0d1b14; --ipw-card-border:#1e3529; --ipw-card-radius:16px;
  --ipw-card-shadow:0 18px 48px rgb(0 0 0 / 45%);
}
</style>
<link rel="stylesheet" href="design-tokens.css" data-ipw-design-tokens>
<style>
*{box-sizing:border-box}
body{margin:0;background:var(--ipw-color-bg);color:var(--ipw-color-text,var(--ipw-color-text));
  font-family:var(--ipw-font-body);font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:var(--ipw-content-width);margin:0 auto;padding:var(--ipw-page-padding)}
.hero{border:1px solid var(--ipw-color-border);border-radius:var(--ipw-card-radius);
  background:linear-gradient(180deg,#0e2018,#0a1610);padding:28px 32px;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;top:-160px;right:-80px;width:420px;height:420px;
  background:radial-gradient(circle,rgba(46,189,133,.16),transparent 62%);pointer-events:none}
.badge{display:inline-flex;gap:7px;align-items:center;border:1px solid var(--ipw-color-border);
  border-radius:999px;padding:4px 12px;font-size:12px;color:var(--ipw-color-primary);background:rgba(46,189,133,.08)}
h1{font-family:var(--ipw-font-display);font-size:36px;line-height:1.15;margin:16px 0 10px;letter-spacing:-.4px}
.lede{color:var(--ipw-color-muted);max-width:64ch;margin:0}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:24px;
  border:1px solid var(--ipw-color-border);border-radius:12px;overflow:hidden;background:var(--ipw-color-border)}
.kpi{background:var(--ipw-color-surface);padding:13px 15px}
.kpi b{display:block;font-size:22px;font-family:var(--ipw-font-display);color:var(--ipw-color-primary)}
.kpi span{font-size:12px;display:block}
.kpi em{font-size:11.5px;color:var(--ipw-color-muted);font-style:normal}
.kpis.k3{grid-template-columns:repeat(3,1fr)}
nav.tabs{display:flex;gap:6px;margin:26px 0 0;flex-wrap:wrap;border-bottom:1px solid var(--ipw-color-border)}
.tab{padding:9px 16px;border:1px solid transparent;border-bottom:none;background:none;
  color:var(--ipw-color-muted);cursor:pointer;font-size:14px;font-family:inherit;border-radius:10px 10px 0 0}
.tab:hover{color:var(--ipw-color-text)}
.tab.on{color:var(--ipw-color-primary);background:var(--ipw-color-surface);
  border-color:var(--ipw-color-border);box-shadow:inset 0 2px 0 var(--ipw-color-primary)}
.panel{display:none}
.panel.on{display:block}
.sec{display:flex;align-items:center;gap:10px;margin:30px 0 14px;flex-wrap:wrap}
.sec .bar{width:3px;height:16px;background:var(--ipw-color-primary);border-radius:2px}
.sec h2{margin:0;font-size:17px;font-family:var(--ipw-font-display)}
.sec .sub{color:var(--ipw-color-muted);font-size:12px}
.card{border:1px solid var(--ipw-card-border);border-radius:var(--ipw-card-radius);
  background:var(--ipw-card-bg);padding:18px 20px;box-shadow:var(--ipw-card-shadow)}
.card h3{margin:0 0 14px;font-size:14px;font-weight:600}
.card h3 .sub{color:var(--ipw-color-muted);font-weight:400;font-size:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.grid2>.card{min-width:0}
.chart{width:100%;height:auto;display:block}
.ct{fill:var(--ipw-color-muted);font-size:11.5px}
.cv{fill:var(--ipw-color-text);font-size:11.5px}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:12px;color:var(--ipw-color-muted)}
.legend i{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{background:var(--ipw-color-surface);color:var(--ipw-color-muted);font-weight:500;text-align:left;
  padding:8px 10px;border-bottom:1px solid var(--ipw-color-border);cursor:pointer;white-space:nowrap;font-size:12px;user-select:none}
.tbl th.num,.tbl td.num{text-align:right;font-variant-numeric:tabular-nums}
.tbl th.on{color:var(--ipw-color-primary)}
.tbl td{padding:7px 10px;border-bottom:1px solid rgba(30,53,41,.55)}
.tbl tbody tr:hover{background:rgba(46,189,133,.06)}
.tbl tbody tr.sel{background:rgba(46,189,133,.14)}
.scroll{max-height:440px;overflow:auto}
.controls{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:0 0 16px}
label{font-size:12px;color:var(--ipw-color-muted)}
select,input[type=text]{background:var(--ipw-color-surface);color:var(--ipw-color-text);
  border:1px solid var(--ipw-color-border);border-radius:9px;padding:8px 11px;font-family:inherit;font-size:13px}
select:focus,input:focus{outline:2px solid rgba(46,189,133,.45);outline-offset:1px;border-color:var(--ipw-color-primary)}
input[type=text]{min-width:230px}
.note{color:var(--ipw-color-muted);font-size:12px;margin:12px 0 0}
.gold{color:var(--ipw-color-accent)}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;
  border:1px solid var(--ipw-color-border);color:var(--ipw-color-muted);white-space:nowrap}
.pill.ok{color:var(--ipw-color-primary);border-color:rgba(46,189,133,.45);background:rgba(46,189,133,.08)}
.pill.no{color:var(--ipw-color-accent);border-color:rgba(217,164,65,.45);background:rgba(217,164,65,.08)}
.pcard{display:grid;grid-template-columns:200px 1fr;gap:20px}
.pstat{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--ipw-color-border);
  border:1px solid var(--ipw-color-border);border-radius:10px;overflow:hidden}
.pstat div{background:var(--ipw-color-surface);padding:9px 11px}
.pstat b{display:block;font-size:17px}
.pstat span{font-size:11.5px;color:var(--ipw-color-muted)}
footer{margin:46px 0 6px;color:var(--ipw-color-muted);font-size:12px;
  border-top:1px solid var(--ipw-color-border);padding-top:16px}
@media (max-width:880px){.grid2{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}
  h1{font-size:27px}.pcard{grid-template-columns:1fr}}
</style>
</head>
<body data-ipw-theme-role="page">
<div class="wrap">

  <header class="hero" data-ipw-theme-role="card">
    <span class="badge" id="gen-badge">数据快照</span>
    <h1 data-ipw-theme-role="heading">足球数据分析与 AI 预测系统</h1>
    <p class="lede">基于五大联赛与 Transfermarkt 球员资产的分析与比赛预测平台。本页由<strong>真实数据库数据</strong>驱动，
      图表与表格在浏览器内现算现画：可切页签、排序、筛选、切换联赛与球队。</p>
    <div class="kpis" id="kpis"></div>
  </header>

  <nav class="tabs" id="tabs">
    <button class="tab on" data-tab="overview">概览</button>
    <button class="tab" data-tab="league">联赛数据</button>
    <button class="tab" data-tab="team">球队分析</button>
    <button class="tab" data-tab="player">球员分析</button>
    <button class="tab" data-tab="predict">比赛预测</button>
    <button class="tab" data-tab="model">模型与评估</button>
  </nav>

  <!-- ========== 概览 ========== -->
  <section class="panel on" id="p-overview">
    <div class="sec"><span class="bar"></span><h2>数据资产</h2><span class="sub">各赛事比赛场次 · 比赛时间分布</span></div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card"><h3>各赛事比赛场次</h3>
        <div id="c-tournaments"></div>
        <p class="note">来源：<code>matches</code> 表按 <code>leagues</code> 分组实时计数。</p></div>
      <div class="card" data-ipw-theme-role="card"><h3>比赛时间分布（月）</h3>
        <div id="c-monthly"></div>
        <p class="note">2021-08 起共 <span id="month-n"></span> 个月有比赛记录。</p></div>
    </div>
    <div class="sec"><span class="bar"></span><h2>各赛事技术风格</h2><span class="sub">点击表头排序</span></div>
    <div class="card" data-ipw-theme-role="card"><div id="t-league-stats"></div></div>
  </section>

  <!-- ========== 联赛 ========== -->
  <section class="panel" id="p-league">
    <div class="controls">
      <label for="sel-league">联赛</label><select id="sel-league"></select>
      <span class="pill" id="league-season"></span>
    </div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card">
        <h3>积分榜 <span class="sub">点击表头排序</span></h3>
        <div class="scroll"><div id="t-standings"></div></div></div>
      <div class="card" data-ipw-theme-role="card"><h3>球队 Elo 评级 <span class="sub">前 14 名</span></h3>
        <div id="c-elo"></div>
        <p class="note">来源：<code>teams.elo_rating</code>（历史交锋递推）。</p></div>
    </div>
  </section>

  <!-- ========== 球队 ========== -->
  <section class="panel" id="p-team">
    <div class="controls">
      <label for="sel-team-a">球队 A</label><select id="sel-team-a"></select>
      <label for="sel-team-b">球队 B</label><select id="sel-team-b"></select>
    </div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card">
        <h3>能力雷达 <span class="sub">同联赛内百分位 0–100</span></h3>
        <div id="c-radar"></div></div>
      <div class="card" data-ipw-theme-role="card"><h3>关键指标对比</h3>
        <div id="t-team-cmp"></div></div>
    </div>
    <div class="sec"><span class="bar"></span><h2>七维评分对照</h2><span class="sub">数值来自 <code>team_radar</code> 视图</span></div>
    <div class="card" data-ipw-theme-role="card"><div id="c-team-dims"></div><div id="lg-team-dims"></div></div>
  </section>

  <!-- ========== 球员 ========== -->
  <section class="panel" id="p-player">
    <div class="controls">
      <input type="text" id="q-player" placeholder="搜索球员或球队（中文 / 英文）">
      <label for="sel-pos">位置</label><select id="sel-pos"></select>
      <label for="sel-player-league">联赛</label><select id="sel-player-league"></select>
    </div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card"><h3>能力雷达 <span class="sub">同位置组百分位 0–100</span></h3>
        <div id="c-player"></div></div>
      <div class="card" data-ipw-theme-role="card"><h3 id="p-name">球员档案</h3>
        <div id="p-card"></div>
        <div id="t-player"></div></div>
    </div>
    <div class="sec"><span class="bar"></span><h2>球员列表</h2><span class="sub" id="player-count"></span></div>
    <div class="card" data-ipw-theme-role="card">
      <div class="scroll"><div id="t-players"></div></div>
      <p class="note">点击任意一行查看该球员的档案与雷达。百分位在全部 4,745 名球员内、按位置组计算。</p></div>
  </section>

  <!-- ========== 预测 ========== -->
  <section class="panel" id="p-predict">
    <div class="sec"><span class="bar"></span><h2>严格样本外评估</h2>
      <span class="sub">训练集 &lt; 2025-08-01 · 测试集 1,817 场</span></div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card"><h3>各方案准确率（%）</h3><div id="c-model-acc"></div></div>
      <div class="card" data-ipw-theme-role="card"><h3>LogLoss（越低越好）</h3><div id="c-model-ll"></div></div>
    </div>
    <div class="grid2" style="margin-top:18px">
      <div class="card" data-ipw-theme-role="card"><h3>混淆矩阵 <span class="sub">集成模型 v2+v7</span></h3>
        <div id="c-confusion"></div></div>
      <div class="card" data-ipw-theme-role="card"><h3>概率校准曲线 <span class="sub">越贴近虚线越好</span></h3>
        <div id="c-calibration"></div><div id="lg-calibration"></div></div>
    </div>
    <div class="sec"><span class="bar"></span><h2>可解释性与复盘</h2><span class="sub">特征重要性 · 历史预测命中</span></div>
    <div class="grid2">
      <div class="card" data-ipw-theme-role="card"><h3>特征重要性 Top 15</h3><div id="c-features"></div></div>
      <div class="card" data-ipw-theme-role="card">
        <h3>历史预测复盘 <span class="sub">最近 40 场</span></h3>
        <div class="scroll"><div id="t-preds"></div></div>
        <p class="note">「命中」由赛后回填；<span class="gold">未结算</span>显示为 —。</p></div>
    </div>
  </section>

  <!-- ========== 模型 ========== -->
  <section class="panel" id="p-model">
    <div class="sec"><span class="bar"></span><h2>部署模型评估</h2><span class="sub">严格样本外 · 读 <code>model_metrics</code></span></div>
    <div class="card" data-ipw-theme-role="card"><div class="kpis k3" id="mkpis" style="margin-top:0"></div></div>
    <div class="sec"><span class="bar"></span><h2>深度学习分支 · 稳健性证据</h2>
      <span class="sub">3 个时间切点 × 3 随机种子 · 同一 126 维特征 · 与 XGBoost 同协议</span></div>
    <div class="card" data-ipw-theme-role="card">
      <h3>各方案在三切点上的准确率（%）</h3><div id="c-dl"></div><div id="lg-dl"></div>
      <p class="note">来源：<code>scripts/dl_robustness.py --seeds 3 --epochs 150</code>（实测 92 秒）。</p></div>
    <div class="grid2" style="margin-top:18px">
      <div class="card" data-ipw-theme-role="card"><h3>跨切点均值与极差</h3><div id="c-dl-mean"></div>
        <p class="note">DL 跨切点极差 0.72pp，XGB-v2 达 5.29pp —— 稳定性显著更好。</p></div>
      <div class="card" data-ipw-theme-role="card"><h3>McNemar 配对检验</h3><div id="t-mcnemar"></div>
        <p class="note">9 组比较中 8 组显著；唯一不显著的是最小测试集上 GRU vs v2 —— 样本量不足，如实标注。</p></div>
    </div>
    <div class="grid2" style="margin-top:18px">
      <div class="card" data-ipw-theme-role="card"><h3>数据泄漏检验 <span class="sub">标签置换</span></h3>
        <div id="t-leak"></div>
        <p class="note">打乱训练标签后准确率精确退化到基线、LogLoss 接近随机 —— 特征管线无未来信息泄漏。</p></div>
      <div class="card" data-ipw-theme-role="card"><h3>模型文件</h3>
        <div class="scroll"><div id="t-files"></div></div></div>
    </div>
    <div class="sec"><span class="bar"></span><h2>诚实的限制</h2><span class="sub">必须与结论一起看</span></div>
    <div class="card" data-ipw-theme-role="card">
      <ul class="lims">
        <li>DL <b>放弃平局换准确率</b>：平局召回仅 0.1%–1.7%（XGB-v2 为 3.5%–12.8%），单种子 GRU 一场平局都不预测。</li>
        <li><b>宏平均 F1 并未提升</b>：DL 0.385–0.400 vs XGB-v2 0.399–0.429 —— 是取舍，不是全面更优。</li>
        <li><b>融合无额外收益</b>：集成 XGB-v7+DL-GRU 均值 51.51%，低于纯 DL-MLP 的 52.52%。</li>
        <li><b>量级有限</b>：最优方案也只比「全押主胜」基线高约 8pp；任何「命中率 60%+」的说法都应被质疑。</li>
      </ul>
      <p class="note">完整报告：<code>docs/模型评估报告.md</code> 第六节。</p></div>
  </section>

  <footer>
    足球数据分析与 AI 预测系统 · 交互演示（数据快照 <span id="gen-time"></span>）。
    本页所有数字均由 <code>data/database/football.db</code> 导出，图表与表格在浏览器内实时计算。
    <p class="note">本页是该系统的**完整数据镜像**；本地同时运行着完整的 Streamlit 系统：
      用户端 <code>http://127.0.0.1:8501</code>（8 页）· 管理员后台 <code>http://127.0.0.1:8502</code>（6 页）。
      画布沙箱会拦截画布内的页面跳转，需要操作真实系统时可直接在浏览器打开上述地址。</p>
  </footer>
</div>

<script id="appdata" type="application/json">__DATA__</script>
<script>
/* ================= 基础工具 ================= */
const D = JSON.parse(document.getElementById('appdata').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = v => (v === null || v === undefined || v === '' || isNaN(v)) ? '—' : (+v).toLocaleString('zh-CN');
const n1 = v => (v === null || v === undefined || isNaN(v)) ? '—' : (+v).toFixed(1);
const n2 = v => (v === null || v === undefined || isNaN(v)) ? '—' : (+v).toFixed(2);
const PRI = 'var(--ipw-color-primary)', ACC = 'var(--ipw-color-accent)';
const MUT = 'var(--ipw-color-muted)', BOR = 'var(--ipw-color-border)';
const BLUE = '#5b8def', PURP = '#b26bd8', ORNG = '#e07a5f', TEAL = '#4fb3a5', GREY = '#8fa79a';
const PALETTE = [PRI, BLUE, ACC, PURP, TEAL, ORNG];
const money = w => !w ? '—' : (w >= 10000 ? (w / 10000).toFixed(2) + ' 亿€' : fmt(w) + ' 万€');

/* ================= 图表（纯 SVG 现画） ================= */
function svgWrap(w, h, inner) {
  return '<svg class="chart" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="xMidYMid meet">' + inner + '</svg>';
}
function legendOf(names, colors) {
  return '<div class="legend">' + names.map((n, i) =>
    '<span><i style="background:' + (colors[i] || PALETTE[i % PALETTE.length]) + '"></i>' + esc(n) + '</span>'
  ).join('') + '</div>';
}
/* 横向排序条 */
function hbar(rows, o) {
  o = o || {};
  const W = o.w || 620, rh = o.rowH || 23, gap = o.gap || 7;
  const lw = o.labelW || 104, pr = o.padR || 78;
  const H = rows.length * (rh + gap) + 8, bw = W - lw - pr;
  const max = Math.max.apply(null, rows.map(r => r.v).concat([1]));
  let s = '';
  rows.forEach((r, i) => {
    const y = 4 + i * (rh + gap), w = Math.max(3, (r.v / max) * bw);
    const op = (0.42 + 0.55 * (r.v / max)).toFixed(3);
    s += '<text x="' + (lw - 10) + '" y="' + (y + rh * 0.72) + '" text-anchor="end" class="ct">' + esc(r.k) + '</text>';
    s += '<rect x="' + lw + '" y="' + y + '" width="' + w.toFixed(1) + '" height="' + rh +
         '" rx="5" fill="' + PRI + '" fill-opacity="' + op + '"></rect>';
    s += '<text x="' + (lw + w + 9) + '" y="' + (y + rh * 0.72) + '" class="cv">' +
         (o.fmt ? o.fmt(r.v) : fmt(r.v)) + '</text>';
  });
  return svgWrap(W, H, s);
}
/* 折线 / 面积（x 为数值轴） */
function lineChart(series, o) {
  o = o || {};
  const W = o.w || 620, H = o.h || 300, pad = { l: 52, r: o.padR || 30, t: 14, b: 32 };
  const xr = o.xRange || [0, 1], yr = o.yRange || [0, 1];
  const px = x => pad.l + (x - xr[0]) / (xr[1] - xr[0]) * (W - pad.l - pad.r);
  const py = y => H - pad.b - (y - yr[0]) / (yr[1] - yr[0]) * (H - pad.t - pad.b);
  let s = '';
  const yT = o.yTicks || 5;
  for (let i = 0; i <= yT; i++) {
    const y = yr[0] + (yr[1] - yr[0]) * i / yT;
    s += '<line x1="' + pad.l + '" x2="' + (W - pad.r) + '" y1="' + py(y) + '" y2="' + py(y) +
         '" stroke="' + BOR + '" stroke-dasharray="3 5" opacity=".75"/>';
    s += '<text x="' + (pad.l - 8) + '" y="' + (py(y) + 4) + '" text-anchor="end" class="ct">' +
         (o.yFmt ? o.yFmt(y) : n2(y)) + '</text>';
  }
  const xT = o.xTicks || 5;
  for (let i = 0; i <= xT; i++) {
    const x = xr[0] + (xr[1] - xr[0]) * i / xT;
    s += '<text x="' + px(x) + '" y="' + (H - pad.b + 18) + '" text-anchor="middle" class="ct">' +
         (o.xFmt ? o.xFmt(x) : n2(x)) + '</text>';
  }
  if (o.diagonal) {
    s += '<line x1="' + px(xr[0]) + '" y1="' + py(yr[0]) + '" x2="' + px(xr[1]) + '" y2="' + py(yr[1]) +
         '" stroke="' + MUT + '" stroke-width="1.3" stroke-dasharray="6 5" opacity=".85"/>';
  }
  series.forEach((se, i) => {
    const col = se.color || PALETTE[i % PALETTE.length];
    const pts = se.points.map(p => px(p.x) + ',' + py(p.y)).join(' ');
    if (o.area) {
      const base = yr[0];
      s += '<polygon points="' + px(se.points[0].x) + ',' + py(base) + ' ' + pts + ' ' +
           px(se.points[se.points.length - 1].x) + ',' + py(base) + '" fill="' + col + '" fill-opacity=".12"/>';
    }
    s += '<polyline points="' + pts + '" fill="none" stroke="' + col + '" stroke-width="2" stroke-linejoin="round"/>';
    if (o.dots) s += se.points.map(p => '<circle cx="' + px(p.x) + '" cy="' + py(p.y) + '" r="2.4" fill="' + col + '"/>').join('');
  });
  return svgWrap(W, H, s);
}
/* 雷达 */
function radar(dims, series, o) {
  o = o || {};
  const W = o.w || 480, H = o.h || 380, cx = W / 2, cy = H / 2 + 4, R = o.r || 132;
  const n = dims.length, ang = i => -Math.PI / 2 + i * 2 * Math.PI / n;
  const pt = (i, v) => [cx + Math.cos(ang(i)) * R * v / 100, cy + Math.sin(ang(i)) * R * v / 100];
  let s = '';
  [25, 50, 75, 100].forEach(ring => {
    s += '<polygon points="' + dims.map((_, i) => pt(i, ring).join(',')).join(' ') +
         '" fill="none" stroke="' + BOR + '" opacity="' + (ring === 100 ? '.9' : '.5') + '"/>';
  });
  dims.forEach((d, i) => {
    const p = pt(i, 100);
    s += '<line x1="' + cx + '" y1="' + cy + '" x2="' + p[0] + '" y2="' + p[1] + '" stroke="' + BOR + '" opacity=".55"/>';
    const lx = cx + Math.cos(ang(i)) * (R + 28), ly = cy + Math.sin(ang(i)) * (R + 28);
    const anchor = Math.abs(Math.cos(ang(i))) < 0.25 ? 'middle' : (Math.cos(ang(i)) > 0 ? 'start' : 'end');
    s += '<text x="' + lx + '" y="' + (ly + 4) + '" text-anchor="' + anchor + '" class="ct">' + esc(d) + '</text>';
  });
  series.forEach((se, i) => {
    const col = se.color || PALETTE[i % PALETTE.length];
    const vv = se.values.map(v => Math.max(0, Math.min(100, v)));
    s += '<polygon points="' + vv.map((v, k) => pt(k, v).join(',')).join(' ') + '" fill="' + col +
         '" fill-opacity=".16" stroke="' + col + '" stroke-width="2"/>';
    s += vv.map((v, k) => { const p = pt(k, v); return '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="3" fill="' + col + '"/>'; }).join('');
  });
  return svgWrap(W, H, s);
}
/* 热力图 */
function heatmap(matrix, rows, cols, o) {
  o = o || {};
  const cell = o.cell || 76, gp = 5, lw = 52, th = 24;
  const W = lw + cols.length * (cell + gp), H = th + rows.length * (cell + gp);
  const max = Math.max.apply(null, matrix.reduce((a, r) => a.concat(r), []).concat([1]));
  let s = '';
  cols.forEach((c, j) => s += '<text x="' + (lw + j * (cell + gp) + cell / 2) + '" y="' + (th - 8) +
    '" text-anchor="middle" class="ct">' + esc(c) + '</text>');
  rows.forEach((r, i) => {
    s += '<text x="' + (lw - 10) + '" y="' + (th + i * (cell + gp) + cell / 2 + 4) +
         '" text-anchor="end" class="ct">' + esc(r) + '</text>';
    cols.forEach((c, j) => {
      const v = matrix[i][j] || 0, op = (0.07 + 0.93 * v / max).toFixed(3);
      s += '<rect x="' + (lw + j * (cell + gp)) + '" y="' + (th + i * (cell + gp)) + '" width="' + cell +
           '" height="' + cell + '" rx="8" fill="' + PRI + '" fill-opacity="' + op + '"/>';
      s += '<text x="' + (lw + j * (cell + gp) + cell / 2) + '" y="' + (th + i * (cell + gp) + cell / 2 + 4) +
           '" text-anchor="middle" class="cv">' + fmt(v) + '</text>';
    });
  });
  return svgWrap(W, H, s);
}
/* 分组柱（数值 0–1，显示为 %） */
function groupBars(cats, series, o) {
  o = o || {};
  const W = o.w || 660, H = o.h || 320, pad = { l: 46, r: 12, t: 14, b: 36 };
  const yMax = o.yMax || Math.max.apply(null, series.reduce((a, s) => a.concat(s.values), []).concat([.01])) * 1.06;
  const gw = (W - pad.l - pad.r) / cats.length;
  const bw = Math.min(o.barW || 20, gw / (series.length + 1.2));
  const py = v => H - pad.b - (v / yMax) * (H - pad.t - pad.b);
  let s = '';
  for (let i = 0; i <= 4; i++) {
    const y = yMax * i / 4;
    s += '<line x1="' + pad.l + '" x2="' + (W - pad.r) + '" y1="' + py(y) + '" y2="' + py(y) +
         '" stroke="' + BOR + '" stroke-dasharray="3 5" opacity=".75"/>';
    s += '<text x="' + (pad.l - 8) + '" y="' + (py(y) + 4) + '" text-anchor="end" class="ct">' + (y * 100).toFixed(0) + '</text>';
  }
  cats.forEach((c, i) => {
    const x0 = pad.l + i * gw + gw / 2 - series.length * bw / 2;
    series.forEach((se, j) => {
      const v = se.values[i], col = se.color || PALETTE[j % PALETTE.length];
      s += '<rect x="' + (x0 + j * bw).toFixed(1) + '" y="' + py(v).toFixed(1) + '" width="' + (bw - 2).toFixed(1) +
           '" height="' + Math.max(1, py(0) - py(v)).toFixed(1) + '" rx="3" fill="' + col + '" fill-opacity=".92">' +
           '<title>' + esc(se.name) + ' · ' + esc(c) + ' — ' + (v * 100).toFixed(2) + '%</title></rect>';
    });
    s += '<text x="' + (pad.l + i * gw + gw / 2) + '" y="' + (H - pad.b + 18) + '" text-anchor="middle" class="ct">' +
         esc(c) + '</text>';
  });
  return svgWrap(W, H, s);
}

/* ================= 表格 ================= */
function makeTable(el, cols, rows, o) {
  o = o || {};
  let sk = o.sortK || cols[0].k, dir = o.dir === undefined ? 1 : o.dir, q = '';
  const limit = o.limit || 0;
  function draw() {
    let data = rows;
    if (o.searchable) {
      const s = q.trim().toLowerCase();
      if (s) data = data.filter(r => cols.some(c => String(r[c.k] ?? '').toLowerCase().includes(s)));
    }
    data = data.slice().sort((a, b) => {
      const x = a[sk], y = b[sk];
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir;
      return String(x ?? '').localeCompare(String(y ?? ''), 'zh') * dir;
    });
    const shown = limit ? data.slice(0, limit) : data;
    let h = '<table class="tbl"><thead><tr>';
    cols.forEach(c => {
      h += '<th data-k="' + c.k + '" class="' + (sk === c.k ? 'on ' : '') + (c.num ? 'num' : '') + '">' +
           esc(c.t) + (sk === c.k ? (dir > 0 ? ' ↑' : ' ↓') : '') + '</th>';
    });
    h += '</tr></thead><tbody>';
    shown.forEach((r, i) => {
      h += '<tr data-i="' + rows.indexOf(r) + '" class="' + (o.isSel && o.isSel(r) ? 'sel' : '') + '">';
      cols.forEach(c => { h += '<td class="' + (c.num ? 'num' : '') + '">' + (c.f ? c.f(r[c.k], r) : esc(r[c.k])) + '</td>'; });
      h += '</tr>';
    });
    h += '</tbody></table>';
    el.innerHTML = h + (limit && data.length > limit
      ? '<p class="note">显示前 ' + limit + ' 行，共 ' + fmt(data.length) + ' 行（可用搜索/排序缩小范围）。</p>' : '');
    el.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      if (k === sk) dir = -dir; else { sk = k; dir = 1; }
      draw();
    });
    if (o.onRow) el.querySelectorAll('tbody tr').forEach(tr => tr.onclick = () => {
      o.onRow(rows[+tr.dataset.i]);
      if (o.rerender) draw();
    });
  }
  draw();
  return { draw, setQ: v => { q = v; draw(); }, rows };
}

/* ================= 面板 ================= */
const state = { league: D.leagues[0].id, playerIdx: 0, filterPos: '全部', filterLeague: '全部', q: '' };

function renderOverview() {
  const k = D.kpi;
  $('#gen-badge').textContent = '数据快照 ' + D.gen;
  $('#gen-time').textContent = D.gen;
  $('#month-n').textContent = D.monthly.length;
  $('#kpis').innerHTML = [
    [fmt(k.matches), '比赛场次', '已完赛 ' + fmt(k.finished)],
    [fmt(k.teams), '球队 / 赛事', fmt(k.leagues) + ' 项赛事'],
    [fmt(k.players), '球员', '含身价与赛季数据'],
    [fmt(k.xg), '官方 xG 覆盖', 'Understat'],
    [fmt(k.transfers), '转会记录', 'Transfermarkt'],
    [fmt(k.injuries), '伤病记录', 'Transfermarkt'],
    [fmt(k.valuations), '市值记录', '球员身价曲线'],
    [fmt(k.preds), '历史预测', '样本外 + 复盘'],
  ].map(a => '<div class="kpi"><b>' + a[0] + '</b><span>' + esc(a[1]) + '</span><em>' + esc(a[2]) + '</em></div>').join('');

  $('#c-tournaments').innerHTML = hbar(D.tournaments, { w: 600, labelW: 82, fmt: fmt });
  const mv = D.monthly.map((m, i) => ({ x: i, y: m.v }));
  const ymax = Math.max.apply(null, D.monthly.map(m => m.v));
  $('#c-monthly').innerHTML = lineChart([{ name: '场次', points: mv, color: PRI }], {
    w: 600, h: 300, xRange: [0, D.monthly.length - 1], yRange: [0, ymax * 1.08], area: true,
    xTicks: 4, yTicks: 4, yFmt: v => Math.round(v),
    xFmt: x => { const m = D.monthly[Math.round(x)]; return m ? m.k : ''; }
  });

  makeTable($('#t-league-stats'),
    [{ k: 'league', t: '联赛' }, { k: 'season', t: '赛季' },
     { k: 'matches', t: '场次', num: true, f: fmt },
     { k: 'goals_pg', t: '场均进球', num: true, f: n2 },
     { k: 'xg_pg', t: '场均 xG', num: true, f: n2 },
     { k: 'home', t: '主胜 %', num: true, f: n1 },
     { k: 'draw', t: '平局 %', num: true, f: n1 },
     { k: 'away', t: '客胜 %', num: true, f: n1 }],
    D.leagueStats, { sortK: 'matches', dir: -1 });
}

function renderLeague() {
  const lid = +state.league;
  const lg = D.leagues.find(l => l.id === lid);
  $('#league-season').textContent = '赛季 ' + (lg ? lg.season : '—') + ' · 数据源 Football-Data.org';
  const rows = (D.standings[String(lid)] || []).map(r => ({
    rank: r[0], team: r[1], p: r[2], w: r[3], d: r[4], l: r[5],
    gf: r[6], ga: r[7], gd: r[8], pts: r[9], form: r[10]
  }));
  makeTable($('#t-standings'),
    [{ k: 'rank', t: '#', num: true }, { k: 'team', t: '球队' },
     { k: 'p', t: '赛', num: true }, { k: 'w', t: '胜', num: true }, { k: 'd', t: '平', num: true },
     { k: 'l', t: '负', num: true }, { k: 'gf', t: '进', num: true }, { k: 'ga', t: '失', num: true },
     { k: 'gd', t: '净', num: true }, { k: 'pts', t: '积分', num: true },
     { k: 'form', t: '近况', f: v => esc(String(v || '').split('').join(' ')) }],
    rows, { sortK: 'rank' });
  const elo = (D.eloByLeague[lg ? lg.name : ''] || []).slice(0, 14);
  $('#c-elo').innerHTML = elo.length ? hbar(elo, { w: 560, labelW: 118, fmt: v => v.toFixed(0) })
    : '<p class="note">该联赛暂无 Elo 数据。</p>';
}

function teamById(id) { return D.teamRadar.find(t => t.id === id); }

function renderTeams() {
  const a = teamById(+$('#sel-team-a').value), b = teamById(+$('#sel-team-b').value);
  if (!a || !b) return;
  $('#c-radar').innerHTML = radar(D.radarDims, [
    { name: a.team, values: a.dims, color: PRI },
    { name: b.team, values: b.dims, color: BLUE }
  ], { w: 460, h: 370 }) + legendOf([a.team, b.team], [PRI, BLUE]);

  const cmp = [
    ['Elo 评级', a.elo, b.elo, v => n1(v)],
    ['统计场次', a.matches, b.matches, fmt],
    ['场均进球', a.stats.goals_pg, b.stats.goals_pg, n2],
    ['场均失球', a.stats.conceded_pg, b.stats.conceded_pg, n2],
    ['场均 xG', a.stats.xg_pg, b.stats.xg_pg, n2],
    ['场均 xGA', a.stats.xga_pg, b.stats.xga_pg, n2],
    ['场均积分', a.stats.ppg, b.stats.ppg, n2],
    ['场均黄牌', a.stats.cards_pg, b.stats.cards_pg, n2],
    ['平均年龄', a.stats.avg_age, b.stats.avg_age, n1],
    ['阵容身价', a.stats.squad_value, b.stats.squad_value, v => v ? (v / 1e8).toFixed(2) + ' 亿€' : '—'],
  ];
  const rows = cmp.map((r, i) => ({ i, k: r[0], a: r[1], b: r[2], fmt: r[3] }));
  $('#t-team-cmp').innerHTML = makeTableInline(
    [[a.team, b.team]], rows.map(r => [r.k, r.fmt(r.a), r.fmt(r.b)]));
  $('#c-team-dims').innerHTML = groupBars(D.radarDims, [
    { name: a.team, values: a.dims.map(v => v / 100), color: PRI },
    { name: b.team, values: b.dims.map(v => v / 100), color: BLUE }
  ], { w: 620, h: 300, yMax: 1 }) + legendOf([a.team, b.team], [PRI, BLUE]);
  $('#lg-team-dims').innerHTML = '';
}

function makeTableInline(head, rows) {
  let h = '<table class="tbl"><thead><tr><th>指标</th>';
  head[0].forEach(c => h += '<th class="num">' + esc(c) + '</th>');
  h += '</tr></thead><tbody>';
  rows.forEach(r => {
    h += '<tr><td>' + esc(r[0]) + '</td>';
    for (let i = 1; i < r.length; i++) h += '<td class="num">' + r[i] + '</td>';
    h += '</tr>';
  });
  return h + '</tbody></table>';
}

const P_DIMS = ['进球', '助攻', '参与进球', '出场时间', '身价', '纪律'];
function playerObj(i) {
  const p = D.players[i];
  return { idx: i, name: p[0], en: p[1], team: p[2], league: p[3], pos: p[4], age: p[5],
    value: p[6], apps: p[7], minutes: p[8], goals: p[9], assists: p[10], cards: p[11],
    pr: [p[12], p[13], p[14], p[15], p[16], p[17]] };
}
function selectPlayer(i) {
  state.playerIdx = i;
  const p = playerObj(i);
  $('#p-name').innerHTML = esc(p.name) + ' <span class="sub">' + esc([p.en, p.team, p.league].filter(Boolean).join(' · ')) + '</span>';
  $('#p-card').innerHTML = '<div class="pstat">' +
    [[money(p.value), '市场身价'], [fmt(p.apps), '出场'], [fmt(p.goals), '进球'],
     [fmt(p.assists), '助攻'], [fmt(p.minutes), '出场分钟'], [p.pos + ' · ' + p.age + ' 岁', '位置 / 年龄']]
      .map(a => '<div><b>' + esc(a[0]) + '</b><span>' + esc(a[1]) + '</span></div>').join('') + '</div>';
  $('#c-player').innerHTML = radar(P_DIMS, [{ name: p.name, values: p.pr, color: PRI }], { w: 430, h: 350 });
  $('#t-player').innerHTML = makeTableInline([['百分位']],
    P_DIMS.map((d, k) => [d + (k === 5 ? '（越低越好已反转）' : ''), p.pr[k]]));
  if (window._plist) window._plist.draw();
}
function renderPlayers() {
  $('#sel-pos').innerHTML = ['全部'].concat([...new Set(D.players.map(p => p[4]))].filter(Boolean).sort())
    .map(v => '<option>' + esc(v) + '</option>').join('');
  $('#sel-player-league').innerHTML = ['全部'].concat([...new Set(D.players.map(p => p[3]))].filter(Boolean).sort())
    .map(v => '<option>' + esc(v) + '</option>').join('');
  let list = [];
  function rebuild() {
    const q = state.q.trim().toLowerCase();
    list = D.players.map((p, i) => i).filter(i => {
      const p = D.players[i];
      if (state.filterPos !== '全部' && p[4] !== state.filterPos) return false;
      if (state.filterLeague !== '全部' && p[3] !== state.filterLeague) return false;
      if (q && !(p[0] + ' ' + p[1] + ' ' + p[2]).toLowerCase().includes(q)) return false;
      return true;
    }).map(playerObj);
    $('#player-count').textContent = '共 ' + fmt(list.length) + ' 名球员 · 点击行查看详情';
    window._plist = makeTable($('#t-players'),
      [{ k: 'name', t: '球员' }, { k: 'en', t: '英文名' }, { k: 'team', t: '球队' },
       { k: 'league', t: '联赛' }, { k: 'pos', t: '位置' }, { k: 'age', t: '年龄', num: true },
       { k: 'value', t: '身价', num: true, f: v => money(v) },
       { k: 'apps', t: '出场', num: true }, { k: 'minutes', t: '分钟', num: true },
       { k: 'goals', t: '进球', num: true }, { k: 'assists', t: '助攻', num: true }],
      list, { sortK: 'value', dir: -1, limit: 60, onRow: r => selectPlayer(r.idx), isSel: r => r.idx === state.playerIdx });
  }
  rebuild();
  $('#q-player').addEventListener('input', e => { state.q = e.target.value; rebuild(); });
  $('#sel-pos').addEventListener('change', e => { state.filterPos = e.target.value; rebuild(); });
  $('#sel-player-league').addEventListener('change', e => { state.filterLeague = e.target.value; rebuild(); });
  selectPlayer(0);
}

function renderPredict() {
  $('#c-model-acc').innerHTML = hbar(D.modelMetrics.map(m => ({ k: m.model, v: m.acc })),
    { w: 600, labelW: 148, fmt: v => v.toFixed(2) });
  $('#c-model-ll').innerHTML = hbar(D.modelMetrics.slice().sort((a, b) => a.logloss - b.logloss)
    .map(m => ({ k: m.model, v: m.logloss })), { w: 600, labelW: 148, fmt: v => v.toFixed(4) });

  const order = ['主胜', '平局', '客胜'];
  const mtx = order.map(a => order.map(p => {
    const hit = D.confusion.find(c => c[0] === a && c[1] === p);
    return hit ? hit[2] : 0;
  }));
  $('#c-confusion').innerHTML = heatmap(mtx, order, order, { cell: 78 }) +
    '<p class="note">行 = 实际结果，列 = 模型预测；对角线为命中。</p>';

  const colors = { '主胜': PRI, '客胜': BLUE, '平局': ACC };
  const series = ['主胜', '客胜', '平局'].map(o => ({
    name: o, color: colors[o],
    points: D.calibration.filter(c => c[0] === o).map(c => ({ x: c[1], y: c[2] }))
  }));
  $('#c-calibration').innerHTML = lineChart(series, {
    w: 600, h: 300, xRange: [0, 1], yRange: [0, 1], diagonal: true, xTicks: 5, yTicks: 5, dots: false
  });
  $('#lg-calibration').innerHTML = legendOf(['主胜', '客胜', '平局', '理想校准'],
    [PRI, BLUE, ACC, MUT]);

  $('#c-features').innerHTML = hbar(D.features, { w: 600, labelW: 150, fmt: v => v.toFixed(4) });

  const preds = D.preds.map(r => ({
    date: r[0], home: r[1], away: r[2], model: r[3], pred: r[4],
    actual: r[5], hit: r[6], conf: r[7]
  }));
  makeTable($('#t-preds'),
    [{ k: 'date', t: '日期' }, { k: 'home', t: '主队' }, { k: 'away', t: '客队' },
     { k: 'model', t: '模型' }, { k: 'pred', t: '预测' }, { k: 'actual', t: '实际' },
     { k: 'conf', t: '置信 %', num: true, f: v => n1(v) },
     { k: 'hit', t: '结果', f: v => v === 1 ? '<span class="pill ok">命中</span>'
        : (v === 0 ? '<span class="pill no">未中</span>' : '<span class="pill">—</span>') }],
    preds, { sortK: 'date', dir: -1 });
}

function renderModels() {
  const best = D.modelMetrics[0];
  const back = D.kpi.predsBacktest ? (D.kpi.predHits / D.kpi.predsBacktest * 100) : 0;
  $('#mkpis').innerHTML = [
    [best.model, '最优模型', '按准确率'],
    [n2(best.acc) + '%', '严格样本外准确率', '测试 ' + fmt(best.n) + ' 场 · 基线 44.36%'],
    [best.logloss.toFixed(4), 'LogLoss', '概率校准质量'],
    [best.f1.toFixed(4), '宏平均 F1', '平局召回 ' + n1(best.draw_recall) + '%'],
    [n1(back) + '%', '历史回测命中率', fmt(D.kpi.predsBacktest) + ' 场 · 含训练期重叠，仅作参考'],
    [fmt(D.modelFiles.length), '模型文件', 'v1 / v2 / v7 / 集成 / DL'],
  ].map(a => '<div class="kpi"><b>' + esc(a[0]) + '</b><span>' + esc(a[1]) + '</span><em>' + esc(a[2]) + '</em></div>').join('');

  const names = Object.keys(D.dl.summary);
  const series = names.map((n, i) => ({
    name: n, color: PALETTE[i % PALETTE.length],
    values: D.dl.summary[n].accs
  }));
  $('#c-dl').innerHTML = groupBars(D.dl.cutoffs, series, { w: 640, h: 320 });
  $('#lg-dl').innerHTML = legendOf(names, series.map(s => s.color));

  const mean = names.map((n, i) => ({
    k: n, v: D.dl.summary[n].mean_acc * 100, c: PALETTE[i % PALETTE.length]
  })).sort((a, b) => b.v - a.v);
  $('#c-dl-mean').innerHTML = hbar(mean, { w: 580, labelW: 150, fmt: v => v.toFixed(2) });

  makeTable($('#t-mcnemar'),
    [{ k: 'cutoff', t: '切点' }, { k: 'pair', t: '对比' },
     { k: 'onlyA', t: '仅前者对', num: true }, { k: 'onlyB', t: '仅后者对', num: true },
     { k: 'p', t: 'p 值' },
     { k: 'sig', t: '结论', f: v => v ? '<span class="pill ok">显著</span>' : '<span class="pill no">不显著</span>' }],
    D.mcnemar.map(m => ({ cutoff: m[0], pair: m[1], onlyA: m[2], onlyB: m[3], p: m[4], sig: m[5] })),
    { sortK: 'cutoff' });

  const lk = D.dl.leakage || {};
  const lkRows = Object.keys(lk).map(k => {
    const v = lk[k];
    return { k, v: (typeof v === 'number') ? (Math.abs(v) < 1 ? v.toFixed(4) : fmt(v)) : String(v) };
  });
  $('#t-leak').innerHTML = lkRows.length ? makeTableInline([['标签置换后']], lkRows.map(r => [r.k, r.v]))
    : '<p class="note">未记录泄漏检验结果。</p>';

  makeTable($('#t-files'),
    [{ k: 'name', t: '文件' }, { k: 'mb', t: '大小 (MB)', num: true, f: v => v.toFixed(2) }],
    D.modelFiles, { sortK: 'mb', dir: -1 });
}

/* ================= 启动 ================= */
const RENDER = { overview: renderOverview, league: renderLeague, team: renderTeams,
                 player: renderPlayers, predict: renderPredict, model: renderModels };
const done = {};
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id === 'p-' + name));
  if (!done[name]) { RENDER[name](); done[name] = true; }
}
document.querySelectorAll('.tab').forEach(t => t.onclick = () => showTab(t.dataset.tab));

$('#sel-league').innerHTML = D.leagues.map(l =>
  '<option value="' + l.id + '">' + esc(l.name) + '</option>').join('');
$('#sel-league').value = state.league;
$('#sel-league').onchange = e => { state.league = e.target.value; done.league = false; renderLeague(); done.league = true; };

const sorted = D.teamRadar.slice().sort((a, b) => (b.elo || 0) - (a.elo || 0));
const picks = [sorted[0], sorted[1], sorted.find(t => t.league === sorted[0].league) || sorted[2]];
['sel-team-a', 'sel-team-b'].forEach((id, k) => {
  const el = $('#' + id);
  el.innerHTML = D.teamRadar.map(t => '<option value="' + t.id + '">' + esc(t.team) +
    (t.league ? ' · ' + esc(t.league) : '') + '</option>').join('');
  el.value = picks[k] ? picks[k].id : sorted[0].id;
  el.onchange = () => { renderTeams(); };
});

renderOverview();
done.overview = true;
</script>
</body>
</html>
'''


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = HTML.replace("__DATA__", payload)
    (OUTDIR / "index.html").write_text(html, encoding="utf-8")

    brief = {
        "title": "足球数据分析与 AI 预测系统 · 交互演示",
        "summary": "真实数据库数据驱动的可交互演示：概览 / 联赛 / 球队 / 球员 / 预测 / 模型 六个页签，"
                   "图表与表格在浏览器内实时计算。",
    }
    (OUTDIR / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = OUTDIR / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        m = {}
    m.update({
        "title": brief["title"],
        "description": "真实数据驱动的可交互演示（非截图）：六个页签、图表与表格浏览器内实时计算。",
        "tags": ["football-analytics", "interactive", "dashboard"],
    })
    manifest_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    kb = len(payload.encode("utf-8")) / 1024
    print(f"已生成 {OUTDIR / 'index.html'}")
    print(f"  内联数据 {kb:.0f} KB · 球员 {len(data['players'])} · 球队 {len(data['teamRadar'])} · "
          f"积分榜联赛 {len(data['standings'])}")
    print(f"  泄漏检验字段: {list((data['dl'].get('leakage') or {}).keys())}")


if __name__ == "__main__":
    main()
