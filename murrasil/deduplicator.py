"""
deduplicator.py — كشف التكرار ودمج القصص
ثلاث مراحل: URL → Title Similarity → Content Hash
"""

import logging
import uuid
from difflib import SequenceMatcher
from datetime import datetime, timezone

from database import get_db_connection
from config import config

logger = logging.getLogger(__name__)


def compute_title_similarity(title1: str, title2: str) -> float:
    """Compute similarity between two titles using SequenceMatcher."""
    if not title1 or not title2:
        return 0.0
    return SequenceMatcher(None, title1.strip(), title2.strip()).ratio()


def find_similar_articles(title_ar: str, similarity_hash: str, category: str) -> str | None:
    """
    Find if a similar article already exists. Returns cluster_id if found, None otherwise.

    Strategy:
    1. Check similarity_hash match (same keywords) → high confidence
    2. Check title similarity > threshold → medium confidence
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Phase 1: Hash match (same keywords = very likely same story)
    if similarity_hash:
        cursor.execute(
            "SELECT id, title_ar, cluster_id FROM news WHERE similarity_hash = ? AND status = 'new' LIMIT 5",
            (similarity_hash,)
        )
        hash_matches = cursor.fetchall()
        if hash_matches:
            for match in hash_matches:
                sim = compute_title_similarity(title_ar, match['title_ar'])
                if sim > 0.5:  # Even low similarity with same hash = same story
                    conn.close()
                    return match['cluster_id'] or _create_cluster(match['id'])

    # Phase 2: Title similarity within same category (last 48 hours)
    cursor.execute(
        """SELECT id, title_ar, cluster_id FROM news
           WHERE category = ? AND status = 'new'
           AND datetime(fetched_at) > datetime('now', '-2 days')
           LIMIT 50""",
        (category,)
    )
    recent = cursor.fetchall()
    conn.close()

    for item in recent:
        sim = compute_title_similarity(title_ar, item['title_ar'])
        if sim >= config.SIMILARITY_THRESHOLD:
            logger.info(f"Duplicate detected (sim={sim:.2f}): '{title_ar[:40]}...' ≈ '{item['title_ar'][:40]}...'")
            return item['cluster_id'] or _create_cluster(item['id'])

    return None


def _create_cluster(news_id: str) -> str:
    """Create a new cluster for an existing article and return the cluster_id."""
    cluster_id = f"cl_{uuid.uuid4().hex[:12]}"
    conn = get_db_connection()
    cursor = conn.cursor()

    # Update the original article
    cursor.execute("UPDATE news SET cluster_id = ? WHERE id = ?", (cluster_id, news_id))

    # Add to clusters table
    cursor.execute(
        "INSERT INTO news_clusters (cluster_id, news_id, similarity_score) VALUES (?, ?, ?)",
        (cluster_id, news_id, 1.0)
    )
    conn.commit()
    conn.close()
    return cluster_id


def add_to_cluster(cluster_id: str, news_id: str, similarity_score: float):
    """Add an article to an existing cluster."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE news SET cluster_id = ? WHERE id = ?", (cluster_id, news_id))
    cursor.execute(
        "INSERT INTO news_clusters (cluster_id, news_id, similarity_score) VALUES (?, ?, ?)",
        (cluster_id, news_id, similarity_score)
    )
    conn.commit()
    conn.close()


def get_cluster_articles(cluster_id: str) -> list[dict]:
    """Get all articles in a cluster."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM news WHERE cluster_id = ? ORDER BY published_at DESC",
        (cluster_id,)
    )
    articles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return articles


def run_deduplication_pass():
    """
    Run a full deduplication pass on recent 'new' articles.
    Called periodically by the scheduler.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT id, title_ar, similarity_hash, category, cluster_id FROM news
           WHERE status = 'new' AND cluster_id IS NULL
           AND datetime(fetched_at) > datetime('now', '-2 days')
           ORDER BY fetched_at DESC"""
    )
    unclustered = [dict(row) for row in cursor.fetchall()]
    conn.close()

    clusters_formed = 0

    for i, article in enumerate(unclustered):
        if article.get('cluster_id'):
            continue  # Already clustered in this pass

        for j in range(i + 1, len(unclustered)):
            other = unclustered[j]
            if other.get('cluster_id'):
                continue

            sim = compute_title_similarity(article['title_ar'], other['title_ar'])
            if sim >= config.SIMILARITY_THRESHOLD:
                # Create or join cluster
                cid = article.get('cluster_id')
                if not cid:
                    cid = _create_cluster(article['id'])
                    article['cluster_id'] = cid

                add_to_cluster(cid, other['id'], sim)
                other['cluster_id'] = cid
                unclustered[j] = other
                clusters_formed += 1

    logger.info(f"Deduplication pass: formed {clusters_formed} new cluster links.")
    return clusters_formed
