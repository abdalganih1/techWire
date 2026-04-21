import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # === AI ===
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # === NVIDIA Translation ===
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b")

    # === Languages ===
    SUPPORTED_LANGUAGES = ["ar", "en", "fr"]
    DEFAULT_LANGUAGE = "ar"

    # === Scheduling ===
    FETCH_INTERVAL_MINUTES = int(os.getenv("FETCH_INTERVAL_MINUTES", "15"))
    MAX_NEWS_AGE_HOURS = int(os.getenv("MAX_NEWS_AGE_HOURS", "168"))  # أسبوع
    CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "6"))

    # === Server ===
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))

    # === Database ===
    DB_PATH = os.path.join(os.path.dirname(__file__), "news.db")

    # === NewsAPI ===
    NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
    NEWSAPI_CATEGORIES = [
        "business",
        "entertainment",
        "health",
        "science",
        "sports",
        "technology",
    ]
    NEWSAPI_COUNTRIES = ["us", "gb"]

    # === TTS ===
    TTS_ENABLED = os.getenv("TTS_ENABLED", "true").lower() == "true"

    # === Deduplication ===
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))

    # === Batch Processing ===
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
    MAX_ARTICLES_PER_SOURCE = int(os.getenv("MAX_ARTICLES_PER_SOURCE", "10"))
    PARALLEL_SOURCES = int(os.getenv("PARALLEL_SOURCES", "3"))

    # === Categories ===
    CATEGORIES = [
        "تكنولوجيا",
        "رياضة",
        "صحة",
        "اقتصاد",
        "سياسة",
        "فن وترفيه",
        "موضة وجمال",
        "علوم",
        "منوعات",
        "عاجل",
    ]


config = Config()
