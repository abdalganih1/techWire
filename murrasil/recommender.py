"""
recommender.py — نظام التوصيات بالفلترة التعاونية
ترتيب الأخبار بناءً على اهتمامات المستخدم
"""

import logging
from datetime import datetime, timezone
from database import get_db_connection

logger = logging.getLogger(__name__)


def record_interaction(news_id: str, action: str, dwell_time: int = 0):
    """Record a user interaction for recommendation learning."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO interactions (news_id, action, timestamp, dwell_time) VALUES (?, ?, ?, ?)",
        (news_id, action, now, dwell_time)
    )
    conn.commit()
    conn.close()


def update_preference_weights():
    """
    Learn from user interactions and update category weights.
    Called periodically by the scheduler.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Count interactions per category
    cursor.execute("""
        SELECT n.category,
               SUM(CASE WHEN i.action = 'approve' THEN 2
                        WHEN i.action = 'read' THEN 1
                        WHEN i.action = 'listen' THEN 1.5
                        WHEN i.action = 'reject' THEN -1
                        ELSE 0 END) as score,
               COUNT(*) as total
        FROM interactions i
        JOIN news n ON i.news_id = n.id
        WHERE n.category IS NOT NULL
        GROUP BY n.category
    """)

    category_scores = {}
    for row in cursor.fetchall():
        cat = row['category']
        score = row['score'] or 0
        total = row['total'] or 1
        # Normalize: base 1.0 + learned adjustment (capped between 0.2 and 3.0)
        weight = max(0.2, min(3.0, 1.0 + (score / total)))
        category_scores[cat] = weight

    # Update preferences
    for cat, weight in category_scores.items():
        cursor.execute(
            """INSERT INTO user_preferences (category, weight)
               VALUES (?, ?)
               ON CONFLICT(category) DO UPDATE SET weight = ?""",
            (cat, weight, weight)
        )

    conn.commit()
    conn.close()
    logger.info(f"Updated preference weights: {category_scores}")


def get_recommended_news(status: str = 'new', page: int = 1, limit: int = 20,
                         category: str = None, source: str = None,
                         q: str = None, sort: str = 'smart') -> dict:
    """
    Get news sorted by recommendation score.

    Score = (category_weight × 2) + (recency × 1) - (read_count × 0.5)

    sort options: 'smart' (recommended), 'desc' (newest), 'asc' (oldest)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    offset = (page - 1) * limit

    # Get current preferences
    cursor.execute("SELECT category, weight FROM user_preferences")
    pref_map = {row['category']: row['weight'] for row in cursor.fetchall()}

    # Build query
    where_clauses = ["n.status = ?"]
    params = [status]

    if q:
        where_clauses.append("(n.title_ar LIKE ? OR n.summary_ar LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if category:
        where_clauses.append("n.category = ?")
        params.append(category)

    if source:
        where_clauses.append("n.source_name = ?")
        params.append(source)

    where_sql = " AND ".join(where_clauses)

    if sort == 'smart':
        # Smart scoring: deduped representative articles ranked by preference
        # We pick the first article per cluster (or unclustered articles)
        query = f"""
            SELECT n.*,
                CASE
                    WHEN n.cluster_id IS NOT NULL THEN (
                        SELECT COUNT(*) FROM news_clusters nc WHERE nc.cluster_id = n.cluster_id
                    )
                    ELSE 1
                END as cluster_size
            FROM news n
            WHERE {where_sql}
            AND (
                n.cluster_id IS NULL
                OR n.id = (
                    SELECT n2.id FROM news n2
                    WHERE n2.cluster_id = n.cluster_id
                    ORDER BY n2.published_at DESC LIMIT 1
                )
            )
            ORDER BY n.published_at DESC
            LIMIT ? OFFSET ?
        """
    else:
        direction = "ASC" if sort == 'asc' else "DESC"
        query = f"""
            SELECT n.*,
                CASE
                    WHEN n.cluster_id IS NOT NULL THEN (
                        SELECT COUNT(*) FROM news_clusters nc WHERE nc.cluster_id = n.cluster_id
                    )
                    ELSE 1
                END as cluster_size
            FROM news n
            WHERE {where_sql}
            ORDER BY n.published_at {direction}
            LIMIT ? OFFSET ?
        """

    cursor.execute(query, params + [limit, offset])
    rows = [dict(row) for row in cursor.fetchall()]

    # Calculate recommendation scores and sort (for 'smart' mode)
    if sort == 'smart':
        for row in rows:
            cat_weight = pref_map.get(row.get('category', ''), 1.0)
            read_penalty = (row.get('read_count', 0) or 0) * 0.3
            cluster_bonus = min((row.get('cluster_size', 1) or 1) - 1, 3) * 0.5  # More sources = more important
            row['_score'] = (cat_weight * 2.0) + cluster_bonus - read_penalty

        rows.sort(key=lambda x: x.get('_score', 0), reverse=True)

    # Count total
    count_query = f"SELECT COUNT(*) FROM news n WHERE {where_sql}"
    if sort == 'smart':
        count_query = f"""
            SELECT COUNT(*) FROM news n
            WHERE {where_sql}
            AND (n.cluster_id IS NULL OR n.id = (
                SELECT n2.id FROM news n2
                WHERE n2.cluster_id = n.cluster_id
                ORDER BY n2.published_at DESC LIMIT 1
            ))
        """
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]

    conn.close()
    return {"data": rows, "total": total, "page": page, "limit": limit}
