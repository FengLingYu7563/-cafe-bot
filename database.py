"""SQLite 資料存取層。

所有頻道/成員資料的唯一入口，cog 只 import 這裡的函式，不直接碰 connection。
連線是模組層級單例 + threading.Lock，資料量極小，同步 I/O 不會明顯阻塞 event loop。
"""

import logging
import pathlib
import sqlite3
import threading
from datetime import datetime, timezone

import config

logger = logging.getLogger("aocafe.database")

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS channels (
    channel_id   INTEGER PRIMARY KEY,
    guild_id     INTEGER NOT NULL,
    owner_id     INTEGER NOT NULL,
    channel_type TEXT    NOT NULL CHECK (channel_type IN ('text', 'voice')),
    name         TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    archived     INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    archived_at  TEXT,
    archived_by  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_channels_owner
    ON channels (guild_id, owner_id, archived);
CREATE INDEX IF NOT EXISTS idx_channels_guild_archived
    ON channels (guild_id, archived);

CREATE TABLE IF NOT EXISTS channel_members (
    channel_id INTEGER NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,
    added_by   INTEGER NOT NULL,
    added_at   TEXT    NOT NULL,
    PRIMARY KEY (channel_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_members_channel
    ON channel_members (channel_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """建立 data 目錄、開連線、跑建表 DDL。由 main.py 的 setup_hook 呼叫一次。"""
    global _conn
    db_path = pathlib.Path(config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _lock:
        _conn.executescript(_SCHEMA)
        _conn.commit()
    logger.info("資料庫已就緒：%s", db_path)


def close_db() -> None:
    global _conn
    if _conn is not None:
        with _lock:
            _conn.close()
        _conn = None


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("資料庫尚未初始化，請先呼叫 init_db()")
    return _conn


# ---------- channels ----------

def add_channel(channel_id: int, guild_id: int, owner_id: int,
                 channel_type: str, name: str) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            """
            INSERT OR REPLACE INTO channels
                (channel_id, guild_id, owner_id, channel_type, name,
                 created_at, archived, archived_at, archived_by)
            VALUES (?, ?, ?, ?, ?, ?, 0, NULL, NULL)
            """,
            (channel_id, guild_id, owner_id, channel_type, name, _now()),
        )
        conn.commit()


def get_channel(channel_id: int) -> sqlite3.Row | None:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT * FROM channels WHERE channel_id = ?", (channel_id,)
        )
        return cur.fetchone()


def archive_channel(channel_id: int, archived_by: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            """
            UPDATE channels
            SET archived = 1, archived_at = ?, archived_by = ?
            WHERE channel_id = ?
            """,
            (_now(), archived_by, channel_id),
        )
        conn.commit()


def count_active_channels(guild_id: int, owner_id: int, channel_type: str) -> list[int]:
    """回傳該使用者在該 guild 未廢棄的該型別頻道 ID 清單。

    回傳清單而非數量，讓呼叫端能逐一確認頻道在 Discord 上是否還存在
    （管理員可能已手動真刪除），過濾殘留紀錄後再計數，確保額度計算正確。
    """
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            """
            SELECT channel_id FROM channels
            WHERE guild_id = ? AND owner_id = ? AND channel_type = ? AND archived = 0
            """,
            (guild_id, owner_id, channel_type),
        )
        return [row["channel_id"] for row in cur.fetchall()]


def list_channels_by_owner(guild_id: int, owner_id: int,
                            include_archived: bool = False) -> list[sqlite3.Row]:
    conn = _get_conn()
    sql = "SELECT * FROM channels WHERE guild_id = ? AND owner_id = ?"
    params: list = [guild_id, owner_id]
    if not include_archived:
        sql += " AND archived = 0"
    sql += " ORDER BY created_at ASC"
    with _lock:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def list_all_channels(guild_id: int, include_archived: bool = False) -> list[sqlite3.Row]:
    conn = _get_conn()
    sql = "SELECT * FROM channels WHERE guild_id = ?"
    params: list = [guild_id]
    if not include_archived:
        sql += " AND archived = 0"
    sql += " ORDER BY created_at ASC"
    with _lock:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def delete_channel_record(channel_id: int) -> None:
    """硬刪除紀錄，僅供清理 Discord 上已不存在的殘留 row（CASCADE 一併清成員）。"""
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        conn.commit()


# ---------- channel_members ----------

def add_member(channel_id: int, user_id: int, added_by: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id),
        )
        if cur.fetchone() is not None:
            return False
        conn.execute(
            """
            INSERT INTO channel_members (channel_id, user_id, added_by, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (channel_id, user_id, added_by, _now()),
        )
        conn.commit()
        return True


def remove_member(channel_id: int, user_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0


def is_member(channel_id: int, user_id: int) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "SELECT 1 FROM channel_members WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id),
        )
        return cur.fetchone() is not None


def list_members(channel_id: int) -> list[int]:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            """
            SELECT user_id FROM channel_members
            WHERE channel_id = ?
            ORDER BY added_at ASC
            """,
            (channel_id,),
        )
        return [row["user_id"] for row in cur.fetchall()]


def clear_members(channel_id: int) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM channel_members WHERE channel_id = ?", (channel_id,))
        conn.commit()
