import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "omochao.db"

_conn: sqlite3.Connection | None = None
GLOBAL_LIGHT_SCOPE = "global"


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH))
        _conn.row_factory = sqlite3.Row
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT NOT NULL,
                fire_at REAL NOT NULL,
                flash INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL
            )
        """)
        _ensure_reminders_schema(_conn)
        _ensure_rss_tables(_conn)
        _conn.commit()
    return _conn


def _ensure_reminders_schema(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(reminders)").fetchall()
    }
    if "guild_id" not in columns:
        conn.execute("ALTER TABLE reminders ADD COLUMN guild_id TEXT")
    if "light_entity_id" not in columns:
        conn.execute("ALTER TABLE reminders ADD COLUMN light_entity_id TEXT")


def add_reminder(
    user_id: str,
    message: str,
    fire_at: float,
    flash: bool,
    guild_id: int | str | None = None,
    light_entity_id: str | None = None,
) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """
        INSERT INTO reminders (user_id, message, fire_at, flash, created_at, guild_id, light_entity_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            message,
            fire_at,
            int(flash),
            time.time(),
            None if guild_id is None else str(guild_id),
            light_entity_id,
        ),
    )
    conn.commit()
    return cur.lastrowid


def delete_reminder(reminder_id: int) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()


def get_pending_reminders() -> list[sqlite3.Row]:
    conn = _get_conn()
    return conn.execute(
        "SELECT id, user_id, message, fire_at, flash, guild_id, light_entity_id FROM reminders ORDER BY fire_at"
    ).fetchall()


def get_pending_reminders_for_user(user_id: int | str) -> list[sqlite3.Row]:
    conn = _get_conn()
    return conn.execute(
        """
        SELECT id, user_id, message, fire_at, flash, guild_id, light_entity_id
        FROM reminders
        WHERE user_id = ?
        ORDER BY fire_at
        """,
        (str(user_id),),
    ).fetchall()


