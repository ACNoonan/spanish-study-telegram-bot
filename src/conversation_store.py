"""Lightweight SQLite-backed conversation history store."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone, date

from src.config import CONVERSATION_DB_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationMessage:
    """Represents a stored conversation message."""

    role: str
    content: str


@dataclass(frozen=True)
class CorrectionEntry:
    """Represents a logged correction for analytics."""

    error_type: str
    original_text: str
    corrected_text: str
    explanation: str


@dataclass(frozen=True)
class UserEngagement:
    """Tracks per-user engagement data for scheduling."""

    user_id: str
    timezone: str
    last_user_message_at: Optional[datetime]
    last_bot_message_at: Optional[datetime]
    last_morning_ping_date: Optional[date]
    reengagement_level: int
    in_session_bot_turns: int
    mood_score: float
    last_weather_date: Optional[date]
    last_weather_summary: Optional[str]
    last_checkin_date: Optional[date]
    last_checkin_window: Optional[str]  # e.g., "morning", "midday", "afternoon", "evening", "night"

    @property
    def last_interaction(self) -> Optional[datetime]:
        """Return the most recent interaction timestamp."""
        candidates = [ts for ts in (self.last_user_message_at, self.last_bot_message_at) if ts]
        if not candidates:
            return None
        return max(candidates)


@dataclass(frozen=True)
class UserProfile:
    """User profile with learning level and preferences."""

    user_id: str
    name: Optional[str]
    telegram_username: Optional[str]
    current_level: str
    current_week: int
    preferences: Optional[str]
    created_at: datetime
    updated_at: datetime


class ConversationStore:
    """Manage conversation history for each user using SQLite."""

    def __init__(self, db_path: Path, history_limit: int = 20):
        self.db_path = db_path
        self.history_limit = history_limit
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the database schema if needed."""
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True
            logger.info("ConversationStore initialized at %s", self.db_path)

    def _initialize_sync(self) -> None:
        """Create the database file and tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_user ON conversation_messages (user_id, id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    corrected_text TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    cards_total INTEGER NOT NULL,
                    cards_completed INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    exit_reason TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_corrections_user ON conversation_corrections (user_id, id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_engagement (
                    user_id TEXT PRIMARY KEY,
                    timezone TEXT NOT NULL,
                    last_user_message_at TEXT,
                    last_bot_message_at TEXT,
                    last_morning_ping_date TEXT,
                    reengagement_level INTEGER DEFAULT 0,
                    in_session_bot_turns INTEGER DEFAULT 0,
                    mood_score REAL DEFAULT 0.6,
                    last_weather_date TEXT,
                    last_weather_summary TEXT,
                    last_checkin_date TEXT,
                    last_checkin_window TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    name TEXT,
                    telegram_username TEXT,
                    current_level TEXT DEFAULT 'B1',
                    current_week INTEGER DEFAULT 1,
                    preferences TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_profiles_user ON user_profiles (user_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vocabulary_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    word TEXT NOT NULL,
                    translation TEXT,
                    example TEXT,
                    introduced_week INTEGER,
                    introduced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ease_factor REAL DEFAULT 2.5,
                    interval_days INTEGER DEFAULT 1,
                    repetition_count INTEGER DEFAULT 0,
                    next_review_date TEXT,
                    last_review_date TEXT,
                    UNIQUE(user_id, word)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vocab_user_review ON vocabulary_cards (user_id, next_review_date)"
            )
            conn.commit()

            # Backfill schema for older databases missing new columns
            try:
                cursor = conn.execute("PRAGMA table_info(user_engagement)")
                cols = {row[1] for row in cursor.fetchall()}
                if "in_session_bot_turns" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN in_session_bot_turns INTEGER DEFAULT 0"
                    )
                if "mood_score" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN mood_score REAL DEFAULT 0.6"
                    )
                if "last_weather_date" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN last_weather_date TEXT"
                    )
                if "last_weather_summary" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN last_weather_summary TEXT"
                    )
                if "last_checkin_date" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN last_checkin_date TEXT"
                    )
                if "last_checkin_window" not in cols:
                    conn.execute(
                        "ALTER TABLE user_engagement ADD COLUMN last_checkin_window TEXT"
                    )
                conn.commit()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Schema backfill for user_engagement failed: %s", exc)

    async def append_message(self, user_id: str, role: str, content: str) -> None:
        """Persist a message for a given user."""
        await self.initialize()
        await asyncio.to_thread(self._append_message_sync, user_id, role, content)

    def _append_message_sync(self, user_id: str, role: str, content: str) -> None:
        """Blocking insert executed in a worker thread."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO conversation_messages (user_id, role, content) VALUES (?, ?, ?)",
                    (user_id, role, content),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to append conversation message: %s", exc, exc_info=True)

    async def get_recent_messages(self, user_id: str) -> List[ConversationMessage]:
        """Fetch recent messages for a user in chronological order."""
        await self.initialize()
        rows = await asyncio.to_thread(self._get_recent_messages_sync, user_id)
        return [ConversationMessage(role=row[0], content=row[1]) for row in rows]

    def _get_recent_messages_sync(self, user_id: str):
        """Fetch conversation rows in a blocking context."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT role, content
                    FROM conversation_messages
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (user_id, self.history_limit),
                )
                rows = cursor.fetchall()
                # Rows were fetched in reverse chronological order; reverse them for the LLM
                return list(reversed(rows))
        except Exception as exc:
            logger.error("Failed to fetch conversation history: %s", exc, exc_info=True)
            return []

    async def log_correction(
        self,
        user_id: str,
        correction: CorrectionEntry,
    ) -> None:
        """Persist a correction entry for later analytics."""
        await self.initialize()
        await asyncio.to_thread(self._log_correction_sync, user_id, correction)

    def _log_correction_sync(self, user_id: str, correction: CorrectionEntry) -> None:
        """Blocking insert for correction entries."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO conversation_corrections (
                        user_id,
                        error_type,
                        original_text,
                        corrected_text,
                        explanation
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        correction.error_type,
                        correction.original_text,
                        correction.corrected_text,
                        correction.explanation,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to log correction: %s", exc, exc_info=True)

    async def get_engagement(self, user_id: str) -> Optional[UserEngagement]:
        """Return a single user's engagement row, if present."""
        await self.initialize()
        row = await asyncio.to_thread(self._get_engagement_sync, user_id)
        return row

    def _get_engagement_sync(self, user_id: str) -> Optional[UserEngagement]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM user_engagement WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return self._row_to_engagement(row) if row else None
        except Exception as exc:
            logger.error("Failed to fetch engagement for %s: %s", user_id, exc, exc_info=True)
            return None

    async def record_user_activity(
        self,
        user_id: str,
        timezone_name: str,
        timestamp: datetime,
    ) -> None:
        """Record that the user interacted with the bot."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            last_user_message_at=timestamp,
            reengagement_level=0,
        )

    async def record_bot_activity(
        self,
        user_id: str,
        timezone_name: str,
        timestamp: datetime,
    ) -> None:
        """Record that the bot sent a proactive message."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            last_bot_message_at=timestamp,
        )

    async def mark_morning_ping(
        self,
        user_id: str,
        timezone_name: str,
        ping_date: date,
    ) -> None:
        """Store the last date a morning ping was delivered."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            last_morning_ping_date=ping_date,
        )

    async def update_reengagement_level(
        self,
        user_id: str,
        timezone_name: str,
        level: int,
    ) -> None:
        """Update the inactivity reminder level for the user."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            reengagement_level=level,
        )

    async def get_all_engagements(self) -> List[UserEngagement]:
        """Return engagement records for all known users."""
        await self.initialize()
        rows = await asyncio.to_thread(self._get_all_engagements_sync)
        return rows

    def _ensure_engagement_row(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        timezone_name: str,
    ) -> None:
        """Create a default engagement row if not present."""
        conn.execute(
            """
            INSERT INTO user_engagement (user_id, timezone)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, timezone_name),
        )

    def _update_engagement_sync(
        self,
        user_id: str,
        timezone_name: str,
        last_user_message_at: Optional[datetime] = None,
        last_bot_message_at: Optional[datetime] = None,
        last_morning_ping_date: Optional[date] = None,
        reengagement_level: Optional[int] = None,
        in_session_bot_turns: Optional[int] = None,
        mood_score: Optional[float] = None,
        last_weather_date: Optional[date] = None,
        last_weather_summary: Optional[str] = None,
        last_checkin_date: Optional[date] = None,
        last_checkin_window: Optional[str] = None,
    ) -> None:
        """Update engagement fields for a user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                self._ensure_engagement_row(conn, user_id, timezone_name)
                updates = ["timezone = ?"]
                params: list = [timezone_name]

                if last_user_message_at is not None:
                    updates.append("last_user_message_at = ?")
                    params.append(last_user_message_at.astimezone(timezone.utc).isoformat())

                if last_bot_message_at is not None:
                    updates.append("last_bot_message_at = ?")
                    params.append(last_bot_message_at.astimezone(timezone.utc).isoformat())

                if last_morning_ping_date is not None:
                    updates.append("last_morning_ping_date = ?")
                    params.append(last_morning_ping_date.isoformat())

                if reengagement_level is not None:
                    updates.append("reengagement_level = ?")
                    params.append(reengagement_level)

                if in_session_bot_turns is not None:
                    updates.append("in_session_bot_turns = ?")
                    params.append(in_session_bot_turns)

                if mood_score is not None:
                    updates.append("mood_score = ?")
                    params.append(mood_score)

                if last_weather_date is not None:
                    updates.append("last_weather_date = ?")
                    params.append(last_weather_date.isoformat())

                if last_weather_summary is not None:
                    updates.append("last_weather_summary = ?")
                    params.append(last_weather_summary)

                if last_checkin_date is not None:
                    updates.append("last_checkin_date = ?")
                    params.append(last_checkin_date.isoformat())

                if last_checkin_window is not None:
                    updates.append("last_checkin_window = ?")
                    params.append(last_checkin_window)

                params.append(user_id)
                conn.execute(
                    f"UPDATE user_engagement SET {', '.join(updates)} WHERE user_id = ?",
                    params,
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to update engagement row: %s", exc, exc_info=True)

    def _get_all_engagements_sync(self) -> List[UserEngagement]:
        """Fetch engagement rows in a blocking context."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM user_engagement")
                rows = cursor.fetchall()
                engagements: List[UserEngagement] = []
                for row in rows:
                    engagements.append(self._row_to_engagement(row))
                return engagements
        except Exception as exc:
            logger.error("Failed to fetch user engagement data: %s", exc, exc_info=True)
            return []

    def _row_to_engagement(self, row: sqlite3.Row) -> UserEngagement:
        """Convert a SQLite row into a UserEngagement object."""
        def parse_datetime(value: Optional[str]) -> Optional[datetime]:
            if not value:
                return None
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                logger.debug("Invalid datetime stored for user %s: %s", row["user_id"], value)
                return None

        def parse_date(value: Optional[str]) -> Optional[date]:
            if not value:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                logger.debug("Invalid date stored for user %s: %s", row["user_id"], value)
                return None

        row_map = dict(row)

        return UserEngagement(
            user_id=row_map["user_id"],
            timezone=row_map["timezone"],
            last_user_message_at=parse_datetime(row_map["last_user_message_at"]),
            last_bot_message_at=parse_datetime(row_map["last_bot_message_at"]),
            last_morning_ping_date=parse_date(row_map["last_morning_ping_date"]),
            reengagement_level=row_map["reengagement_level"] or 0,
            in_session_bot_turns=row_map["in_session_bot_turns"] or 0,
            mood_score=float(row_map["mood_score"]) if row_map["mood_score"] is not None else 0.6,
            last_weather_date=parse_date(row_map["last_weather_date"]),
            last_weather_summary=row_map["last_weather_summary"],
            last_checkin_date=parse_date(row_map.get("last_checkin_date")),
            last_checkin_window=row_map.get("last_checkin_window"),
        )

    async def reset_in_session_turns(
        self,
        user_id: str,
        timezone_name: str,
    ) -> None:
        """Reset the in-session bot turns counter to zero."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            in_session_bot_turns=0,
        )

    async def set_in_session_turns(
        self,
        user_id: str,
        timezone_name: str,
        turns: int,
    ) -> None:
        """Set the in-session bot turns counter to a specific value."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            in_session_bot_turns=turns,
        )

    async def set_mood_score(
        self,
        user_id: str,
        timezone_name: str,
        mood_score: float,
    ) -> None:
        """Persist the latest computed mood score."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            mood_score=mood_score,
        )

    async def set_weather_cache(
        self,
        user_id: str,
        timezone_name: str,
        weather_date: date,
        weather_summary: str,
    ) -> None:
        """Cache last weather info for a user (shared default for now)."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            last_weather_date=weather_date,
            last_weather_summary=weather_summary,
        )

    async def mark_checkin(
        self,
        user_id: str,
        timezone_name: str,
        checkin_date: date,
        checkin_window: str,
    ) -> None:
        """Mark that a casual check-in was sent in a specific time window."""
        await self.initialize()
        await asyncio.to_thread(
            self._update_engagement_sync,
            user_id,
            timezone_name,
            last_checkin_date=checkin_date,
            last_checkin_window=checkin_window,
        )

    async def prune_older_than_days(self, days: int) -> None:
        """Delete conversation data older than the given number of days."""
        await self.initialize()
        await asyncio.to_thread(self._prune_older_than_days_sync, days)

    def _prune_older_than_days_sync(self, days: int) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM conversation_messages WHERE created_at < datetime('now', ?)",
                    (f'-{int(days)} days',),
                )
                conn.execute(
                    "DELETE FROM conversation_corrections WHERE created_at < datetime('now', ?)",
                    (f'-{int(days)} days',),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to prune old conversation data: %s", exc, exc_info=True)

    async def get_correction_count(
        self,
        user_id: str,
        error_type: str,
        window_days: Optional[int] = None,
    ) -> int:
        """Return number of times a given error_type was logged for a user in window."""
        await self.initialize()
        return await asyncio.to_thread(self._get_correction_count_sync, user_id, error_type, window_days)

    def _get_correction_count_sync(self, user_id: str, error_type: str, window_days: Optional[int]) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                if window_days is None:
                    cursor = conn.execute(
                        "SELECT COUNT(1) FROM conversation_corrections WHERE user_id = ? AND error_type = ?",
                        (user_id, error_type),
                    )
                else:
                    cursor = conn.execute(
                        (
                            "SELECT COUNT(1) FROM conversation_corrections "
                            "WHERE user_id = ? AND error_type = ? AND created_at >= datetime('now', ?)"
                        ),
                        (user_id, error_type, f'-{int(window_days)} days'),
                    )
                row = cursor.fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except Exception as exc:
            logger.error("Failed to count corrections: %s", exc, exc_info=True)
            return 0

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Fetch user profile if present."""
        await self.initialize()
        return await asyncio.to_thread(self._get_profile_sync, user_id)

    def _get_profile_sync(self, user_id: str) -> Optional[UserProfile]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return UserProfile(
                    user_id=row["user_id"],
                    name=row["name"],
                    telegram_username=row["telegram_username"],
                    current_level=row["current_level"] or "B1",
                    current_week=row["current_week"] or 1,
                    preferences=row["preferences"],
                    created_at=self._parse_timestamp(row["created_at"]),
                    updated_at=self._parse_timestamp(row["updated_at"]),
                )
        except Exception as exc:
            logger.error("Failed to fetch profile for %s: %s", user_id, exc, exc_info=True)
            return None

    async def upsert_profile(
        self,
        user_id: str,
        name: Optional[str] = None,
        telegram_username: Optional[str] = None,
        current_level: Optional[str] = None,
        current_week: Optional[int] = None,
        preferences: Optional[str] = None,
    ) -> None:
        """Insert or update user profile."""
        await self.initialize()
        await asyncio.to_thread(
            self._upsert_profile_sync,
            user_id,
            name,
            telegram_username,
            current_level,
            current_week,
            preferences,
        )

    def _upsert_profile_sync(
        self,
        user_id: str,
        name: Optional[str],
        telegram_username: Optional[str],
        current_level: Optional[str],
        current_week: Optional[int],
        preferences: Optional[str],
    ) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT user_id FROM user_profiles WHERE user_id = ?", (user_id,))
                exists = cursor.fetchone() is not None

                if not exists:
                    conn.execute(
                        """
                        INSERT INTO user_profiles (user_id, name, telegram_username, current_level, current_week, preferences)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (user_id, name, telegram_username, current_level or "B1", current_week or 1, preferences),
                    )
                else:
                    updates = ["updated_at = CURRENT_TIMESTAMP"]
                    params: list = []
                    if name is not None:
                        updates.append("name = ?")
                        params.append(name)
                    if telegram_username is not None:
                        updates.append("telegram_username = ?")
                        params.append(telegram_username)
                    if current_level is not None:
                        updates.append("current_level = ?")
                        params.append(current_level)
                    if current_week is not None:
                        updates.append("current_week = ?")
                        params.append(current_week)
                    if preferences is not None:
                        updates.append("preferences = ?")
                        params.append(preferences)

                    if len(params) > 0:
                        params.append(user_id)
                        conn.execute(
                            f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = ?",
                            params,
                        )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to upsert profile for %s: %s", user_id, exc, exc_info=True)

    async def log_review_session(
        self,
        user_id: str,
        cards_total: int,
        cards_completed: int,
        duration_seconds: float,
        exit_reason: str,
    ) -> None:
        """Log a vocabulary review session for analytics."""
        await asyncio.to_thread(
            self._log_review_session_sync,
            user_id,
            cards_total,
            cards_completed,
            duration_seconds,
            exit_reason,
        )

    def _log_review_session_sync(
        self,
        user_id: str,
        cards_total: int,
        cards_completed: int,
        duration_seconds: float,
        exit_reason: str,
    ) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO review_sessions (user_id, cards_total, cards_completed, duration_seconds, exit_reason)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, cards_total, cards_completed, duration_seconds, exit_reason),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to log review session for %s: %s", user_id, exc, exc_info=True)

    async def get_review_stats(self, user_id: str, days: int = 30) -> dict:
        """Get vocabulary review statistics for the last N days."""
        return await asyncio.to_thread(self._get_review_stats_sync, user_id, days)

    def _get_review_stats_sync(self, user_id: str, days: int) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
                cursor = conn.execute(
                    """
                    SELECT 
                        COUNT(*) as session_count,
                        SUM(cards_completed) as total_cards_reviewed,
                        AVG(cards_completed * 1.0 / cards_total) as avg_completion_rate
                    FROM review_sessions
                    WHERE user_id = ? AND created_at >= datetime(?, 'unixepoch')
                    """,
                    (user_id, cutoff),
                )
                row = cursor.fetchone()
                return {
                    "session_count": row[0] or 0,
                    "total_cards_reviewed": row[1] or 0,
                    "avg_completion_rate": row[2] or 0.0,
                }
        except Exception as exc:
            logger.error("Failed to get review stats for %s: %s", user_id, exc, exc_info=True)
            return {"session_count": 0, "total_cards_reviewed": 0, "avg_completion_rate": 0.0}

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        """Parse a timestamp string or return epoch if missing."""
        if not value:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return datetime.fromtimestamp(0, tz=timezone.utc)


# Global instance used throughout the bot
conversation_store = ConversationStore(CONVERSATION_DB_PATH)
