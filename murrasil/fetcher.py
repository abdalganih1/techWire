"""
fetcher.py — جلب الأخبار من RSS و NewsAPI
يدعم: Batch Processing، استخراج الصور، كشف التكرار
"""

import feedparser
import hashlib
import logging
import asyncio
import aiohttp
import re
from datetime import datetime, timezone

from config import config
from database import get_db_connection
from nlp_engine import process_batch, process_single_article
from deduplicator import find_similar_articles, add_to_cluster
from notifier import check_and_notify

logger = logging.getLogger(__name__)


def _extract_image(entry) -> str:
    """Extract image URL from RSS entry."""
    # media:content
    media = getattr(entry, 'media_content', None)
    if media and len(media) > 0:
        return media[0].get('url', '')

    # media:thumbnail
    thumb = getattr(entry, 'media_thumbnail', None)
    if thumb and len(thumb) > 0:
        return thumb[0].get('url', '')

    # enclosure
    enclosures = getattr(entry, 'enclosures', [])
    for enc in enclosures:
        if enc.get('type', '').startswith('image'):
            return enc.get('href', enc.get('url', ''))

    # Try to find image in summary/content HTML
    summary = getattr(entry, 'summary', '') or ''
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if img_match:
        return img_match.group(1)

    return ''


async def fetch_rss():
    """Fetch news from all enabled RSS sources with batch AI processing."""
    logger.info("Starting RSS fetch...")
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM sources WHERE enabled = 1")
    sources = cursor.fetchall()
    conn.close()

    new_articles_count = 0

    for source in sources:
        try:
            feed = feedparser.parse(source['url'])
            if not feed.entries:
                logger.warning(f"No entries from {source['name']}")
                continue

            # Collect new entries for batch processing
            batch_entries = []
            batch_meta = []
            source_count = 0
            max_per = config.MAX_ARTICLES_PER_SOURCE

            for entry in feed.entries:
                if source_count >= max_per:
                    break
                link = getattr(entry, 'link', '')
                if not link:
                    continue

                article_id = hashlib.md5(link.encode('utf-8')).hexdigest()

                # Check if already exists
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                exists = cursor.fetchone()
                conn.close()

                if exists:
                    continue

                title = getattr(entry, 'title', '')
                content = getattr(entry, 'summary', getattr(entry, 'description', ''))
                published_at = getattr(entry, 'published', datetime.now(timezone.utc).isoformat())
                image_url = _extract_image(entry)
                lang = source['lang'] if source['lang'] else 'en'

                batch_entries.append({
                    "title": title,
                    "content": content or title,
                    "lang": lang
                })
                batch_meta.append({
                    "id": article_id,
                    "link": link,
                    "published_at": published_at,
                    "image_url": image_url,
                    "source_name": source['name'],
                    "source_url": source['url'],
                    "lang": lang,
                    "category_hint": source['category_hint'] or ''
                })
                source_count += 1

                # Process in batches of BATCH_SIZE
                if len(batch_entries) >= config.BATCH_SIZE:
                    count = await _process_and_store_batch(batch_entries, batch_meta)
                    new_articles_count += count
                    batch_entries = []
                    batch_meta = []
                    await asyncio.sleep(1)

            # Process remaining
            if batch_entries:
                count = await _process_and_store_batch(batch_entries, batch_meta)
                new_articles_count += count
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error fetching source {source['name']}: {e}")

    # Fetch from NewsAPI
    newsapi_count = await fetch_newsapi()
    new_articles_count += newsapi_count

    logger.info(f"Fetch completed. Added {new_articles_count} new articles.")
    return new_articles_count


