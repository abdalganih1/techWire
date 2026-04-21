"""
nlp_engine.py — محرك NLP الذكي
يتولى: التلخيص، التصنيف التلقائي، استخراج الكلمات المفتاحية
يستخدم Gemini API مع Batch Processing
"""

import json
import logging
import asyncio
import hashlib
from typing import List

import google.generativeai as genai
from config import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)
_model = genai.GenerativeModel(
    config.GEMINI_MODEL, generation_config={"response_mime_type": "application/json"}
)

CATEGORIES_LIST = ", ".join(config.CATEGORIES)


async def process_single_article(
    title: str, content: str, source_lang: str = "en"
) -> dict | None:
    """Process a single article: translate, summarize, classify, extract keywords."""

    if source_lang == "ar":
        prompt = f"""أنت محرر أخبار محترف. حلل الخبر العربي التالي وأعد JSON:

عنوان الخبر: {title}
محتوى الخبر: {content[:1500]}

أعد JSON بالشكل التالي (بدون أي شرح):
{{
  "title_ar": "عنوان مختصر وجذاب (نفس اللغة أو محسّن)",
  "summary_ar": "ملخص من 2-3 جمل مركزة يحول 10 أسطر إلى 3",
  "category": "واحدة من: [{CATEGORIES_LIST}]",
  "keywords": ["كلمة1", "كلمة2", "كلمة3"],
  "is_breaking": false
}}

قواعد التصنيف:
- إذا كان عاجلاً أو كبيراً جداً → "عاجل" و is_breaking=true
- صنّف بدقة حسب المحتوى الفعلي"""
    else:
        prompt = f"""You are a professional news editor. Analyze this English news article and return JSON:

Title: {title}
Content: {content[:1500]}

Return ONLY valid JSON (no explanation):
{{
  "title_ar": "Arabic translation of title (concise, journalistic)",
  "summary_ar": "2-3 sentence Arabic summary (convert 10 lines to 3)",
  "category": "one of: [{CATEGORIES_LIST}]",
  "keywords": ["keyword1_ar", "keyword2_ar", "keyword3_ar"],
  "is_breaking": false
}}

Classification rules:
- If it's breaking/major news → "عاجل" and is_breaking=true
- Classify accurately from the content"""

    try:
        response = _model.generate_content(prompt)
        result = json.loads(response.text)

        # Validate category
        if result.get("category") not in config.CATEGORIES:
            result["category"] = "منوعات"

        # Generate similarity hash from keywords
        keywords = result.get("keywords", [])
        kw_str = " ".join(sorted(keywords)).lower()
        result["similarity_hash"] = hashlib.md5(kw_str.encode("utf-8")).hexdigest()[:16]

        return result
    except Exception as e:
        logger.error(f"NLP single article error: {e}")
        return None


async def process_batch(articles: List[dict]) -> List[dict | None]:
    """
    Process a batch of up to 5 articles in one Gemini call.
    Each article: {"title": ..., "content": ..., "lang": "en"/"ar"}
    Returns list of processed results (same order, None for failures).
    """
    if len(articles) <= 2:
        # For small batches, process individually (more reliable)
        results = []
        for art in articles:
            r = await process_single_article(
                art["title"], art["content"], art.get("lang", "en")
            )
            results.append(r)
            await asyncio.sleep(0.5)
        return results

    # Build batch prompt
    articles_text = ""
    for i, art in enumerate(articles):
        articles_text += f"""
--- Article {i + 1} (lang: {art.get("lang", "en")}) ---
Title: {art["title"]}
Content: {art["content"][:800]}
"""

    prompt = f"""You are a professional news editor. Process these {len(articles)} articles.
For each article, provide:
- title_ar: Arabic headline (translate if English, improve if Arabic)
- summary_ar: 2-3 sentence Arabic summary (compress 10 lines into 3)
- category: one of [{CATEGORIES_LIST}]
- keywords: 3 Arabic keywords
- is_breaking: true only for major breaking news

{articles_text}

Return ONLY a JSON array with {len(articles)} objects, in the same order as the articles.
Each object has: title_ar, summary_ar, category, keywords, is_breaking"""

    try:
        response = _model.generate_content(prompt)
        results_raw = json.loads(response.text)

        if not isinstance(results_raw, list):
            results_raw = [results_raw]

        processed = []
        for i, r in enumerate(results_raw):
            if not r:
                processed.append(None)
                continue

            if r.get("category") not in config.CATEGORIES:
                r["category"] = "منوعات"

            keywords = r.get("keywords", [])
            kw_str = " ".join(sorted(keywords)).lower()
            r["similarity_hash"] = hashlib.md5(kw_str.encode("utf-8")).hexdigest()[:16]
            processed.append(r)

        # Pad with None if results are fewer than articles
        while len(processed) < len(articles):
            processed.append(None)

        return processed

    except Exception as e:
        logger.error(f"NLP batch error: {e}. Falling back to individual processing.")
        # Fallback: process individually
        results = []
        for art in articles:
            r = await process_single_article(
                art["title"], art["content"], art.get("lang", "en")
            )
            results.append(r)
            await asyncio.sleep(0.5)
        return results


async def generate_article(
    title_ar: str, summary_ar: str, source_name: str
) -> str | None:
    """Generate a full article in Arabic from title and summary."""
    # Use a fresh model WITHOUT JSON response_mime_type
    model_text = genai.GenerativeModel(config.GEMINI_MODEL)

    prompt = f"""أنت صحفي محترف. اكتب مقالاً إخبارياً قصيراً باللغة العربية الفصحى.

المقال يجب أن يكون:
- بين 150 و 250 كلمة
- يبدأ بعنوان جذاب (مختلف عن العنوان الأصلي)
- يتضمن: مقدمة، تفاصيل أساسية (من؟ ماذا؟ لماذا يهم؟)، خاتمة تحليلية قصيرة
- بأسلوب إخباري احترافي
- لا تستخدم JSON، اكتب نصاً عادياً فقط

عنوان الخبر: {title_ar}
ملخص الخبر: {summary_ar}
المصدر: {source_name}"""

    for attempt in range(2):
        try:
            response = model_text.generate_content(prompt)

            # Check for safety blocks
            if not response.candidates:
                logger.warning(
                    f"Article generation blocked (no candidates): {title_ar[:50]}"
                )
                if hasattr(response, "prompt_feedback"):
                    logger.warning(f"Prompt feedback: {response.prompt_feedback}")
                return None

            candidate = response.candidates[0]
            if candidate.finish_reason and candidate.finish_reason.name == "SAFETY":
                logger.warning(f"Article blocked by safety filter: {title_ar[:50]}")
                return None

            text = response.text.strip() if response.text else ""
            if not text:
                logger.warning(
                    f"Article generation returned empty text: {title_ar[:50]}"
                )
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                return None

            logger.info(
                f"Article generated successfully ({len(text)} chars): {title_ar[:40]}"
            )
            return text

        except Exception as e:
            logger.error(f"Error generating article (attempt {attempt + 1}): {e}")
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            return None

    return None
