# -*- coding: utf-8 -*-
"""把 app.py / admin.py 里的 DASH.dashboard(...) 调用整段换成 HERO.render(...) 复刻层。

用行范围替换而不是 edit 文本匹配: 那一整段有 60 行, 逐字抄进 old_string 太容易错。
"""
import io
import re
import sys

NEW_APP = '''            HERO.render(
                kpis=[
                    {"tag": t("比赛场次"), "num": f"{n_match:,}",
                     "trend": f"↑ {t('本月新增')} {_n_new_month:,}"},
                    {"tag": t("已完赛"), "num": f"{n_ft:,}",
                     "trend": f"↑ {t('近 30 天')} {_n_ft30:,}"},
                    {"tag": t("已生成预测"), "num": f"{n_pred:,}",
                     "trend": f"↑ {t('覆盖')} {_pct_pred:.1f}% {t('赛事')}"},
                    {"tag": t("球员 / 球队"), "num": f"{n_player:,}", "plus": True,
                     "trend": f"↑ {t('含身价')} {n_mv:,} · {t('球队')} {n_team}"},
                ],
                stage="/app/static/hero_stadium.jpg",
                focus={
                    "title": f"{t('焦点赛事')} · {i18n_s(_frow['home'])} vs {i18n_s(_frow['away'])}",
                    "odds": [
                        {"k": t("主胜"), "v": f"{_ph:.1f}%", "s": i18n_s(_frow["home"])},
                        {"k": t("平局"), "v": f"{_pd:.1f}%",
                         "s": f"{i18n_s(_frow['lg'])} · {t('模型')} {_frow['model_version']}"},
                        {"k": t("客胜"), "v": f"{_pa:.1f}%", "s": f"{t('首选')} {_pick}"},
                    ],
                    "seg": _maxp,
                    "mini": [
                        {"k": t("主队近 5 场"), "v": f"{_feat.get('v2_home_points_5', 0):.1f} {t('分')}"},
                        {"k": t("客队近 5 场"), "v": f"{_feat.get('v2_away_points_5', 0):.1f} {t('分')}"},
                        {"k": t("主队 Elo"), "v": f"{_feat.get('v2_home_elo', 0):.0f}"},
                        {"k": t("客队 Elo"), "v": f"{_feat.get('v2_away_elo', 0):.0f}"},
                        {"k": t("比赛日"), "v": str(_frow["d"])},
                    ],
                },
                bars={"rows": [
                    {"label": t("官方 xG 覆盖"), "pct": _pct_xg, "val": f"{_pct_xg:.1f}%"},
                    {"label": t("球员身价覆盖"), "pct": _pct_mv, "val": f"{_pct_mv:.1f}%"},
                    {"label": t("赛事预测覆盖"), "pct": _pct_pred, "val": f"{_pct_pred:.1f}%"},
                    {"label": t("位置数据覆盖"), "pct": _pct_pos, "val": f"{_pct_pos:.1f}%"},
                ]},
                side={
                    "slim": {"icon": "i-db", "label": t("未来赛程"),
                             "val": f"{_n_ns:,} {t('场')}", "pct": _pct_ns},
                    "stats": [
                        {"icon": "i-doc", "pct": f"{_pct_xg:.1f}"},
                        {"icon": "i-chart", "pct": f"{_pct_mv:.1f}"},
                        {"icon": "i-clock", "pct": f"{_pct_pred:.1f}"},
                        {"icon": "i-player", "pct": f"{_pct_pos:.1f}"},
                    ],
                    "todo": {
                        "title": t("数据完善度"), "link": t("质量与资产"),
                        "rows": [{"tone": ("g" if it.get("tone") in ("ok", "info") else "y"),
                                  "text": f"{it.get('title', '')} · {it.get('value', '')}"}
                                 for it in _notices],
                    },
                },
                foot=(f"{t('数据更新时间')} · {last_day} · {t('数据源')} "
                      f"SQLite football.db · 🔗 {n_league} {t('个联赛')} / {n_match:,} {t('场比赛')}"),
                height=790, theme=_theme_key())
'''

