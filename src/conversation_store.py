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

    @property
    def last_interaction(self) -> Optional[datetime]:
        """Return the most recent interaction timestamp."""
        candidates = [ts for ts in (self.last_user_message_at, self.last_bot_message_at) if ts]
        if not candidates:
            return None
        return max(candidates)


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
                    reengagement_level INTEGER DEFAULT 0
                )
                """
            )
            conn.commit()

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

        return UserEngagement(
            user_id=row["user_id"],
            timezone=row["timezone"],
            last_user_message_at=parse_datetime(row["last_user_message_at"]),
            last_bot_message_at=parse_datetime(row["last_bot_message_at"]),
            last_morning_ping_date=parse_date(row["last_morning_ping_date"]),
            reengagement_level=row["reengagement_level"] or 0,
        )


# Global instance used throughout the bot
conversation_store = ConversationStore(CONVERSATION_DB_PATH)
