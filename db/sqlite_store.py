import json
import os
import sqlite3
from datetime import timezone

DB_FILE = "db.sqlite"


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events (occurred_at)"
    )
    conn.commit()
    conn.close()


def insert_event(event):
    conn = get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO events (
            id, type, occurred_at, source, category,
            payload_json, tags_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["id"],
            event["type"],
            event["occurred_at"],
            event["source"],
            event["category"],
            json.dumps(event.get("payload", {}), ensure_ascii=False),
            json.dumps(event.get("tags", []), ensure_ascii=False),
            event["created_at"],
        )
    )
    conn.commit()
    conn.close()


def row_to_event(row):
    payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
    tags = json.loads(row["tags_json"]) if row["tags_json"] else []
    return {
        "id": row["id"],
        "type": row["type"],
        "occurred_at": row["occurred_at"],
        "source": row["source"],
        "category": row["category"],
        "payload": payload,
        "tags": tags,
        "created_at": row["created_at"],
    }


def fetch_recent_events(limit, since_dt=None):
    conn = get_conn()
    if since_dt:
        since_iso = (
            since_dt.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        rows = conn.execute(
            """
            SELECT * FROM events
            WHERE occurred_at >= ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (since_iso, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM events
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    conn.close()
    return [row_to_event(row) for row in rows]


def fetch_events_since(cutoff_dt):
    cutoff_iso = (
        cutoff_dt.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM events
        WHERE occurred_at >= ?
        ORDER BY occurred_at DESC
        """,
        (cutoff_iso,)
    ).fetchall()
    conn.close()
    return [row_to_event(row) for row in rows]


def get_event_by_id(event_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM events WHERE id = ?",
        (event_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return row_to_event(row)


def update_event_payload(event_id, payload):
    conn = get_conn()
    conn.execute(
        """
        UPDATE events
        SET payload_json = ?
        WHERE id = ?
        """,
        (json.dumps(payload, ensure_ascii=False), event_id)
    )
    conn.commit()
    conn.close()


def migrate_events_from_memory(memory_file):
    if not os.path.exists(memory_file):
        return 0
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return 0
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return 0
    events = data.get("events", [])
    if not events:
        return 0
    conn = get_conn()
    count = 0
    for event in events:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO events (
                id, type, occurred_at, source, category,
                payload_json, tags_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("id"),
                event.get("type", "manual"),
                event.get("occurred_at"),
                event.get("source", "parent"),
                event.get("category", "unknown"),
                json.dumps(event.get("payload", {}), ensure_ascii=False),
                json.dumps(event.get("tags", []), ensure_ascii=False),
                event.get("created_at") or event.get("occurred_at"),
            )
        )
        if cursor.rowcount and cursor.rowcount > 0:
            count += cursor.rowcount
    conn.commit()
    conn.close()
    return count
