import sqlite3
import os
import logging
from config import config

logger = logging.getLogger(__name__)


def get_db_connection():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # ══════════════════════════════════════
    # جدول الأخبار (محدّث)
    # ══════════════════════════════════════
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
            status TEXT DEFAULT 'new',
            cluster_id TEXT,
            original_lang TEXT DEFAULT 'en',
            similarity_hash TEXT,
            read_count INTEGER DEFAULT 0,
            image_url TEXT,
            keywords TEXT
        )
    ''')

    # فهارس
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_status ON news(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_category ON news(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_cluster ON news(cluster_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_sim_hash ON news(similarity_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_name)')

    # ترقية الجدول إذا كان قديماً — إضافة أعمدة جديدة
    _safe_add_column(cursor, 'news', 'cluster_id', 'TEXT')
    _safe_add_column(cursor, 'news', 'original_lang', "TEXT DEFAULT 'en'")
    _safe_add_column(cursor, 'news', 'similarity_hash', 'TEXT')
    _safe_add_column(cursor, 'news', 'read_count', 'INTEGER DEFAULT 0')
    _safe_add_column(cursor, 'news', 'image_url', 'TEXT')
    _safe_add_column(cursor, 'news', 'keywords', 'TEXT')

    # ══════════════════════════════════════
    # جدول المصادر
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            url TEXT,
            category_hint TEXT,
            lang TEXT DEFAULT 'en',
            enabled INTEGER DEFAULT 1
        )
    ''')
    _safe_add_column(cursor, 'sources', 'category_hint', 'TEXT')
    _safe_add_column(cursor, 'sources', 'lang', "TEXT DEFAULT 'en'")

    # ══════════════════════════════════════
    # جدول الإعدادات
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    # ══════════════════════════════════════
    # جدول تفضيلات المستخدم
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT UNIQUE,
            weight REAL DEFAULT 1.0,
            notify INTEGER DEFAULT 0
        )
    ''')

    # ══════════════════════════════════════
    # جدول تجميعات القصص (Clusters)
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_clusters (
            cluster_id TEXT,
            news_id TEXT,
            similarity_score REAL,
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_clusters_cid ON news_clusters(cluster_id)')

    # ══════════════════════════════════════
    # جدول التفاعلات (للتوصيات)
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id TEXT,
            action TEXT,
            timestamp TEXT,
            dwell_time INTEGER DEFAULT 0,
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_interactions_action ON interactions(action)')

    # ══════════════════════════════════════
    # جدول الإشعارات
    # ══════════════════════════════════════
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            body TEXT,
            news_id TEXT,
            category TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read)')

    # ══════════════════════════════════════
    # المصادر الافتراضية
    # ══════════════════════════════════════
    cursor.execute('SELECT COUNT(*) FROM sources')
    if cursor.fetchone()[0] == 0:
        default_sources = [
            # ── تكنولوجيا ──
            ("TechCrunch", "https://techcrunch.com/feed/", "تكنولوجيا", "en"),
            ("The Verge", "https://www.theverge.com/rss/index.xml", "تكنولوجيا", "en"),
            ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "تكنولوجيا", "en"),
            ("Wired AI", "https://www.wired.com/feed/tag/ai/latest/rss", "تكنولوجيا", "en"),
            ("THE DECODER", "https://the-decoder.com/feed/", "تكنولوجيا", "en"),
            ("Hacker News", "https://news.ycombinator.com/rss", "تكنولوجيا", "en"),

            # ── أخبار عامة ──
            ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "منوعات", "en"),

            # ── صحة ──
            ("Medical News Today", "https://www.medicalnewstoday.com/rss", "صحة", "en"),

            # ── موضة وجمال ──
            ("Vogue", "https://www.vogue.com/feed/rss", "موضة وجمال", "en"),
            ("Elle", "https://www.elle.com/rss/all.xml/", "موضة وجمال", "en"),

            # ── رياضة ──
            ("ESPN", "https://www.espn.com/espn/rss/news", "رياضة", "en"),
            ("Sky Sports", "https://www.skysports.com/rss/12040", "رياضة", "en"),

            # ── فن وترفيه ──
            ("Variety", "https://variety.com/feed/", "فن وترفيه", "en"),
            ("BuzzFeed", "https://www.buzzfeed.com/index.xml", "منوعات", "en"),

            # ── مصادر عربية ──
            ("الجزيرة نت", "https://www.aljazeera.net/aljazeera/rss", "منوعات", "ar"),
            ("العربية", "https://www.alarabiya.net/.mrss/ar.xml", "منوعات", "ar"),
            ("RT عربي", "https://arabic.rt.com/rss/", "منوعات", "ar"),
        ]
        cursor.executemany(
            'INSERT INTO sources (name, url, category_hint, lang) VALUES (?, ?, ?, ?)',
            default_sources
        )

    # ══════════════════════════════════════
    # تفضيلات افتراضية
    # ══════════════════════════════════════
    cursor.execute('SELECT COUNT(*) FROM user_preferences')
    if cursor.fetchone()[0] == 0:
        default_prefs = [
            ("تكنولوجيا", 1.5, 1),
            ("رياضة", 1.0, 0),
            ("صحة", 1.0, 0),
            ("اقتصاد", 1.0, 0),
            ("سياسة", 0.8, 0),
            ("فن وترفيه", 1.0, 0),
            ("موضة وجمال", 0.8, 0),
            ("علوم", 1.2, 0),
            ("منوعات", 0.5, 0),
            ("عاجل", 2.0, 1),
        ]
        cursor.executemany(
            'INSERT INTO user_preferences (category, weight, notify) VALUES (?, ?, ?)',
            default_prefs
        )

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")


def _safe_add_column(cursor, table, column, col_type):
    """Add column if it doesn't exist (SQLite ALTER TABLE safe wrapper)."""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # Column already exists


# Initialize on import
init_db()
