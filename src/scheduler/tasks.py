# -*- coding: utf-8 -*-
"""定时任务 - 数据更新、比分轮询、模型重训练
使用 APScheduler 后台调度

数据源: Football-Data.org (免费 100次/天)
  - 每日 03:00  同步未来 7 天赛程        (~1 次请求)
  - 比赛日每5分钟 轮询当天比分            (无比赛日自动跳过, 额度内)
  - 每周一       重算统计(占位)
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from pathlib import Path
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

BASE = Path(__file__).parent.parent
DB_PATH = BASE / "data" / "database" / "football.db"


def _has_today_or_live() -> bool:
    """是否有今天的比赛或进行中的比赛(决定是否值得轮询, 省配额)"""
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        today = datetime.now().date().isoformat()
        n = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE status IN ('1H','2H','HT') "
            "OR date(date) = ?", (today,)).fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def sync_fixtures(days: int = 7):
    """每日同步未来赛程 (+ 回填赛果 + 生成新预测)"""
    try:
        from src.data_sources.football_data_api import import_matches
        info = import_matches(days=days)
        logger.info(f"赛程同步完成: 返回{info['fetched']} 新增{info['inserted']} 更新{info['updated']}")
        backfill_predictions()
        generate_predictions()
    except Exception as e:
        logger.error(f"赛程同步失败: {e}")


def generate_predictions(days: int = 7):
    """为未来比赛生成预测(当前为 v2+v7 集成模型)"""
    try:
        from src.prediction.prediction_service import predict_upcoming
        info = predict_upcoming(days=days)
        logger.info(f"预测生成: {info.get('predicted')}/{info.get('matches')} 场 "
                    f"(模型 {info.get('model')})")
        return info
    except Exception as e:
        logger.error(f"预测生成失败: {e}")
        return {"error": str(e)}


def backfill_predictions():
    """把已完赛比赛的实际赛果回填到 predictions (预测复盘闭环)"""
    try:
        from src.prediction.prediction_service import backfill_results
        info = backfill_results()
        if info["backfilled"]:
            logger.info(f"预测赛果回填: {info['backfilled']} 条")
    except Exception as e:
        logger.error(f"预测回填失败: {e}")


def poll_live_scores():
    """比赛日轮询当天比分; 无比赛日则跳过(不消耗额度)"""
    if not _has_today_or_live():
        logger.debug("当前无比赛, 跳过比分轮询")
        return
    try:
        from src.data_sources.football_data_api import import_matches
        today = datetime.now().date()
        info = import_matches(days=1, date_from=today)
        logger.info(f"比分轮询完成: 新增{info['inserted']} 更新{info['updated']}")
        backfill_predictions()
    except Exception as e:
        logger.error(f"比分轮询失败: {e}")


def update_weekly_stats():
    """每周一重算统计(占位: 后续可加 Elo 重算/模型重训)"""
    logger.info("每周统计更新(占位): 数据库统计刷新")


def update_transfers():
    """转会数据(当前无来源, 仅记录)"""
    logger.info("转会更新(占位): 无数据源, 跳过")


def start_scheduler() -> BackgroundScheduler:
    """启动定时任务调度器"""
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    scheduler.add_job(
        sync_fixtures,
        trigger=CronTrigger(hour=3, minute=0, timezone="Asia/Shanghai"),
        id="daily_fixtures", replace_existing=True, misfire_grace_time=900,
        kwargs={"days": 7},
    )
    scheduler.add_job(
        generate_predictions,
        trigger=CronTrigger(hour=3, minute=30, timezone="Asia/Shanghai"),
        id="daily_predict", replace_existing=True, misfire_grace_time=900,
        kwargs={"days": 7},
    )
    scheduler.add_job(
        poll_live_scores,
        trigger=IntervalTrigger(minutes=5),
        id="live_poll", replace_existing=True, misfire_grace_time=300,
    )
    scheduler.add_job(
        update_weekly_stats,
        trigger=CronTrigger(day_of_week="mon", hour=4, minute=0, timezone="Asia/Shanghai"),
        id="weekly_stats", replace_existing=True,
    )
    scheduler.add_job(
        update_transfers,
        trigger=CronTrigger(hour=5, minute=0, timezone="Asia/Shanghai"),
        id="transfer_update", replace_existing=True,
    )

    logger.info("定时任务调度器已启动")
    return scheduler


def stop_scheduler(scheduler: Optional[BackgroundScheduler]):
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已停止")
