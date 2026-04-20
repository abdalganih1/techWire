"""
notifier.py — نظام الإشعارات
إشعارات داخلية بناءً على تفضيلات المستخدم
"""

import logging
from datetime import datetime, timezone
from database import get_db_connection

logger = logging.getLogger(__name__)


def check_and_notify(news_id: str, title_ar: str, category: str):
    """
    Check if new article matches user notification preferences.
    If so, create an in-app notification.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if category has notifications enabled
    cursor.execute(
        "SELECT notify FROM user_preferences WHERE category = ?", (category,)
    )
    pref = cursor.fetchone()

    if pref and pref["notify"]:
        now = datetime.now(timezone.utc).isoformat()
        body = f"خبر جديد في قسم {category}"
        cursor.execute(
            """INSERT INTO notifications (title, body, news_id, category, read, created_at)
               VALUES (?, ?, ?, ?, 0, ?)""",
            (title_ar, body, news_id, category, now),
        )
        conn.commit()
        logger.info(f"Notification created for: {title_ar[:50]}")

    conn.close()


def get_notifications(limit: int = 50, unread_only: bool = False) -> list[dict]:
    """Get recent notifications."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM notifications"
    if unread_only:
        query += " WHERE read = 0"
    query += " ORDER BY created_at DESC LIMIT ?"

    cursor.execute(query, (limit,))
    notifs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return notifs


def get_unread_count() -> int:
    """Get count of unread notifications."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE read = 0")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def mark_all_read():
    """Mark all notifications as read."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read = 1 WHERE read = 0")
    conn.commit()
    conn.close()


def mark_read(notification_id: int):
    """Mark a single notification as read."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def cleanup_old_notifications(days: int = 7):
    """Remove notifications older than N days."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM notifications WHERE datetime(created_at) < datetime('now', ? || ' days')",
        (f"-{int(days)}",),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted:
        logger.info(f"Cleaned up {deleted} old notifications.")
    return deleted
