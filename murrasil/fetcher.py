"""
fetcher.py — جلب الأخبار من RSS و NewsAPI
يدعم: Batch Processing، استخراج الصور، كشف التكرار، progress callback
"""

import feedparser
import hashlib
import logging
import asyncio
import aiohttp
import re
from datetime import datetime, timezone
from typing import Callable, Optional

from config import config
from database import get_db_connection
from nlp_engine import process_batch
from deduplicator import find_similar_articles, add_to_cluster
from notifier import check_and_notify

logger = logging.getLogger(__name__)


def _extract_image(entry) -> str:
    media = getattr(entry, "media_content", None)
    if media and len(media) > 0:
        return media[0].get("url", "")

    thumb = getattr(entry, "media_thumbnail", None)
    if thumb and len(thumb) > 0:
        return thumb[0].get("url", "")

    enclosures = getattr(entry, "enclosures", [])
    for enc in enclosures:
        if enc.get("type", "").startswith("image"):
            return enc.get("href", enc.get("url", ""))

    summary = getattr(entry, "summary", "") or ""
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if img_match:
        return img_match.group(1)

    return ""


async def fetch_rss(progress_callback: Optional[Callable] = None):
    """Fetch news from all enabled RSS sources with batch AI processing."""
    logger.info("Starting RSS fetch...")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE enabled = 1")
    sources = cursor.fetchall()
    conn.close()

    total_sources = len(sources)
    max_per_source = config.MAX_ARTICLES_PER_SOURCE

    all_entries = []
    all_metas = []

    for source in sources:
        try:
            feed = feedparser.parse(source["url"])
            if not feed.entries:
                if progress_callback:
                    progress_callback(f"⚠️ لا أخبار من {source['name']}")
                else:
                    logger.warning(f"No entries from {source['name']}")
                continue

            source_count = 0
            source_conn = get_db_connection()
            source_cursor = source_conn.cursor()

            for entry in feed.entries:
                if source_count >= max_per_source:
                    break
                link = getattr(entry, "link", "")
                if not link:
                    continue

                article_id = hashlib.md5(link.encode("utf-8")).hexdigest()

                source_cursor.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                if source_cursor.fetchone():
                    continue

                title = getattr(entry, "title", "")
                content = getattr(entry, "summary", getattr(entry, "description", ""))
                published_at = getattr(
                    entry, "published", datetime.now(timezone.utc).isoformat()
                )
                image_url = _extract_image(entry)
                lang = source["lang"] if source["lang"] else "en"

                all_entries.append(
                    {"title": title, "content": content or title, "lang": lang}
                )
                all_metas.append(
                    {
                        "id": article_id,
                        "link": link,
                        "published_at": published_at,
                        "image_url": image_url,
                        "source_name": source["name"],
                        "source_url": source["url"],
                        "lang": lang,
                        "category_hint": source["category_hint"] or "",
                    }
                )
                source_count += 1

            source_conn.close()

            if source_count > 0:
                if progress_callback:
                    progress_callback(f"📥 {source['name']}: {source_count} خبر جديد")
                else:
                    logger.info(f"{source['name']}: {source_count} new articles")

        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ {source['name']}: {str(e)[:50]}")
            else:
                logger.error(f"Error fetching source {source['name']}: {e}")

    newsapi_count = 0
    if config.NEWSAPI_KEY:
        if progress_callback:
            progress_callback("📡 جلب من NewsAPI...")
        try:
            newsapi_entries, newsapi_metas, newsapi_count = await _collect_newsapi(
                progress_callback
            )
            all_entries.extend(newsapi_entries)
            all_metas.extend(newsapi_metas)
            if newsapi_count > 0 and progress_callback:
                progress_callback(f"📥 NewsAPI: {newsapi_count} خبر جديد")
        except Exception as e:
            if progress_callback:
                progress_callback(f"❌ NewsAPI: {str(e)[:50]}")

    total_new = len(all_entries)
    if total_new == 0:
        if progress_callback:
            progress_callback("✅ لا توجد أخبار جديدة")
        return 0

    if progress_callback:
        progress_callback(f"📊 إجمالي: {total_new} خبر جديد من جميع المصادر")

    batch_size = config.BATCH_SIZE
    num_batches = (total_new + batch_size - 1) // batch_size

    if progress_callback:
        progress_callback(
            f"🧠 المرحلة 2: معالجة AI — {num_batches} دفعة (بحجم {batch_size}) بالتوازي..."
        )

    batches = []
    for i in range(0, total_new, batch_size):
        batches.append((all_entries[i : i + batch_size], all_metas[i : i + batch_size]))

    semaphore = asyncio.Semaphore(config.PARALLEL_SOURCES)
    total_stored = 0
    completed_batches = 0

    async def process_one_batch(batch_idx, entries, metas):
        nonlocal total_stored, completed_batches
        async with semaphore:
            cnt = await _process_and_store_batch(entries, metas)
            total_stored += cnt
            completed_batches += 1
            if progress_callback:
                progress_callback(
                    f"✅ دفعة {completed_batches}/{num_batches}: معالجة {cnt} خبر", cnt
                )

    tasks = []
    for idx, (entries, metas) in enumerate(batches):
        tasks.append(asyncio.create_task(process_one_batch(idx, entries, metas)))

    await asyncio.gather(*tasks, return_exceptions=True)

    if progress_callback:
        progress_callback(
            f"🎉 اكتمل! {total_stored} خبر جديد في {completed_batches} دفعة"
        )

    logger.info(f"Fetch completed. Added {total_stored} new articles.")
    return total_stored


