"""
translator.py — محرك الترجمة عبر NVIDIA Nemotron API
يدعم: كاش SQLite، ترجمة فردية/جماعية، تخطي المترجم مسبقاً
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict

from openai import OpenAI

from config import config
from database import get_db_connection

logger = logging.getLogger(__name__)

LANG_NAMES = {
    "ar": "Arabic",
    "en": "English",
    "fr": "French",
}


class Translator:
    def __init__(self):
        self.client = None
        if config.NVIDIA_API_KEY:
            self.client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=config.NVIDIA_API_KEY,
            )

    def _get_cached(self, news_id: str, lang: str) -> Optional[Dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT title, summary, article, model_used FROM translations WHERE news_id = ? AND lang = ?",
            (news_id, lang),
        )
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "news_id": news_id,
                "lang": lang,
                "title": row["title"],
                "summary": row["summary"],
                "article": row["article"],
                "model_used": row["model_used"],
                "is_translated": True,
            }
        return None

    def _get_original(self, news_id: str) -> Optional[Dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id, title_ar, summary_ar, article_ar, original_lang FROM news WHERE id = ?",
            (news_id,),
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)

    def _save_cache(
        self,
        news_id: str,
        lang: str,
        title: str,
        summary: str,
        article: str,
        model: str,
    ):
        conn = get_db_connection()
        c = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        c.execute(
            """INSERT INTO translations (news_id, lang, title, summary, article, translated_at, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(news_id, lang) DO UPDATE SET
                   title=excluded.title, summary=excluded.summary, article=excluded.article,
                   translated_at=excluded.translated_at, model_used=excluded.model_used""",
            (news_id, lang, title, summary, article, now, model),
        )
        conn.commit()
        conn.close()

    def _call_nvidia(
        self,
        original_title: str,
        original_summary: str,
        original_article: str,
        target_lang: str,
    ) -> Dict:
        if not self.client:
            raise RuntimeError("NVIDIA API key not configured")

        target_name = LANG_NAMES.get(target_lang, target_lang)
        prompt = f"""You are a professional news translator. Translate the following news content to {target_name}.
Return ONLY valid JSON with no explanation:
{{
  "title": "translated title",
  "summary": "translated summary",
  "article": "translated article (if provided)"
}}

Title: {original_title}
Summary: {original_summary}"""
        if original_article:
            prompt += f"\nArticle: {original_article[:3000]}"

        response = self.client.chat.completions.create(
            model=config.NVIDIA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator. Translate news content to {target_name}. Return only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        import json

        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        return {
            "title": result.get("title", original_title),
            "summary": result.get("summary", original_summary),
            "article": result.get("article", ""),
        }

    async def translate_article(self, news_id: str, target_lang: str) -> Dict:
        if target_lang == "ar":
            original = self._get_original(news_id)
            if not original:
                return {"error": "Article not found", "news_id": news_id}
            return {
                "news_id": news_id,
                "lang": "ar",
                "title": original["title_ar"],
                "summary": original["summary_ar"],
                "article": original.get("article_ar", ""),
                "is_translated": False,
            }

        cached = self._get_cached(news_id, target_lang)
        if cached:
            return cached

        original = self._get_original(news_id)
        if not original:
            return {"error": "Article not found", "news_id": news_id}

        try:
            translated = self._call_nvidia(
                original["title_ar"],
                original["summary_ar"] or "",
                original.get("article_ar", "") or "",
                target_lang,
            )
            self._save_cache(
                news_id,
                target_lang,
                translated["title"],
                translated["summary"],
                translated["article"],
                config.NVIDIA_MODEL,
            )
            return {
                "news_id": news_id,
                "lang": target_lang,
                "title": translated["title"],
                "summary": translated["summary"],
                "article": translated["article"],
                "model_used": config.NVIDIA_MODEL,
                "is_translated": True,
            }
        except Exception as e:
            logger.error(f"Translation error for {news_id} -> {target_lang}: {e}")
            return {
                "news_id": news_id,
                "lang": target_lang,
                "title": original["title_ar"],
                "summary": original["summary_ar"],
                "article": original.get("article_ar", ""),
                "is_translated": False,
                "needs_translation": True,
                "error": str(e),
            }

    async def bulk_translate(self, news_ids: List[str], target_lang: str) -> List[Dict]:
        results = []
        for nid in news_ids:
            result = await self.translate_article(nid, target_lang)
            results.append(result)
        return results

    async def bulk_translate_recent(
        self, target_lang: str, limit: int = 50
    ) -> List[Dict]:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM news WHERE status = 'new' ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        )
        ids = [row["id"] for row in c.fetchall()]
        conn.close()

        untranslated = []
        for nid in ids:
            cached = self._get_cached(nid, target_lang)
            if not cached:
                untranslated.append(nid)

        if not untranslated:
            return []

        logger.info(f"Pre-translating {len(untranslated)} articles to {target_lang}")
        return await self.bulk_translate(untranslated, target_lang)

    def get_cached_translations(
        self, news_ids: List[str], lang: str
    ) -> Dict[str, Dict]:
        if lang == "ar":
            return {}
        if not news_ids:
            return {}
        conn = get_db_connection()
        c = conn.cursor()
        placeholders = ",".join("?" for _ in news_ids)
        c.execute(
            f"SELECT news_id, title, summary, article FROM translations WHERE lang = ? AND news_id IN ({placeholders})",
            [lang] + news_ids,
        )
        result = {}
        for row in c.fetchall():
            result[row["news_id"]] = {
                "title": row["title"],
                "summary": row["summary"],
                "article": row["article"],
            }
        conn.close()
        return result


translator = Translator()
