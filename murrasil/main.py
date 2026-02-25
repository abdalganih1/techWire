import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict

from database import init_db, get_db_connection
from fetcher import fetch_rss
from ai_writer import generate_article
from scheduler import start_scheduler, scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up application...")
    init_db()
    start_scheduler()
    
    # Run an initial fetch in the background without blocking startup
    asyncio.create_task(fetch_rss())
    
    yield
    logger.info("Shutting down application...")
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# Pydantic models
class SourceCreate(BaseModel):
    name: str
    url: str

class SourceToggle(BaseModel):
    enabled: int

@app.get("/api/news")
def get_news(status: str = 'new', page: int = 1, limit: int = 20):
    conn = get_db_connection()
    c = conn.cursor()
    offset = (page - 1) * limit
    c.execute("SELECT * FROM news WHERE status = ? ORDER BY published_at DESC LIMIT ? OFFSET ?", (status, limit, offset))
    rows = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM news WHERE status = ?", (status,))
    total = c.fetchone()[0]
    conn.close()
    
    return {"data": [dict(row) for row in rows], "total": total, "page": page, "limit": limit}

@app.get("/api/news/counts")
def get_news_counts():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM news GROUP BY status")
    counts = {"new": 0, "approved": 0, "rejected": 0}
    for row in c.fetchall():
        counts[row['status']] = row['COUNT(*)']
    conn.close()
    return counts

@app.post("/api/news/{news_id}/approve")
async def approve_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT title_ar, summary_ar, source_name FROM news WHERE id = ?", (news_id,))
    news_item = c.fetchone()
    if not news_item:
        conn.close()
        raise HTTPException(status_code=404, detail="News item not found")
        
    article = await generate_article(news_item['title_ar'], news_item['summary_ar'], news_item['source_name'])
    
    if article:
        c.execute("UPDATE news SET status = 'approved', article_ar = ? WHERE id = ?", (article, news_id))
        conn.commit()
    conn.close()
    return {"status": "success", "article_ar": article}

@app.post("/api/news/{news_id}/reject")
def reject_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE news SET status = 'rejected' WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/news/{news_id}/restore")
def restore_news(news_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE news SET status = 'new' WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/news/fetch")
async def manual_fetch():
    count = await fetch_rss()
    return {"status": "success", "fetched": count}

@app.get("/api/sources")
def get_sources():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM sources")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/sources")
def add_source(source: SourceCreate):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO sources (name, url) VALUES (?, ?)", (source.name, source.url))
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

@app.get("/api/settings")
def get_settings():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM settings")
    settings = {row['key']: row['value'] for row in c.fetchall()}
    conn.close()
    from config import config
    default_settings = {
        "AI_MODEL": config.AI_MODEL,
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
        c.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    conn.commit()
    conn.close()
    return {"status": "success"}

import os
from dotenv import load_dotenv
load_dotenv()

# Create static directory if not exists
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

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
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )
