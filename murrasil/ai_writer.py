import logging
import os
import google.generativeai as genai
from config import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

async def generate_article(title_ar, summary_ar, source_name):
    prompt = f"""أنت صحفي تقني محترف. اكتب مقالاً إخبارياً قصيراً باللغة العربية الفصحى عن الخبر التالي.

المقال يجب أن يكون:
- بين 150 و 250 كلمة
- يبدأ بعنوان جذاب (مختلف عن العنوان الأصلي)
- يتضمن: مقدمة، تفاصيل أساسية (من؟ ماذا؟ لماذا يهم؟)، خاتمة تحليلية قصيرة
- بأسلوب إخباري احترافي

عنوان الخبر: {title_ar}
ملخص الخبر: {summary_ar}
المصدر: {source_name}"""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error generating article: {e}")
        return None
