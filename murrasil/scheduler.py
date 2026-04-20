"""
scheduler.py — جدولة المهام الدورية
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import config

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    from fetcher import fetch_rss
    from deduplicator import run_deduplication_pass
    from recommender import update_preference_weights
    from notifier import cleanup_old_notifications

    interval = config.FETCH_INTERVAL_MINUTES

    # ── جلب الأخبار دورياً ──
    scheduler.add_job(
        fetch_rss,
        "interval",
        minutes=interval,
        id="rss_fetch_job",
        replace_existing=True,
    )

    # ── تنظيف الأخبار القديمة ──
    scheduler.add_job(
        _cleanup_old_news,
        "interval",
        hours=config.CLEANUP_INTERVAL_HOURS,
        id="cleanup_job",
        replace_existing=True,
    )

    # ── تحديث أوزان التوصيات ──
    scheduler.add_job(
        update_preference_weights,
        "interval",
        hours=1,
        id="pref_update_job",
        replace_existing=True,
    )

    # ── تمرير كشف التكرار ──
    scheduler.add_job(
        run_deduplication_pass,
        "interval",
        hours=2,
        id="dedup_job",
        replace_existing=True,
    )

    # ── تنظيف الإشعارات القديمة ──
    scheduler.add_job(
        lambda: cleanup_old_notifications(7),
        "interval",
        hours=24,
        id="notif_cleanup_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        f"Scheduler started: fetch every {interval}min, cleanup every {config.CLEANUP_INTERVAL_HOURS}h"
    )


def _cleanup_old_news():
    """Remove news older than MAX_NEWS_AGE_HOURS."""
    from database import get_db_connection

    max_hours = config.MAX_NEWS_AGE_HOURS
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM news WHERE datetime(fetched_at) < datetime('now', ? || ' hours')",
        (f"-{int(max_hours)}",),
    )
    deleted = cursor.rowcount

    # Also clean orphaned cluster entries
    cursor.execute(
        "DELETE FROM news_clusters WHERE news_id NOT IN (SELECT id FROM news)"
    )

    # Clean orphaned interactions
    cursor.execute(
        "DELETE FROM interactions WHERE news_id NOT IN (SELECT id FROM news)"
    )

    conn.commit()
    conn.close()

    if deleted:
        logger.info(
            f"Cleaned up {deleted} old news articles (older than {max_hours}h)."
        )