def _ensure_rss_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rss_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            feed_url TEXT NOT NULL,
            title TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(guild_id, channel_id, feed_url)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rss_seen_items (
            subscription_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            seen_at REAL NOT NULL,
            PRIMARY KEY (subscription_id, item_key),
            FOREIGN KEY (subscription_id) REFERENCES rss_subscriptions(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def add_rss_subscription(
    guild_id: int | str,
    channel_id: int | str,
    feed_url: str,
    title: str,
    created_by: int | str,
) -> int:
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """
        INSERT INTO rss_subscriptions (guild_id, channel_id, feed_url, title, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, channel_id, feed_url) DO UPDATE SET
            title = excluded.title,
            updated_at = excluded.updated_at
        """,
        (str(guild_id), str(channel_id), feed_url, title, str(created_by), now, now),
    )
    conn.commit()
    row = conn.execute(
        """
        SELECT id FROM rss_subscriptions
        WHERE guild_id = ? AND channel_id = ? AND feed_url = ?
        """,
        (str(guild_id), str(channel_id), feed_url),
    ).fetchone()
    return int(row["id"])


def list_rss_subscriptions(guild_id: int | str) -> list[sqlite3.Row]:
    conn = _get_conn()
    return conn.execute(
        """
        SELECT id, guild_id, channel_id, feed_url, title, created_by, created_at, updated_at
        FROM rss_subscriptions
        WHERE guild_id = ?
        ORDER BY title, id
        """,
        (str(guild_id),),
    ).fetchall()


def list_all_rss_subscriptions() -> list[sqlite3.Row]:
    conn = _get_conn()
    return conn.execute(
        """
        SELECT id, guild_id, channel_id, feed_url, title, created_by, created_at, updated_at
        FROM rss_subscriptions
        ORDER BY id
        """
    ).fetchall()


def get_rss_subscription(guild_id: int | str, subscription_id: int) -> sqlite3.Row | None:
    conn = _get_conn()
    return conn.execute(
        """
        SELECT id, guild_id, channel_id, feed_url, title, created_by, created_at, updated_at
        FROM rss_subscriptions
        WHERE guild_id = ? AND id = ?
        """,
        (str(guild_id), subscription_id),
    ).fetchone()


def remove_rss_subscription(guild_id: int | str, subscription_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM rss_subscriptions WHERE guild_id = ? AND id = ?",
        (str(guild_id), subscription_id),
    )
    conn.execute(
        "DELETE FROM rss_seen_items WHERE subscription_id = ?",
        (subscription_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def get_seen_rss_item_keys(subscription_id: int, item_keys: list[str]) -> set[str]:
    if not item_keys:
        return set()
    conn = _get_conn()
    placeholders = ",".join("?" for _ in item_keys)
    rows = conn.execute(
        f"""
        SELECT item_key FROM rss_seen_items
        WHERE subscription_id = ? AND item_key IN ({placeholders})
        """,
        [subscription_id, *item_keys],
    ).fetchall()
    return {str(row["item_key"]) for row in rows}


def mark_rss_items_seen(subscription_id: int, item_keys: list[str]) -> None:
    if not item_keys:
        return
    conn = _get_conn()
    now = time.time()
    conn.executemany(
        """
        INSERT OR IGNORE INTO rss_seen_items (subscription_id, item_key, seen_at)
        VALUES (?, ?, ?)
        """,
        [(subscription_id, item_key, now) for item_key in item_keys],
    )
    conn.commit()


def _ensure_user_default_lights_table() -> None:
    conn = _get_conn()
    existing = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'user_default_lights'"
    ).fetchone()
    if existing is not None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(user_default_lights)").fetchall()
        }
        if "guild_id" not in columns:
            conn.execute("ALTER TABLE user_default_lights RENAME TO user_default_lights_legacy")
            conn.execute("""
                CREATE TABLE user_default_lights (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)
            conn.commit()
            return

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_default_lights (
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    conn.commit()


def _light_scope(guild_id: int | str | None) -> str:
    return GLOBAL_LIGHT_SCOPE if guild_id is None else str(guild_id)


def get_user_default_light_for_scope(guild_id: int | str | None, user_id: int | str) -> str | None:
    _ensure_user_default_lights_table()
    conn = _get_conn()
    row = conn.execute(
        "SELECT entity_id FROM user_default_lights WHERE guild_id = ? AND user_id = ?",
        (_light_scope(guild_id), str(user_id)),
    ).fetchone()
    return None if row is None else row["entity_id"]


def get_user_default_light(guild_id: int | str | None, user_id: int | str) -> str | None:
    if guild_id is not None:
        entity_id = get_user_default_light_for_scope(guild_id, user_id)
        if entity_id is not None:
            return entity_id
    return get_user_default_light_for_scope(None, user_id)


def set_user_default_light(guild_id: int | str | None, user_id: int | str, entity_id: str) -> None:
    _ensure_user_default_lights_table()
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """
        INSERT INTO user_default_lights (guild_id, user_id, entity_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            entity_id = excluded.entity_id,
            updated_at = excluded.updated_at
        """,
        (_light_scope(guild_id), str(user_id), entity_id, now, now),
    )
    conn.commit()


def clear_user_default_light(guild_id: int | str | None, user_id: int | str) -> None:
    _ensure_user_default_lights_table()
    conn = _get_conn()
    conn.execute(
        "DELETE FROM user_default_lights WHERE guild_id = ? AND user_id = ?",
        (_light_scope(guild_id), str(user_id)),
    )
    conn.commit()


def _ensure_module_access_table() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS module_role_restrictions (
            guild_id TEXT NOT NULL,
            module TEXT NOT NULL,
            role_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (guild_id, module, role_id)
        )
    """)
    conn.commit()


def get_module_role_ids(guild_id: int, module: str) -> set[int]:
    _ensure_module_access_table()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role_id FROM module_role_restrictions WHERE guild_id = ? AND module = ? ORDER BY role_id",
        (str(guild_id), module),
    ).fetchall()
    return {int(row["role_id"]) for row in rows}


def get_all_module_role_ids(guild_id: int) -> dict[str, set[int]]:
    _ensure_module_access_table()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT module, role_id FROM module_role_restrictions WHERE guild_id = ? ORDER BY module, role_id",
        (str(guild_id),),
    ).fetchall()
    rules: dict[str, set[int]] = {}
    for row in rows:
        rules.setdefault(row["module"], set()).add(int(row["role_id"]))
    return rules


def set_module_role_ids(guild_id: int, module: str, role_ids: list[int]) -> None:
    _ensure_module_access_table()
    conn = _get_conn()
    conn.execute(
        "DELETE FROM module_role_restrictions WHERE guild_id = ? AND module = ?",
        (str(guild_id), module),
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO module_role_restrictions (guild_id, module, role_id, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [(str(guild_id), module, str(role_id), time.time()) for role_id in role_ids],
    )
    conn.commit()
