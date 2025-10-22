"""Lightweight SQLite-backed conversation history store."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.config import CONVERSATION_DB_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationMessage:
    """Represents a stored conversation message."""

    role: str
    content: str


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


# Global instance used throughout the bot
conversation_store = ConversationStore(CONVERSATION_DB_PATH)
