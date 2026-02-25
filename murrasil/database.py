import sqlite3
import os
from config import config

def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول الأخبار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id TEXT PRIMARY KEY,
            title_ar TEXT,
            summary_ar TEXT,
            article_ar TEXT,
            source_name TEXT,
            source_url TEXT,
            original_url TEXT,
            published_at TEXT,
            fetched_at TEXT,
            category TEXT,
            status TEXT DEFAULT 'new'
        )
    ''')
    
    # جدول المصادر
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT,
            enabled INTEGER DEFAULT 1
        )
    ''')
    
    # جدول الإعدادات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # إضافة المصادر الافتراضية إذا كان الجدول فارغاً
    cursor.execute('SELECT COUNT(*) FROM sources')
    if cursor.fetchone()[0] == 0:
        default_sources = [
            ("TechCrunch", "https://techcrunch.com/feed/"),
            ("The Verge", "https://www.theverge.com/rss/index.xml"),
            ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
            ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss"),
            ("THE DECODER", "https://the-decoder.com/feed/"),
            ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
            ("OpenAI Blog", "https://openai.com/blog/rss/"),
            ("Google AI Blog", "http://googleaiblog.blogspot.com/atom.xml"),
            ("Hacker News", "https://news.ycombinator.com/rss"),
            ("Reddit MachineLearning", "https://www.reddit.com/r/MachineLearning/.rss"),
            ("arXiv cs.AI", "https://arxiv.org/rss/cs.AI"),
            ("arXiv cs.LG", "https://arxiv.org/rss/cs.LG")
        ]
        cursor.executemany('INSERT INTO sources (name, url) VALUES (?, ?)', default_sources)
        
    conn.commit()
    conn.close()

# عند الاستيراد، تأكد من تهيئة القاعدة
if not os.path.exists(config.DB_PATH):
    init_db()
else:
    # لتأكيد أن الجداول موجودة حتى لو الملف موجود بس فارغ
    init_db()
