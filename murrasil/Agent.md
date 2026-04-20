# 🧠 Agent.md - مُراسِل v2.1

## 📊 نظرة عامة

- **نوع المشروع:** Web App (PWA)
- **اللغة:** Python / JavaScript / HTML / CSS
- **الإطار:** FastAPI / Vanilla JS / Vanilla CSS
- **الإصدار:** 2.1.0 (Performance Update)
- **نقطة الدخول:** `main.py`

## 🌲 المخطط الشجري

```
murrasil/
├── main.py              # FastAPI app + all API endpoints
├── config.py            # Settings from .env
├── database.py          # SQLite schema (7 tables) + migrations
├── nlp_engine.py        # AI: summarize, classify, translate (batch)
├── fetcher.py           # RSS + NewsAPI fetching with batch AI
├── deduplicator.py      # Story deduplication + clustering
├── recommender.py       # Collaborative filtering + smart sorting
├── notifier.py          # In-app notification system
├── scheduler.py         # 5 periodic jobs
├── ai_writer.py         # Backward compat → nlp_engine
├── .env                 # API keys (Gemini + NewsAPI)
├── requirements.txt     # Python deps
├── news.db              # SQLite database (auto-created)
├── static/
│   ├── index.html       # Premium UI with 5 themes
│   ├── style.css        # 5 CSS themes + design system
│   ├── app.js           # Frontend logic + TTS + offline
│   ├── sw.js            # Service Worker (offline support)
│   ├── manifest.json    # PWA manifest
│   └── icons/           # PWA icons
├── setup.bat / start.bat / stop.bat
```

## 🛠️ أوامر التشغيل

| الأمر | الوظيفة |
|-------|---------|
| `setup.bat` | تهيئة + تثبيت مكتبات |
| `start.bat` | تشغيل الخادم |
| `stop.bat` | إيقاف الخادم |
| `python main.py` | تشغيل يدوي |

## 📦 التبعيات الرئيسية

| المكتبة | الوظيفة |
|---------|---------|
| fastapi + uvicorn | API server |
| feedparser | RSS parsing |
| google-generativeai | Gemini AI (summarize/classify) |
| apscheduler | Periodic jobs |
| aiohttp | Async HTTP (NewsAPI) |
| beautifulsoup4 | HTML cleaning |
| scikit-learn | Text similarity |

## 📰 المصادر (17 مصدر)

Tech: TechCrunch, The Verge, VentureBeat, Wired, THE DECODER, HN
News: BBC News
Health: Medical News Today
Fashion: Vogue, Elle
Sports: ESPN, Sky Sports
Entertainment: Variety, BuzzFeed
Arabic: الجزيرة, العربية, RT عربي

## 🎨 الثيمات (5)

1. Midnight (dark navy) - default
2. Dawn (pink/rose)
3. Ocean (deep blue/cyan)
4. Forest (dark green)
5. Clean (light/white)

## ⚙️ إعدادات الأداء (config.py)

| الإعداد | القيمة | الوصف |
|---------|--------|-------|
| `MAX_ARTICLES_PER_SOURCE` | 10 | حد أقصى للمقالات من كل مصدر |
| `PARALLEL_SOURCES` | 3 | عدد الدفعات المتوازية |
| `BATCH_SIZE` | 10 | حجم الدفعة لمعالجة AI |

## ⚠️ المشاكل المعروفة

| المشكلة | الحل | التاريخ |
|---------|------|---------|
| API key expired | تجديد مفتاح Gemini في .env | 2026-04-01 |
| NLP JSON parse error | fallback لمعالجة فردية تلقائياً | 2026-04-01 |

## ✅ مشاكل تم حلها

| المشكلة | الحل | التاريخ |
|---------|------|---------|
| Database is locked | WAL mode + busy_timeout=30000 | 2026-04-01 |
| FOREIGN KEY constraint | ترتيب الإدراج: news قبل clusters | 2026-04-01 |
| 404 على counts/progress | Route ordering: static قبل {news_id} | 2026-04-01 |
| جلب الأخبار 20 دقيقة | 2-Phase parallel + MAX_ARTICLES=10 → ~2 دقيقة | 2026-04-01 |
| تغيير التصنيف بطيء | كاش محلي client-side → فوري | 2026-04-01 |
| فشل توليد المقال | retry + logging + safety filter check | 2026-04-01 |
| favicon.ico 404 | أيقونة + route مخصص | 2026-04-01 |
| سجل الجلب فارغ | toggle يسحب الحالة من API | 2026-04-01 |

## 🚫 أنماط يجب تجنبها

- لا تستخدم `npx wrangler` (Cloudflare)
- لا تحذف news.db أثناء التشغيل
- لا تتجاوز 15 RPM على حساب Gemini المجاني
- لا تستخدم `response_mime_type: json` مع generate_article (نص حر)

## 🧹 صيانة الذاكرة
### آخر تنظيف: 2026-04-01
