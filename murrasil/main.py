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
from translator import translator

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

fetch_progress = {"active": False, "messages": [], "done": False, "total_fetched": 0}


def reset_fetch_progress():
    fetch_progress["active"] = True
    fetch_progress["messages"] = []
    fetch_progress["done"] = False
    fetch_progress["total_fetched"] = 0


def add_progress(msg: str, count: int = 0):
    fetch_progress["messages"].append(
        {"text": msg, "time": datetime.now().strftime("%H:%M:%S"), "count": count}
    )
    fetch_progress["total_fetched"] += count


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
# ══════════════════════════════════════
@app.get("/api/news")
async def get_news(
    status: str = "new",
    page: int = 1,
    limit: int = 20,
    q: str = None,
    category: str = None,
    source: str = None,
    sort: str = "smart",
    ai_search: bool = False,
    lang: str = "ar",
):
    """Get news with smart recommendation sorting and translation support."""
    if ai_search and q:
        try:
            import google.generativeai as genai
            from config import config

            genai.configure(api_key=config.GEMINI_API_KEY)
            ai_model = genai.GenerativeModel(
                config.GEMINI_MODEL,
                generation_config={"response_mime_type": "application/json"},
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
        status=status,
        page=page,
        limit=limit,
        category=category,
        source=source,
        q=q,
        sort=sort,
    )

    if lang and lang != "ar" and result.get("data"):
        news_ids = [item["id"] for item in result["data"]]
        translations = translator.get_cached_translations(news_ids, lang)

        for item in result["data"]:
            if item["id"] in translations:
                t = translations[item["id"]]
                item["title_display"] = t["title"]
                item["summary_display"] = t["summary"]
                item["article_display"] = t.get("article", "")
                item["is_translated"] = True
            else:
                item["title_display"] = item.get("title_ar", "")
                item["summary_display"] = item.get("summary_ar", "")
                item["article_display"] = item.get("article_ar", "")
                item["is_translated"] = False
                item["needs_translation"] = True
    elif result.get("data"):
        for item in result["data"]:
            item["title_display"] = item.get("title_ar", "")
            item["summary_display"] = item.get("summary_ar", "")
            item["article_display"] = item.get("article_ar", "")
            item["is_translated"] = True

    return result


@app.get("/api/news/counts")
def get_news_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) as cnt FROM news GROUP BY status")
    counts = {"new": 0, "approved": 0, "rejected": 0}
    for row in c.fetchall():
        counts[row["status"]] = row["cnt"]
    conn.close()
    return counts


@app.get("/api/news/cluster/{cluster_id}")
async def get_cluster(cluster_id: str):
    articles = get_cluster_articles(cluster_id)
    return {"cluster_id": cluster_id, "articles": articles, "count": len(articles)}


@app.get("/api/news/fetch-progress")
async def get_fetch_progress():
    return fetch_progress


@app.get("/api/news/{news_id}")
async def get_single_news(news_id: str, lang: str = "ar"):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM news WHERE id = ?", (news_id,))
    item = c.fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")
    result = dict(item)

    if lang and lang != "ar":
        translations = translator.get_cached_translations([news_id], lang)
        if news_id in translations:
            t = translations[news_id]
            result["title_display"] = t["title"]
            result["summary_display"] = t["summary"]
            result["article_display"] = t.get("article", "")
            result["is_translated"] = True
        else:
            result["title_display"] = result.get("title_ar", "")
            result["summary_display"] = result.get("summary_ar", "")
            result["article_display"] = result.get("article_ar", "")
            result["is_translated"] = False
            result["needs_translation"] = True
    else:
        result["title_display"] = result.get("title_ar", "")
        result["summary_display"] = result.get("summary_ar", "")
        result["article_display"] = result.get("article_ar", "")
        result["is_translated"] = True

    return result


