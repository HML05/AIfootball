# -*- coding: utf-8 -*-
"""API-Football 覆盖检查 —— 付费/抓取前先确认"哪些联赛哪些赛季真有数据"

背景: API-Football 在覆盖缺失时返回 200 + 空数组(静默失败), 必须先查 coverage 开关。

用法:
    python scripts/check_af_coverage.py                       # 我们 10 个赛事 × 2021~2025
    python scripts/check_af_coverage.py --seasons 2024,2025    # 指定赛季
    python scripts/check_af_coverage.py --leagues 英超,欧冠      # 指定联赛
输出:
    终端表格 + data/af_coverage.json

请求数: 联赛数 × 赛季数(免费档 100 次/天, 10 联赛 × 5 赛季 = 50 次, 够用)
"""
import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.data_sources.api_football import (AF_LEAGUES, AF_SEASON_CODE,  # noqa: E402
                                           ApiFootballClient, QuotaExceeded)

KEYS = [("fixtures", "events"), ("fixtures", "lineups"),
        ("fixtures", "statistics_fixtures"), ("fixtures", "statistics_players"),
        ("players",), ("injuries",), ("standings",), ("top_scorers",), ("predictions",)]


def flag(coverage: dict, path: tuple) -> str:
    cur = coverage
    for k in path:
        if not isinstance(cur, dict):
            return "-"
        cur = cur.get(k)
    if cur is True:
        return "✅"
    if cur is False:
        return "❌"
    return "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2021,2022,2023,2024,2025")
    ap.add_argument("--leagues", default=",".join(AF_LEAGUES))
    ap.add_argument("--min-interval", type=float, default=None,
                    help="请求间隔秒(免费档 6.0, Pro 档 0.25)")
    args = ap.parse_args()

    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    leagues = [l for l in args.leagues.split(",") if l]

    try:
        cli = ApiFootballClient(min_interval=args.min_interval)
    except ValueError as e:
        print(f"❌ {e}")
        print("   → 免费注册: https://dashboard.api-football.com 然后把 key 写入 .env:")
        print("     API_SPORTS_KEY=你的key")
        return 1

    print("=" * 78)
    print(f"API-Football 覆盖检查 | 模式={cli.mode} | 预算={cli.daily_budget}/天 | "
          f"间隔={cli.min_interval}s")
    print("=" * 78)

    auth_failed = False
    try:
        st = cli.status()
        sub = st.get("subscription", {}) if isinstance(st, dict) else {}
        req = st.get("requests", {}) if isinstance(st, dict) else {}
        print(f"账号: 计划={sub.get('plan')} 到期={sub.get('end')} | "
              f"今日请求={req.get('current')}/{req.get('limit_day')}")
    except Exception as e:
        msg = str(e)
        if any(k in msg for k in ("403", "not subscribed", "token", "key")):
            print(f"❌ 认证失败: {msg}")
            print("\n   → 请在 .env 配置有效的 API_SPORTS_KEY（免费档即可）:")
            print("     https://dashboard.api-football.com 注册 → API key 复制到 .env")
            print("     API_SPORTS_KEY=你的key")
            return 1
        print(f"⚠️  无法读取账号状态({msg})，继续尝试覆盖查询")

    report = {}
    for name in leagues:
        lid = AF_LEAGUES.get(name)
        if not lid:
            continue
        for season in seasons:
            code = AF_SEASON_CODE.get(season, str(season))
            try:
                info = cli.league_coverage(lid, season)
            except QuotaExceeded as e:
                print(f"\n⛔ {e}\n   明天继续, 已查部分已保存。")
                _save(report)
                return 0
            except RuntimeError as e:
                if any(k in str(e) for k in ("403", "not subscribed", "token", "key")):
                    print(f"\n❌ 认证失败, 中止: {e}")
                    _save(report)
                    return 1
                print(f"\n⚠️  {name} {season}: {e}")
                continue
            if not info:
                print(f"\n—  {name:<4} {season}({code}): 无该赛季数据")
                continue
            cov = info.get("coverage", {})
            row = {"league_id": lid, "season": season, "season_code": code,
                   "flags": {"/".join(k): flag(cov, k) for k in KEYS}}
            report[f"{name}_{code}"] = row
            flags = " ".join(f"{'/'.join(k).split('/')[-1]}={flag(cov, k)}" for k in KEYS)
            print(f"\n—  {name:<4} {season}({code}) [{info.get('league', {}).get('name')}]")
            print(f"     {flags}")

    _save(report)
    print("\n" + "=" * 78)
    _summary(report)
    print(f"\n报告已保存: data/af_coverage.json | 本次消耗请求 {cli.used} 次")
    return 0


def _save(report: dict):
    p = BASE / "data" / "af_coverage.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


def _summary(report: dict):
    """汇总: 每类数据有多少个联赛-赛季可用"""
    print("汇总(可用联赛-赛季数):")
    for k in KEYS:
        key = "/".join(k)
        ok = sum(1 for r in report.values() if r["flags"].get(key) == "✅")
        total = len(report)
        print(f"   {'/'.join(k):<28} {ok}/{total}")


if __name__ == "__main__":
    sys.exit(main())