async def _process_and_store_batch(entries: list, metas: list) -> int:
    results = await process_batch(entries)
    count = 0
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    for i, ai_data in enumerate(results):
        if not ai_data:
            continue

        meta = metas[i]
        title_ar = ai_data.get("title_ar", entries[i]["title"])
        summary_ar = ai_data.get("summary_ar", "")
        category = ai_data.get("category", meta.get("category_hint", "منوعات"))
        keywords = ai_data.get("keywords", [])
        similarity_hash = ai_data.get("similarity_hash", "")
        is_breaking = ai_data.get("is_breaking", False)

        if is_breaking:
            category = "عاجل"

        cluster_id = find_similar_articles(title_ar, similarity_hash, category)

        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO news
                (id, title_ar, summary_ar, source_name, source_url, original_url,
                 published_at, fetched_at, category, status, cluster_id,
                 original_lang, similarity_hash, image_url, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)
            """,
                (
                    meta["id"],
                    title_ar,
                    summary_ar,
                    meta["source_name"],
                    meta["source_url"],
                    meta["link"],
                    meta["published_at"],
                    now,
                    category,
                    cluster_id,
                    meta["lang"],
                    similarity_hash,
                    meta["image_url"],
                    ",".join(keywords) if keywords else "",
                ),
            )
            conn.commit()

            if cluster_id:
                try:
                    add_to_cluster(cluster_id, meta["id"], 0.8)
                except Exception:
                    pass

            count += 1
            check_and_notify(meta["id"], title_ar, category)

        except Exception as e:
            logger.error(f"Error storing article {meta['id']}: {e}")

    conn.close()
    return count


async def _collect_newsapi(progress_callback=None):
    if not config.NEWSAPI_KEY:
        logger.warning("No NEWSAPI_KEY found, skipping NewsAPI fetch.")
        return [], [], 0

    logger.info("Starting NewsAPI fetch...")
    entries = []
    metas = []
    total_count = 0
    now = datetime.now(timezone.utc).isoformat()

    cat_map = {
        "business": "اقتصاد",
        "entertainment": "فن وترفيه",
        "health": "صحة",
        "science": "علوم",
        "sports": "رياضة",
        "technology": "تكنولوجيا",
    }

    async with aiohttp.ClientSession() as session:
        for cat in config.NEWSAPI_CATEGORIES:
            url = (
                f"https://newsapi.org/v2/top-headlines"
                f"?category={cat}&language=en&pageSize={config.MAX_ARTICLES_PER_SOURCE}"
                f"&apiKey={config.NEWSAPI_KEY}"
            )

            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status != 200:
                        logger.error(f"NewsAPI error for {cat}: {response.status}")
                        continue
                    data = await response.json()
            except Exception as e:
                logger.error(f"NewsAPI connection error for {cat}: {e}")
                continue

            articles = data.get("articles", [])
            if not articles:
                continue

            batch_entries = []
            batch_meta = []

            existing_conn = get_db_connection()
            existing_cursor = existing_conn.cursor()

            for article in articles:
                link = article.get("url", "")
                if not link:
                    continue

                article_id = hashlib.md5(link.encode("utf-8")).hexdigest()

                existing_cursor.execute(
                    "SELECT id FROM news WHERE id = ?", (article_id,)
                )
                if existing_cursor.fetchone():
                    continue

                title = article.get("title", "")
                content = (
                    article.get("description", "") or article.get("content", "") or ""
                )
                published_at = article.get("publishedAt", now)
                source_name = article.get("source", {}).get("name", "NewsAPI")
                image_url = article.get("urlToImage", "")

                batch_entries.append(
                    {"title": title, "content": content or title, "lang": "en"}
                )
                batch_meta.append(
                    {
                        "id": article_id,
                        "link": link,
                        "published_at": published_at,
                        "image_url": image_url,
                        "source_name": source_name,
                        "source_url": "NewsAPI",
                        "lang": "en",
                        "category_hint": cat_map.get(cat, "منوعات"),
                    }
                )

            existing_conn.close()

            if batch_entries:
                count = await _process_and_store_batch(batch_entries, batch_meta)
                total_count += count
                await asyncio.sleep(0.5)

    logger.info(f"NewsAPI fetch completed. Added {total_count} new articles.")
    return entries, metas, total_count