NEW_ADMIN = '''            HERO.render(
                kpis=[
                    {"tag": t("比赛数量"), "num": f"{n_match:,}", "trend": f"↑ {t('已完赛')} {n_ft:,}"},
                    {"tag": t("预测记录"), "num": f"{n_pred:,}",
                     "trend": f"↑ {t('覆盖')} {_pct_pred:.1f}% {t('赛事')}"},
                    {"tag": t("球员 / 球队"), "num": f"{n_player:,}", "plus": True,
                     "trend": f"↑ {t('含身价')} {n_mv:,} · {t('球队')} {n_team}"},
                    {"tag": t("数据库大小"), "num": f"{_db_mb:.1f} MB",
                     "trend": f"↑ {_n_tables} {t('张表')} · SQLite football.db"},
                ],
                stage="/app/static/hero_stadium.jpg",
                focus={
                    "title": t("库内赛事分布"),
                    "odds": [
                        {"k": t("联赛"), "v": f"{n_league}", "s": "football-data.org"},
                        {"k": t("比赛"), "v": f"{n_match:,}", "s": "matches"},
                        {"k": t("转会记录"), "v": f"{n_transfer:,}", "s": "Transfermarkt"},
                    ],
                    "seg": _pct_pred,
                    "mini": [
                        {"k": t("球队"), "v": f"{n_team}"},
                        {"k": t("球员"), "v": f"{n_player:,}"},
                        {"k": t("官方 xG"), "v": f"{n_xg:,}"},
                        {"k": t("历史预测"), "v": f"{n_pred:,}"},
                        {"k": t("最新比赛日"), "v": str(last_day)},
                    ],
                },
                bars={"rows": [
                    {"label": t("官方 xG 覆盖"), "pct": _pct_xg, "val": f"{_pct_xg:.1f}%"},
                    {"label": t("球员身价覆盖"), "pct": _pct_mv, "val": f"{_pct_mv:.1f}%"},
                    {"label": t("赛事预测覆盖"), "pct": _pct_pred, "val": f"{_pct_pred:.1f}%"},
                    {"label": t("位置数据覆盖"), "pct": _pct_pos, "val": f"{_pct_pos:.1f}%"},
                ]},
                side={
                    "slim": {"icon": "i-db", "label": t("数据库"), "val": f"{_db_mb:.1f} MB",
                             "pct": 100.0},
                    "stats": [
                        {"icon": "i-doc", "pct": f"{_pct_xg:.1f}"},
                        {"icon": "i-chart", "pct": f"{_pct_mv:.1f}"},
                        {"icon": "i-clock", "pct": f"{_pct_pred:.1f}"},
                        {"icon": "i-player", "pct": f"{_pct_pos:.1f}"},
                    ],
                    "todo": {
                        "title": t("数据完善度"), "link": t("质量与资产"),
                        "rows": [{"tone": ("g" if it.get("tone") in ("ok", "info") else "y"),
                                  "text": f"{it.get('title', '')} · {it.get('value', '')}"}
                                 for it in _notices],
                    },
                },
                foot=(f"{t('数据源')} SQLite · football.db · {_n_tables} {t('张表')} · "
                      f"{n_match:,} {t('场比赛')} · {t('模型文件')} models/"),
                height=790, theme=_theme_key())
'''


def patch(path, new_block, start_pat, end_pat):
    src = io.open(path, encoding="utf-8").read()
    lines = src.split("\n")
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and re.search(start_pat, ln):
            start = i
            continue
        if start is not None and re.search(end_pat, ln):
            end = i
            break
    if start is None or end is None:
        print(f"[skip] {path}: 未找到范围 start={start} end={end}")
        return False
    print(f"[patch] {path}: 替换第 {start + 1}-{end + 1} 行 ({end - start + 1} 行)")
    out = lines[:start] + new_block.rstrip("\n").split("\n") + lines[end + 1:]
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    return True


ok1 = patch(r"D:\AIfootball\frontend\app.py", NEW_APP,
            r"^\s*DASH\.dashboard\(", r"^\s*height=780\)\s*$")
ok2 = patch(r"D:\AIfootball\frontend\admin.py", NEW_ADMIN,
            r"^\s*DASH\.dashboard\(", r"^\s*height=\d+\)\s*$")
sys.exit(0 if (ok1 and ok2) else 1)
