# 🧠 Agent.md - مُراسِل

## 📊 نظرة عامة

- **نوع المشروع:** web app
- **اللغة:** Python / JavaScript / HTML / CSS
- **الإطار:** FastAPI / Vanilla JS / Tailwind CSS
- **الإصدار:** 1.0.0
- **نقطة الدخول:** `main.py`

## 🌲 المخطط الشجري

murrasil/
├── main.py              # FastAPI app entry point
├── scheduler.py         # Background RSS fetching job
├── fetcher.py           # RSS parsing + AI summarization logic
├── database.py          # SQLite models and CRUD operations
├── ai_writer.py         # Article generation logic
├── config.py            # Settings loaded from .env
├── .env                 # API keys and user preferences
├── static/
│   ├── index.html       # Main SPA dashboard
│   ├── style.css        # Custom styles (Tailwind CDN)
│   └── app.js           # Frontend logic (fetch API calls)
├── requirements.txt
├── README.md

## 🛠️ أوامر التشغيل

| الأمر | الوظيفة |
|-------|---------|
| `python main.py` | أو `uvicorn main:app --reload` لتشغيل الخادم |
| `pip install -r requirements.txt` | تثبيت الاعتماديات |

## 📦 التبعيات الرئيسية

| المكتبة | الوظيفة |
|---------|---------|
| fastapi | الواجهة البرمجية (API) |
| feedparser | التعامل مع RSS |
| openai | الربط مع نماذج الذكاء الاصطناعي |
| apscheduler | جدولة الجلب التلقائي |
| aiohttp | طلبات الشبكة |

## ✅ أفضل الممارسات المكتشفة

- الاستعلامات واستخدام SQLite محليًا.
- حفظ الإعدادات في قاعدة البيانات والبيانات الحساسة في `.env`.

## ⚠️ المشاكل المعروفة والحلول

| المشكلة | السبب | الحل | التاريخ |
|---------|-------|------|---------|
| -- | -- | -- | -- |

## 📚 مراجع مفيدة

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [OpenAI Python Library](https://github.com/openai/openai-python)
