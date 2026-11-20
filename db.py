"""SQLite storage. All times are Unix timestamps (seconds since 1970, UTC)."""
import time

import aiosqlite

DB_PATH = "tracker.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY,
    tracking  INTEGER NOT NULL DEFAULT 0,    -- 1 = opted in
    reminder_channel INTEGER                 -- channel to post reminders in, NULL = off
);
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    kind       TEXT NOT NULL,                -- 'voice' or 'game'
    name       TEXT,                         -- channel name or game name
    started_at REAL NOT NULL,
    ended_at   REAL                          -- NULL while still running
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id, kind);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_db: aiosqlite.Connection


async def connect():
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    await _db.executescript(SCHEMA)
    # Upgrade databases created by older versions of the bot.
    async with _db.execute("PRAGMA table_info(users)") as cur:
        columns = [row[1] for row in await cur.fetchall()]
    if "reminder_channel" not in columns:
        await _db.execute("ALTER TABLE users ADD COLUMN reminder_channel INTEGER")
    if "reminders" in columns:  # replaced by reminder_channel
        await _db.execute("ALTER TABLE users DROP COLUMN reminders")
    await _db.commit()


# --- Opt-in ---

async def is_tracking(user_id: int) -> bool:
    async with _db.execute("SELECT tracking FROM users WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])


async def set_tracking(user_id: int, on: bool):
    await _db.execute(
        "INSERT INTO users (user_id, tracking) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET tracking = excluded.tracking",
        (user_id, int(on)),
    )
    await _db.commit()


async def tracked_users() -> list[int]:
    async with _db.execute("SELECT user_id FROM users WHERE tracking = 1") as cur:
        return [row[0] for row in await cur.fetchall()]


# --- Reminders ---

async def reminder_channel(user_id: int) -> int | None:
    async with _db.execute("SELECT reminder_channel FROM users WHERE user_id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def set_reminder_channel(user_id: int, channel_id: int | None):
    """Pass None to turn reminders off."""
    await _db.execute("UPDATE users SET reminder_channel = ? WHERE user_id = ?", (channel_id, user_id))
    await _db.commit()


async def reminder_users() -> list[tuple[int, int]]:
    """(user_id, channel_id) for everyone with tracking and reminders on."""
    async with _db.execute(
        "SELECT user_id, reminder_channel FROM users WHERE tracking = 1 AND reminder_channel IS NOT NULL"
    ) as cur:
        return await cur.fetchall()


# --- Sessions ---

async def start_session(user_id: int, kind: str, name: str):
    """Start a new session, ending any session of the same kind that's still open."""
    now = time.time()
    await _db.execute(
        "UPDATE sessions SET ended_at = ? WHERE user_id = ? AND kind = ? AND ended_at IS NULL",
        (now, user_id, kind),
    )
    await _db.execute(
        "INSERT INTO sessions (user_id, kind, name, started_at) VALUES (?, ?, ?, ?)",
        (user_id, kind, name, now),
    )
    await _db.commit()


async def end_session(user_id: int, kind: str | None = None):
    """End the user's open session of this kind, or all their open sessions if kind is None."""
    if kind is None:
        await _db.execute(
            "UPDATE sessions SET ended_at = ? WHERE user_id = ? AND ended_at IS NULL",
            (time.time(), user_id),
        )
    else:
        await _db.execute(
            "UPDATE sessions SET ended_at = ? WHERE user_id = ? AND kind = ? AND ended_at IS NULL",
            (time.time(), user_id, kind),
        )
    await _db.commit()


async def close_all_open_sessions(at: float):
    """Used on startup: close sessions left open by a crash or shutdown."""
    await _db.execute(
        "UPDATE sessions SET ended_at = MAX(started_at, ?) WHERE ended_at IS NULL", (at,)
    )
    await _db.commit()


# --- Heartbeat (when the bot was last known to be running) ---

async def last_seen() -> float | None:
    async with _db.execute("SELECT value FROM meta WHERE key = 'last_seen'") as cur:
        row = await cur.fetchone()
    return float(row[0]) if row else None


async def set_last_seen(ts: float):
    await _db.execute(
        "INSERT INTO meta (key, value) VALUES ('last_seen', ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (str(ts),),
    )
    await _db.commit()


# --- Stats ---
# Open sessions count up to "now". With `since`, only the part after `since` counts.

async def total_seconds(user_id: int, kind: str, since: float = 0) -> float:
    async with _db.execute(
        """
        SELECT COALESCE(SUM(COALESCE(ended_at, :now) - MAX(started_at, :since)), 0)
        FROM sessions
        WHERE user_id = :uid AND kind = :kind AND COALESCE(ended_at, :now) > :since
        """,
        {"now": time.time(), "since": since, "uid": user_id, "kind": kind},
    ) as cur:
        return (await cur.fetchone())[0]


async def top_games(user_id: int, limit: int) -> list[tuple[str, float]]:
    async with _db.execute(
        """
        SELECT name, SUM(COALESCE(ended_at, :now) - started_at) AS secs
        FROM sessions
        WHERE user_id = :uid AND kind = 'game'
        GROUP BY name ORDER BY secs DESC LIMIT :limit
        """,
        {"now": time.time(), "uid": user_id, "limit": limit},
    ) as cur:
        return await cur.fetchall()


async def leaderboard(kind: str, since: float, limit: int) -> list[tuple[int, float]]:
    """Top opted-in users by time of this kind since `since`."""
    async with _db.execute(
        """
        SELECT s.user_id, SUM(COALESCE(s.ended_at, :now) - MAX(s.started_at, :since)) AS secs
        FROM sessions s
        JOIN users u ON u.user_id = s.user_id AND u.tracking = 1
        WHERE s.kind = :kind AND COALESCE(s.ended_at, :now) > :since
        GROUP BY s.user_id ORDER BY secs DESC LIMIT :limit
        """,
        {"now": time.time(), "since": since, "kind": kind, "limit": limit},
    ) as cur:
        return await cur.fetchall()
