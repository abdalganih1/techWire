import logging
from openai import AsyncOpenAI
from config import config

logger = logging.getLogger(__name__)

base_url = None if "gpt" in config.AI_MODEL.lower() else "http://localhost:11434/v1"
client = AsyncOpenAI(
    api_key=config.OPENAI_API_KEY or "ollama",
    base_url=base_url 
)

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
        response = await client.chat.completions.create(
            model=config.AI_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating article: {e}")
        return None
