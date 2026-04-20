"""
main.py — مُراسِل: منصة الأخبار الذكية
FastAPI backend مع endpoints شاملة
"""

import logging
import asyncio
import os
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Dict, Optional, List
from dotenv import load_dotenv

load_dotenv()

from database import init_db, get_db_connection
from fetcher import fetch_rss
from nlp_engine import generate_article
from recommender import get_recommended_news, record_interaction
from notifier import get_notifications, get_unread_count, mark_all_read, mark_read
from deduplicator import get_cluster_articles
from scheduler import start_scheduler, scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Global fetch progress tracker ──
fetch_progress = {
    "active": False,
    "messages": [],
    "done": False,
    "total_fetched": 0
}

def reset_fetch_progress():
    fetch_progress["active"] = True
    fetch_progress["messages"] = []
    fetch_progress["done"] = False
    fetch_progress["total_fetched"] = 0

def add_progress(msg: str, count: int = 0):
    fetch_progress["messages"].append({
        "text": msg,
        "time": datetime.now().strftime("%H:%M:%S"),
        "count": count
    })
    fetch_progress["total_fetched"] += count


# ══════════════════════════════════════
# Lifespan
# ══════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting مُراسِل...")
    init_db()
    start_scheduler()
    fetch_task = asyncio.create_task(fetch_rss())
    yield
    logger.info("Shutting down مُراسِل...")
    scheduler.shutdown(wait=False)
    if not fetch_task.done():
        fetch_task.cancel()
        try:
            await fetch_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="مُراسِل API", lifespan=lifespan)


# ══════════════════════════════════════
# Pydantic Models
# ══════════════════════════════════════
class SourceCreate(BaseModel):
    name: str
    url: str
    category_hint: str = ""
    lang: str = "en"

class SourceToggle(BaseModel):
    enabled: int

class InteractionCreate(BaseModel):
    action: str
    dwell_time: int = 0

class PreferenceUpdate(BaseModel):
    category: str
    weight: float = 1.0
    notify: int = 0


# ══════════════════════════════════════
# NEWS ENDPOINTS
# IMPORTANT: Static paths MUST come BEFORE {news_id} path param
# ══════════════════════════════════════
@app.get("/api/news")
async def get_news(
    status: str = 'new', page: int = 1, limit: int = 20,
    q: str = None, category: str = None, source: str = None,
    sort: str = 'smart', ai_search: bool = False
):
    """Get news with smart recommendation sorting."""
    if ai_search and q:
        try:
            import google.generativeai as genai
            from config import config
            genai.configure(api_key=config.GEMINI_API_KEY)
            ai_model = genai.GenerativeModel(
                config.GEMINI_MODEL,
                generation_config={"response_mime_type": "application/json"}
            )
            prompt = f"""Extract 1-3 essential keywords in Arabic to search a news database for: "{q}"
Return ONLY a JSON list of strings."""
            resp = ai_model.generate_content(prompt)
            parsed = json.loads(resp.text)
            if isinstance(parsed, list) and len(parsed) > 0:
                q = " ".join(parsed)
        except Exception as e:
            logger.error(f"AI search error: {e}")

    result = get_recommended_news(
        status=status, page=page, limit=limit,
        category=category, source=source, q=q, sort=sort
    )
    return result


# ── These MUST be before /api/news/{news_id} ──

@app.get("/api/news/counts")
def get_news_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as cnt FROM news GROUP BY status")
    counts = {"new": 0, "approved": 0, "rejected": 0}
    for row in c.fetchall():
        counts[row['status']] = row['cnt']
    conn.close()
    return counts


@app.get("/api/news/cluster/{cluster_id}")
async def get_cluster(cluster_id: str):
    """Get all articles in a cluster (related stories)."""
    articles = get_cluster_articles(cluster_id)
    return {"cluster_id": cluster_id, "articles": articles, "count": len(articles)}


@app.get("/api/news/fetch-progress")
async def get_fetch_progress():
    """Get the current fetch progress state."""
    return fetch_progress


@app.get("/api/news/{news_id}")
async def get_single_news(news_id: str):
    """Get a single news article by ID."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    item = c.fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")
    return dict(item)


@app.get("/api/categories/counts")
def get_categories_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT category, COUNT(*) as count
        FROM news WHERE status = 'new' AND category IS NOT NULL
        GROUP BY category ORDER BY count DESC
    """)
    counts = {row['category']: row['count'] for row in c.fetchall()}
    conn.close()
    return counts


