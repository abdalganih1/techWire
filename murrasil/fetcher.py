import feedparser
import hashlib
import json
import logging
import os
import asyncio
from datetime import datetime, timezone

import google.generativeai as genai
from config import config
from database import get_db_connection

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"response_mime_type": "application/json"})

async def generate_summary(title, content):
    prompt = f"""You are a tech journalist. Given this news article title and content in English,
return a JSON object with:
- "title_ar": Arabic translation of the title (concise, journalistic)
- "summary_ar": 2-3 sentence Arabic summary of the article
- "category": one of [نماذج AI, أبحاث, أدوات, شركات ناشئة, أجهزة, سياسات]

Article title: {title}
Article content/description: {content}

Return ONLY valid JSON, no explanation."""
    
    try:
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        return result
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return None

async def fetch_rss():
    logger.info("Starting RSS fetch...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM sources WHERE enabled = 1")
    sources = cursor.fetchall()
    
    new_articles_count = 0
    now = datetime.now(timezone.utc).isoformat()
    
    for source in sources:
        try:
            feed = feedparser.parse(source['url'])
            for entry in feed.entries:
                link = getattr(entry, 'link', '')
                if not link:
                    continue
                
                article_id = hashlib.md5(link.encode('utf-8')).hexdigest()
                
                cursor.execute("SELECT id FROM news WHERE id = ?", (article_id,))
                if cursor.fetchone():
                    continue
                
                title = getattr(entry, 'title', '')
                content = getattr(entry, 'summary', getattr(entry, 'description', ''))
                published_at = getattr(entry, 'published', now)
                
                ai_data = await generate_summary(title, content)
                await asyncio.sleep(4)  # Rate Limit protection (Gemini Free: 15 RPM)
                
                if not ai_data:
                    continue
                
                title_ar = ai_data.get('title_ar', title)
                summary_ar = ai_data.get('summary_ar', '')
                category = ai_data.get('category', 'أخرى')
                
                cursor.execute('''
                    INSERT INTO news 
                    (id, title_ar, summary_ar, source_name, source_url, original_url, published_at, fetched_at, category, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                ''', (article_id, title_ar, summary_ar, source['name'], source['url'], link, published_at, now, category))
                
                new_articles_count += 1
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error fetching source {source['name']}: {e}")
            
    conn.close()
    logger.info(f"RSS fetch completed. Added {new_articles_count} new articles.")
    return new_articles_count
