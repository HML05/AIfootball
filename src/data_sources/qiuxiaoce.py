# -*- coding: utf-8 -*-
"""球小策 (qiuxiaoce) 数据源适配器

特点: 按点计费(1元=100点), 30次/分限流, 60秒内同请求不重复扣点
用途: 补 football-data 拿不到的精细化数据 —— xG/技术统计、首发阵容、球员逐场统计、伤停、转会
注意: 本适配器只使用"纯足球数据"接口, 不使用市场参考值/赔率类接口。

Base: https://www.qiuxiaoce.com/wp-json/abv2-creator/v1
认证头: X-API-Key
"""
import json
import os
import time
from datetime import datetime

import requests

from config.settings import settings

SLEEP = 2.1          # 限流: 30次/分钟
COST = {             # 单次点数(用于记账提示)
    "/today/digest": 5, "/fixtures": 2, "/review": 10,
    "/match-pack": 50,
}
STATS_COST = 5       # /fixtures/{id}/stats|events|lineups|players
_CACHE = {}          # (path, params) -> (ts, data)  # 60秒去重窗口


class QiuxiaoceClient:
    def __init__(self, key: str = None, base: str = None):
        self.key = key or settings.QIXIAOCE_API_KEY
        self.base = base or settings.QIXIAOCE_BASE
        if not self.key:
            raise ValueError("未配置 QIXIAOCE_API_KEY")
        self.spent_points = 0

    # ---------- 底层 ----------
    def _get(self, path, params=None, cost=0, retries=3):
        params = params or {}
        ck = (path, tuple(sorted(params.items())))
        now = time.time()
        if ck in _CACHE and now - _CACHE[ck][0] < 60:
            return _CACHE[ck][1]                      # 60秒内同请求: 本地去重, 不扣点
        for i in range(retries):
            try:
                r = requests.get(f"{self.base}{path}",
                                 headers={"X-API-Key": self.key},
                                 params=params, timeout=30)
                if r.status_code == 429:
                    time.sleep(8)
                    continue
                data = r.json()
                if r.status_code == 200 and data.get("success"):
                    self.spent_points += cost
                    _CACHE[ck] = (now, data)
                    time.sleep(SLEEP)
                    return data
                # 403 subscription_required 等
                print(f"  ⚠️ {path} HTTP {r.status_code}: "
                      f"{json.dumps(data, ensure_ascii=False)[:160]}")
                return None
            except Exception as e:
                time.sleep(3)
        return None

    # ---------- 接口 ----------
    def digest(self, date=None):
        """今日赛事总览 (5点)"""
        return self._get("/today/digest", {"date": date} if date else {}, cost=5)

    def fixtures(self, **params):
        """赛程/赛果 (2点): date / from / to / league / season / team / status / round / id"""
        return self._get("/fixtures", params, cost=2)

    def fixture_stats(self, fixture_id):
        """单场技术统计(赛后) (5点): 射门/控球/xG/角球"""
        return self._get(f"/fixtures/{fixture_id}/stats", cost=STATS_COST)

    def fixture_lineups(self, fixture_id):
        """单场阵容 (5点): 阵型/首发/替补"""
        return self._get(f"/fixtures/{fixture_id}/lineups", cost=STATS_COST)

    def fixture_players(self, fixture_id):
        """单场球员统计 (5点): 评分/进球/助攻/传球"""
        return self._get(f"/fixtures/{fixture_id}/players", cost=STATS_COST)

    def fixture_events(self, fixture_id):
        """单场事件流 (5点)"""
        return self._get(f"/fixtures/{fixture_id}/events", cost=STATS_COST)

    def match_pack(self, fixture_id):
        """单场全景包 (50点): 200+维赛前数据/预测首发/伤停/战术"""
        return self._get(f"/match-pack/{fixture_id}", cost=50)

    def teams(self, q):
        """球队检索 (轻量)"""
        return self._get("/teams", {"q": q}, cost=2)

    def team_squad(self, team_id):
        """球队完整阵容 + 球队资料 (轻量)"""
        return self._get(f"/teams/{team_id}/squad", cost=5)

    def players(self, q):
        """球员检索 (轻量)"""
        return self._get("/players", {"q": q}, cost=2)

    def leagues(self, q=None):
        """联赛检索 (轻量)"""
        return self._get("/leagues", {"q": q} if q else {}, cost=2)

    def review(self, days=7):
        """预测复盘聚合 (10点)"""
        return self._get("/review", {"days": days}, cost=10)