@app.get("/api/sources/counts")
def get_sources_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT source_name, COUNT(*) as count
        FROM news WHERE status = 'new' AND source_name IS NOT NULL
        GROUP BY source_name ORDER BY count DESC
    """)
    counts = {row['source_name']: row['count'] for row in c.fetchall()}
    conn.close()
    return counts


# ══════════════════════════════════════
# NEWS ACTIONS
# ══════════════════════════════════════
@app.post("/api/news/{news_id}/approve")
async def approve_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT title_ar, summary_ar, source_name FROM news WHERE id = ?", (news_id,))
    news_item = c.fetchone()
    if not news_item:
        conn.close()
        raise HTTPException(status_code=404, detail="News not found")

    article = await generate_article(news_item['title_ar'], news_item['summary_ar'], news_item['source_name'])
    if article:
        c.execute("UPDATE news SET status = 'approved', article_ar = ? WHERE id = ?", (article, news_id))
        conn.commit()
        conn.close()
        record_interaction(news_id, 'approve')
        return {"status": "success", "article_ar": article}
    else:
        conn.close()
        return {"status": "error", "error": "فشل في توليد المقال — حاول مرة أخرى"}


@app.post("/api/news/{news_id}/reject")
def reject_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category FROM news WHERE id = ?", (news_id,))
    item = c.fetchone()
    c.execute("UPDATE news SET status = 'rejected' WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    record_interaction(news_id, 'reject')
    return {"status": "success"}


@app.post("/api/news/{news_id}/restore")
def restore_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE news SET status = 'new' WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.post("/api/news/{news_id}/read")
def mark_news_read(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE news SET read_count = read_count + 1 WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    record_interaction(news_id, 'read')
    return {"status": "success"}


@app.post("/api/news/{news_id}/listen")
def mark_news_listened(news_id: str):
    record_interaction(news_id, 'listen')
    return {"status": "success"}


# ══════════════════════════════════════
# FETCH & CLEANUP with PROGRESS
# ══════════════════════════════════════
@app.post("/api/news/fetch")
async def manual_fetch():
    """Start fetch with progress tracking."""
    reset_fetch_progress()
    add_progress("⏳ بدء جلب الأخبار من المصادر...")

    try:
        count = await fetch_rss_with_progress()
        return {"status": "success", "fetched": count}
    except Exception as e:
        add_progress(f"❌ خطأ: {str(e)[:80]}")
        fetch_progress["done"] = True
        fetch_progress["active"] = False
        return {"status": "error", "error": str(e)}


async def fetch_rss_with_progress():
    """2-Phase parallel fetch: Collect all → Process AI in parallel."""
    import feedparser
    import hashlib
    import re
    import aiohttp
    from config import config

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sources WHERE enabled = 1")
    sources = cursor.fetchall()
    conn.close()

    total_sources = len(sources)
    max_per_source = config.MAX_ARTICLES_PER_SOURCE

    # ══════════════════════════════════════
    # PHASE 1: Collect articles from ALL sources (fast, no AI)
    # ══════════════════════════════════════
    add_progress(f"📡 المرحلة 1: جمع الأخبار من {total_sources} مصدر...")
    all_entries = []  # [{title, content, lang}]
    all_metas = []    # [{id, link, ...}]

    for src_idx, source in enumerate(sources):
        try:
            feed = feedparser.parse(source['url'])
            if not feed.entries:
                add_progress(f"⚠️ لا أخبار من {source['name']}")
                continue

            source_count = 0
            for entry in feed.entries:
                if source_count >= max_per_source:
                    break

                link = getattr(entry, 'link', '')
                if not link:
                    continue

                article_id = hashlib.md5(link.encode('utf-8')).hexdigest()

                # Check if exists (use single connection)
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                exists = c.fetchone()
                conn.close()
                if exists:
                    continue

                title = getattr(entry, 'title', '')
                content = getattr(entry, 'summary', getattr(entry, 'description', ''))
                published_at = getattr(entry, 'published', datetime.now(timezone.utc).isoformat())
                lang = source['lang'] if source['lang'] else 'en'

                # Extract image
                image_url = ''
                media = getattr(entry, 'media_content', None)
                if media and len(media) > 0:
                    image_url = media[0].get('url', '')
                if not image_url:
                    thumb = getattr(entry, 'media_thumbnail', None)
                    if thumb and len(thumb) > 0:
                        image_url = thumb[0].get('url', '')
                if not image_url:
                    for enc in getattr(entry, 'enclosures', []):
                        if enc.get('type', '').startswith('image'):
                            image_url = enc.get('href', enc.get('url', ''))
                            break
                if not image_url:
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content or '')
                    if img_match:
                        image_url = img_match.group(1)

                all_entries.append({"title": title, "content": content or title, "lang": lang})
                all_metas.append({
                    "id": article_id, "link": link, "published_at": published_at,
                    "image_url": image_url, "source_name": source['name'],
                    "source_url": source['url'], "lang": lang,
                    "category_hint": source['category_hint'] or ''
                })
                source_count += 1

            if source_count > 0:
                add_progress(f"📥 {source['name']}: {source_count} خبر جديد")

        except Exception as e:
            add_progress(f"❌ {source['name']}: {str(e)[:50]}")

    # NewsAPI
    if config.NEWSAPI_KEY:
        add_progress("📡 جلب من NewsAPI...")
        try:
            newsapi_articles = await _collect_newsapi(config)
            all_entries.extend(newsapi_articles['entries'])
            all_metas.extend(newsapi_articles['metas'])
            if newsapi_articles['count'] > 0:
                add_progress(f"📥 NewsAPI: {newsapi_articles['count']} خبر جديد")
        except Exception as e:
            add_progress(f"❌ NewsAPI: {str(e)[:50]}")

    total_new = len(all_entries)
    if total_new == 0:
        add_progress("✅ لا توجد أخبار جديدة")
        fetch_progress["done"] = True
        fetch_progress["active"] = False
        return 0

    add_progress(f"📊 إجمالي: {total_new} خبر جديد من جميع المصادر")

    # ══════════════════════════════════════
    # PHASE 2: Process AI in PARALLEL batches
    # ══════════════════════════════════════
    batch_size = config.BATCH_SIZE
    num_batches = (total_new + batch_size - 1) // batch_size
    add_progress(f"🧠 المرحلة 2: معالجة AI — {num_batches} دفعة (بحجم {batch_size}) بالتوازي...")

    # Create batches
    batches = []
    for i in range(0, total_new, batch_size):
        batches.append((
            all_entries[i:i+batch_size],
            all_metas[i:i+batch_size]
        ))

    # Process with semaphore for parallel control
    semaphore = asyncio.Semaphore(config.PARALLEL_SOURCES)
    total_stored = 0
    completed_batches = 0

    async def process_one_batch(batch_idx, entries, metas):
        nonlocal total_stored, completed_batches
        async with semaphore:
            cnt = await _store_batch(entries, metas)
            total_stored += cnt
            completed_batches += 1
            add_progress(f"✅ دفعة {completed_batches}/{num_batches}: معالجة {cnt} خبر", cnt)

    # Launch all batches concurrently (semaphore limits to PARALLEL_SOURCES at a time)
    tasks = []
    for idx, (entries, metas) in enumerate(batches):
        tasks.append(asyncio.create_task(process_one_batch(idx, entries, metas)))

    await asyncio.gather(*tasks, return_exceptions=True)

    add_progress(f"🎉 اكتمل! {total_stored} خبر جديد في {completed_batches} دفعة")
    fetch_progress["done"] = True
    fetch_progress["active"] = False
    return total_stored


async def _store_batch(entries, metas):
    """Process and store a batch."""
    from nlp_engine import process_batch
    from deduplicator import find_similar_articles, add_to_cluster
    from notifier import check_and_notify

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

        cluster_id = find_similar_articles(title_ar, similarity_hash, category)

        try:
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
            if cluster_id:
                try:
                    add_to_cluster(cluster_id, meta['id'], 0.8)
                except Exception:
                    pass
            count += 1
            check_and_notify(meta['id'], title_ar, category)
        except Exception as e:
            logger.error(f"Store error {meta['id']}: {e}")

    conn.close()
    return count


async def _collect_newsapi(config):
    """Collect articles from NewsAPI (no AI, just collect)."""
    import aiohttp
    import hashlib

    entries = []
    metas = []
    cat_map = {
        "business": "اقتصاد", "entertainment": "فن وترفيه",
        "health": "صحة", "science": "علوم",
        "sports": "رياضة", "technology": "تكنولوجيا",
    }
    now = datetime.now(timezone.utc).isoformat()

    async with aiohttp.ClientSession() as session:
        for cat in config.NEWSAPI_CATEGORIES:
            url = (f"https://newsapi.org/v2/top-headlines"
                   f"?category={cat}&language=en&pageSize={config.MAX_ARTICLES_PER_SOURCE}"
                   f"&apiKey={config.NEWSAPI_KEY}")
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            except Exception:
                continue

            for article in data.get('articles', []):
                link = article.get('url', '')
                if not link:
                    continue
                article_id = hashlib.md5(link.encode('utf-8')).hexdigest()

                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                if c.fetchone():
                    conn.close()
                    continue
                conn.close()

                entries.append({
                    "title": article.get('title', ''),
                    "content": article.get('description', '') or '',
                    "lang": "en"
                })
                metas.append({
                    "id": article_id, "link": link,
                    "published_at": article.get('publishedAt', now),
                    "image_url": article.get('urlToImage', ''),
                    "source_name": article.get('source', {}).get('name', 'NewsAPI'),
                    "source_url": "NewsAPI", "lang": "en",
                    "category_hint": cat_map.get(cat, "منوعات")
                })

    return {"entries": entries, "metas": metas, "count": len(entries)}


# ══════════════════════════════════════
# CLEAR/CLEANUP
# ══════════════════════════════════════
@app.post("/api/news/clear-old")
def clear_old_news():
    """Delete all old news (keeps only today's)."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM news WHERE datetime(fetched_at) < datetime('now', '-24 hours')")
    deleted = c.rowcount
    c.execute("DELETE FROM news_clusters WHERE news_id NOT IN (SELECT id FROM news)")
    c.execute("DELETE FROM interactions WHERE news_id NOT IN (SELECT id FROM news)")
    c.execute("DELETE FROM notifications WHERE news_id NOT IN (SELECT id FROM news)")
    conn.commit()
    conn.close()
    return {"status": "success", "deleted": deleted}


@app.post("/api/news/clear-all")
def clear_all_news():
    """Delete ALL news from database."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM news")
    deleted = c.rowcount
    c.execute("DELETE FROM news_clusters")
    c.execute("DELETE FROM interactions")
    c.execute("DELETE FROM notifications")
    conn.commit()
    conn.close()
    return {"status": "success", "deleted": deleted}


# ══════════════════════════════════════
# SOURCES
# ══════════════════════════════════════
@app.get("/api/sources")
def get_sources():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sources ORDER BY name")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


@app.post("/api/sources")
def add_source(source: SourceCreate):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sources (name, url, category_hint, lang) VALUES (?, ?, ?, ?)",
        (source.name, source.url, source.category_hint, source.lang)
    )
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.put("/api/sources/{source_id}")
def toggle_source(source_id: int, source: SourceToggle):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE sources SET enabled = ? WHERE id = ?", (source.enabled, source_id))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}


# ══════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════
@app.get("/api/settings")
def get_settings():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM settings")
    settings = {row['key']: row['value'] for row in c.fetchall()}
    conn.close()
    from config import config
    default_settings = {
        "FETCH_INTERVAL_MINUTES": str(config.FETCH_INTERVAL_MINUTES),
        "MAX_NEWS_AGE_HOURS": str(config.MAX_NEWS_AGE_HOURS)
    }
    default_settings.update(settings)
    return default_settings


@app.post("/api/settings")
def update_settings(updates: Dict[str, str]):
    conn = get_db_connection()
    c = conn.cursor()
    for k, v in updates.items():
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v))
        )
    conn.commit()
    conn.close()
    return {"status": "success"}


# ══════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════
@app.get("/api/notifications")
def api_get_notifications(unread_only: bool = False, limit: int = 50):
    notifs = get_notifications(limit=limit, unread_only=unread_only)
    unread = get_unread_count()
    return {"notifications": notifs, "unread_count": unread}


@app.post("/api/notifications/read")
def api_mark_all_read():
    mark_all_read()
    return {"status": "success"}


@app.post("/api/notifications/{notif_id}/read")
def api_mark_read(notif_id: int):
    mark_read(notif_id)
    return {"status": "success"}


# ══════════════════════════════════════
# PREFERENCES
# ══════════════════════════════════════
@app.get("/api/preferences")
def api_get_preferences():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM user_preferences ORDER BY weight DESC")
    prefs = [dict(r) for r in c.fetchall()]
    conn.close()
    return prefs


@app.post("/api/preferences")
def api_update_preferences(updates: List[PreferenceUpdate]):
    conn = get_db_connection()
    c = conn.cursor()
    for u in updates:
        c.execute(
            """INSERT INTO user_preferences (category, weight, notify)
               VALUES (?, ?, ?)
               ON CONFLICT(category) DO UPDATE SET weight=?, notify=?""",
            (u.category, u.weight, u.notify, u.weight, u.notify)
        )
    conn.commit()
    conn.close()
    return {"status": "success"}


# ══════════════════════════════════════
# STATS
# ══════════════════════════════════════
@app.get("/api/stats")
def get_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM news")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT source_name) FROM news")
    sources = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT cluster_id) FROM news WHERE cluster_id IS NOT NULL")
    clusters = c.fetchone()[0]
    c.execute("SELECT category, COUNT(*) as cnt FROM news WHERE status='new' GROUP BY category ORDER BY cnt DESC")
    top_categories = [{"category": r['category'], "count": r['cnt']} for r in c.fetchall()]
    conn.close()
    return {
        "total_articles": total,
        "active_sources": sources,
        "story_clusters": clusters,
        "top_categories": top_categories
    }


# ══════════════════════════════════════
# STATIC FILES & ENTRY POINT
# ══════════════════════════════════════
os.makedirs("static", exist_ok=True)
os.makedirs("static/icons", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/manifest.json")
def serve_manifest():
    return FileResponse("static/manifest.json")


@app.get("/sw.js")
def serve_sw():
    return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/favicon.ico")
def serve_favicon():
    return FileResponse("static/favicon.ico")


@app.get("/")
def read_index():
    if not os.path.exists("static/index.html"):
        return {"message": "index.html not found"}
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False
    )
