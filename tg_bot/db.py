import aiosqlite
from datetime import datetime, timezone

_db: aiosqlite.Connection | None = None


async def init_db(path: str = "tg_bot/bot.sqlite3") -> None:
    global _db
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id       INTEGER PRIMARY KEY,
            backend_user_id TEXT NOT NULL,
            conversation_id TEXT,
            agent_mode  TEXT NOT NULL DEFAULT 'auto',
            created_at  TEXT NOT NULL
        )
    """)
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def get_user(tg_id: int) -> dict | None:
    assert _db is not None
    async with _db.execute(
        "SELECT * FROM users WHERE tg_id = ?", (tg_id,)
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        return dict(row)


async def save_user(tg_id: int, backend_user_id: str) -> None:
    assert _db is not None
    now = datetime.now(timezone.utc).isoformat()
    await _db.execute(
        "INSERT OR REPLACE INTO users (tg_id, backend_user_id, agent_mode, created_at) "
        "VALUES (?, ?, 'auto', ?)",
        (tg_id, backend_user_id, now),
    )
    await _db.commit()


async def set_conversation_id(tg_id: int, conversation_id: str | None) -> None:
    assert _db is not None
    await _db.execute(
        "UPDATE users SET conversation_id = ? WHERE tg_id = ?",
        (conversation_id, tg_id),
    )
    await _db.commit()


async def reset_conversation(tg_id: int) -> None:
    await set_conversation_id(tg_id, None)


async def set_agent_mode(tg_id: int, mode: str) -> None:
    assert _db is not None
    await _db.execute(
        "UPDATE users SET agent_mode = ? WHERE tg_id = ?",
        (mode, tg_id),
    )
    await _db.commit()