async def _process_and_store_batch(entries: list, metas: list) -> int:
    """Process a batch of articles through NLP and store them."""
    results = await process_batch(entries)
    count = 0
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    for i, ai_data in enumerate(results):
        if not ai_data:
            continue

        meta = metas[i]
        title_ar = ai_data.get('title_ar', entries[i]['title'])
        summary_ar = ai_data.get('summary_ar', '')
        category = ai_data.get('category', meta.get('category_hint', 'منوعات'))
        keywords = ai_data.get('keywords', [])
        similarity_hash = ai_data.get('similarity_hash', '')
        is_breaking = ai_data.get('is_breaking', False)

        if is_breaking:
            category = "عاجل"

        # Check for duplicates (get cluster_id but don't insert into clusters yet)
        cluster_id = find_similar_articles(title_ar, similarity_hash, category)

        try:
            # Insert news FIRST (before any cluster reference)
            cursor.execute('''
                INSERT OR IGNORE INTO news
                (id, title_ar, summary_ar, source_name, source_url, original_url,
                 published_at, fetched_at, category, status, cluster_id,
                 original_lang, similarity_hash, image_url, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)
            ''', (
                meta['id'], title_ar, summary_ar, meta['source_name'],
                meta['source_url'], meta['link'], meta['published_at'],
                now, category, cluster_id, meta['lang'],
                similarity_hash, meta['image_url'],
                ','.join(keywords) if keywords else ''
            ))
            conn.commit()

            # Now add to cluster AFTER news row exists
            if cluster_id:
                try:
                    add_to_cluster(cluster_id, meta['id'], 0.8)
                except Exception:
                    pass  # Non-critical

            count += 1

            # Check for notifications
            check_and_notify(meta['id'], title_ar, category)

        except Exception as e:
            logger.error(f"Error storing article {meta['id']}: {e}")

    conn.close()
    return count


async def fetch_newsapi() -> int:
    """Fetch news from NewsAPI across all configured categories."""
    if not config.NEWSAPI_KEY:
        logger.warning("No NEWSAPI_KEY found, skipping NewsAPI fetch.")
        return 0

    logger.info("Starting NewsAPI fetch...")
    total_count = 0
    now = datetime.now(timezone.utc).isoformat()

    try:
        async with aiohttp.ClientSession() as session:
            for cat in config.NEWSAPI_CATEGORIES:
                url = (
                    f"https://newsapi.org/v2/top-headlines"
                    f"?category={cat}&language=en&pageSize=10"
                    f"&apiKey={config.NEWSAPI_KEY}"
                )

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                        if response.status != 200:
                            logger.error(f"NewsAPI error for {cat}: {response.status}")
                            continue
                        data = await response.json()
                except Exception as e:
                    logger.error(f"NewsAPI connection error for {cat}: {e}")
                    continue

                articles = data.get('articles', [])
                if not articles:
                    continue

                # Map NewsAPI category to our categories
                cat_map = {
                    "business": "اقتصاد",
                    "entertainment": "فن وترفيه",
                    "health": "صحة",
                    "science": "علوم",
                    "sports": "رياضة",
                    "technology": "تكنولوجيا",
                }

                batch_entries = []
                batch_meta = []

                for article in articles:
                    link = article.get('url', '')
                    if not link:
                        continue

                    article_id = hashlib.md5(link.encode('utf-8')).hexdigest()

                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                    exists = cursor.fetchone()
                    conn.close()

                    if exists:
                        continue

                    title = article.get('title', '')
                    content = article.get('description', '') or article.get('content', '') or ''
                    published_at = article.get('publishedAt', now)
                    source_name = article.get('source', {}).get('name', 'NewsAPI')
                    image_url = article.get('urlToImage', '')

                    batch_entries.append({
                        "title": title,
                        "content": content or title,
                        "lang": "en"
                    })
                    batch_meta.append({
                        "id": article_id,
                        "link": link,
                        "published_at": published_at,
                        "image_url": image_url,
                        "source_name": source_name,
                        "source_url": "NewsAPI",
                        "lang": "en",
                        "category_hint": cat_map.get(cat, "منوعات")
                    })

                if batch_entries:
                    count = await _process_and_store_batch(batch_entries, batch_meta)
                    total_count += count
                    await asyncio.sleep(0.5)

    except Exception as e:
        logger.error(f"NewsAPI global error: {e}")

    logger.info(f"NewsAPI fetch completed. Added {total_count} new articles.")
    return total_count
