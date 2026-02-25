from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fetcher import fetch_rss
from config import config
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

def start_scheduler():
    interval = config.FETCH_INTERVAL_MINUTES
    scheduler.add_job(fetch_rss, 'interval', minutes=interval, id='rss_fetch_job')
    scheduler.start()
    logger.info(f"Scheduler started with interval: {interval} minutes.")