@app.get("/api/categories/counts")
def get_categories_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT category, COUNT(*) as count
        FROM news WHERE status = 'new' AND category IS NOT NULL
        GROUP BY category ORDER BY count DESC
    """)
    counts = {row["category"]: row["count"] for row in c.fetchall()}
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
    counts = {row["source_name"]: row["count"] for row in c.fetchall()}
    conn.close()
    return counts


# ══════════════════════════════════════
# NEWS ACTIONS
# ══════════════════════════════════════
@app.post("/api/news/{news_id}/approve")
async def approve_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT title_ar, summary_ar, source_name FROM news WHERE id = ?", (news_id,)
    )
    news_item = c.fetchone()
    if not news_item:
        conn.close()
        raise HTTPException(status_code=404, detail="News not found")

    article = await generate_article(
        news_item["title_ar"], news_item["summary_ar"], news_item["source_name"]
    )
    if article:
        c.execute(
            "UPDATE news SET status = 'approved', article_ar = ? WHERE id = ?",
            (article, news_id),
        )
        conn.commit()
        conn.close()
        record_interaction(news_id, "approve")
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
    record_interaction(news_id, "reject")
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
    record_interaction(news_id, "read")
    return {"status": "success"}


@app.post("/api/news/{news_id}/listen")
def mark_news_listened(news_id: str):
    record_interaction(news_id, "listen")
    return {"status": "success"}


# ══════════════════════════════════════
# FETCH & CLEANUP with PROGRESS
# ══════════════════════════════════════
@app.post("/api/news/fetch")
async def manual_fetch():
    reset_fetch_progress()
    add_progress("⏳ بدء جلب الأخبار من المصادر...")

    try:
        count = await fetch_rss(progress_callback=add_progress)
        fetch_progress["done"] = True
        fetch_progress["active"] = False
        return {"status": "success", "fetched": count}
    except Exception as e:
        add_progress(f"❌ خطأ: {str(e)[:80]}")
        fetch_progress["done"] = True
        fetch_progress["active"] = False
        return {"status": "error", "error": str(e)}


@app.post("/api/news/clear-old")
def clear_old_news():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "DELETE FROM news WHERE datetime(fetched_at) < datetime('now', '-24 hours')"
    )
    deleted = c.rowcount
    c.execute("DELETE FROM news_clusters WHERE news_id NOT IN (SELECT id FROM news)")
    c.execute("DELETE FROM interactions WHERE news_id NOT IN (SELECT id FROM news)")
    c.execute("DELETE FROM notifications WHERE news_id NOT IN (SELECT id FROM news)")
    c.execute("DELETE FROM translations WHERE news_id NOT IN (SELECT id FROM news)")
    conn.commit()
    conn.close()
    return {"status": "success", "deleted": deleted}


@app.post("/api/news/clear-all")
def clear_all_news():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM news")
    deleted = c.rowcount
    c.execute("DELETE FROM news_clusters")
    c.execute("DELETE FROM interactions")
    c.execute("DELETE FROM notifications")
    c.execute("DELETE FROM translations")
    conn.commit()
    conn.close()
    return {"status": "success", "deleted": deleted}


# ══════════════════════════════════════
# TRANSLATION ENDPOINTS
# ══════════════════════════════════════
@app.post("/api/settings/language")
async def set_display_language(body: dict):
    from config import config as cfg

    lang = body.get("lang", cfg.DEFAULT_LANGUAGE)
    if lang not in cfg.SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO settings (key, value) VALUES ('display_language', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (lang,),
    )
    conn.commit()
    conn.close()

    if lang != "ar":
        asyncio.create_task(translator.bulk_translate_recent(lang, limit=50))

    return {"status": "success", "lang": lang}


@app.post("/api/translate/{news_id}")
async def translate_single(news_id: str, lang: str = "ar"):
    result = await translator.translate_article(news_id, lang)
    return result


@app.post("/api/translate/bulk")
async def translate_bulk(body: dict):
    news_ids = body.get("news_ids", [])
    lang = body.get("lang", "ar")
    if not news_ids:
        return {"translations": []}
    results = await translator.bulk_translate(news_ids, lang)
    return {"translations": results}


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
        (source.name, source.url, source.category_hint, source.lang),
    )
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.put("/api/sources/{source_id}")
def toggle_source(source_id: int, source: SourceToggle):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE sources SET enabled = ? WHERE id = ?", (source.enabled, source_id)
    )
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
    settings = {row["key"]: row["value"] for row in c.fetchall()}
    conn.close()
    from config import config

    default_settings = {
        "FETCH_INTERVAL_MINUTES": str(config.FETCH_INTERVAL_MINUTES),
        "MAX_NEWS_AGE_HOURS": str(config.MAX_NEWS_AGE_HOURS),
        "DISPLAY_LANGUAGE": config.DEFAULT_LANGUAGE,
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
            (k, str(v)),
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
            (u.category, u.weight, u.notify, u.weight, u.notify),
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
    c.execute(
        "SELECT COUNT(DISTINCT cluster_id) FROM news WHERE cluster_id IS NOT NULL"
    )
    clusters = c.fetchone()[0]
    c.execute(
        "SELECT category, COUNT(*) as cnt FROM news WHERE status='new' GROUP BY category ORDER BY cnt DESC"
    )
    top_categories = [
        {"category": r["category"], "count": r["cnt"]} for r in c.fetchall()
    ]
    conn.close()
    return {
        "total_articles": total,
        "active_sources": sources,
        "story_clusters": clusters,
        "top_categories": top_categories,
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
        reload=False,
    )
