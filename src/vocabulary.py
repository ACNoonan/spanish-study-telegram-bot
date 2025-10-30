"""Vocabulary tracking and spaced repetition system (SM-2 algorithm)."""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from src.config import CONVERSATION_DB_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VocabularyCard:
    """Represents a single vocabulary card with SM-2 spaced repetition data."""

    id: int
    user_id: str
    word: str
    translation: Optional[str]
    example: Optional[str]
    introduced_week: int
    introduced_at: datetime
    ease_factor: float
    interval_days: int
    repetition_count: int
    next_review_date: Optional[date]
    last_review_date: Optional[date]


class VocabularyManager:
    """Manage vocabulary introduction and spaced repetition reviews."""

    def __init__(self, db_path: Path = CONVERSATION_DB_PATH):
        self.db_path = db_path

    async def introduce_word(
        self,
        user_id: str,
        word: str,
        translation: Optional[str],
        example: Optional[str],
        week: int,
    ) -> None:
        """Add a new vocabulary word for a user (or skip if already exists)."""
        await asyncio.to_thread(
            self._introduce_word_sync,
            user_id,
            word,
            translation,
            example,
            week,
        )

    def _introduce_word_sync(
        self,
        user_id: str,
        word: str,
        translation: Optional[str],
        example: Optional[str],
        week: int,
    ) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if word already introduced for this user
                cursor = conn.execute(
                    "SELECT id FROM vocabulary_cards WHERE user_id = ? AND word = ?",
                    (user_id, word),
                )
                if cursor.fetchone():
                    return  # Already exists

                # Schedule first review for tomorrow
                next_review = (datetime.now(timezone.utc) + timedelta(days=1)).date()
                conn.execute(
                    """
                    INSERT INTO vocabulary_cards (
                        user_id, word, translation, example, introduced_week,
                        ease_factor, interval_days, repetition_count, next_review_date
                    ) VALUES (?, ?, ?, ?, ?, 2.5, 1, 0, ?)
                    """,
                    (user_id, word, translation, example, week, next_review.isoformat()),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to introduce word '%s' for user %s: %s", word, user_id, exc, exc_info=True)

    async def get_due_words(self, user_id: str, limit: int = 10) -> List[VocabularyCard]:
        """Fetch words due for review (next_review_date <= today)."""
        return await asyncio.to_thread(self._get_due_words_sync, user_id, limit)

    def _get_due_words_sync(self, user_id: str, limit: int) -> List[VocabularyCard]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                today_iso = date.today().isoformat()
                cursor = conn.execute(
                    """
                    SELECT * FROM vocabulary_cards
                    WHERE user_id = ? AND next_review_date IS NOT NULL AND next_review_date <= ?
                    ORDER BY next_review_date ASC
                    LIMIT ?
                    """,
                    (user_id, today_iso, limit),
                )
                rows = cursor.fetchall()
                cards: List[VocabularyCard] = []
                for row in rows:
                    cards.append(self._row_to_card(row))
                return cards
        except Exception as exc:
            logger.error("Failed to fetch due words for user %s: %s", user_id, exc, exc_info=True)
            return []

    async def update_card_after_review(
        self,
        card_id: int,
        quality: int,
    ) -> None:
        """
        Update vocabulary card using SM-2 algorithm after user review.

        quality: 0-5 scale
          0-2: incorrect/hard (reset interval)
          3+: correct (increase interval based on ease factor)
        """
        await asyncio.to_thread(self._update_card_after_review_sync, card_id, quality)

    def _update_card_after_review_sync(self, card_id: int, quality: int) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM vocabulary_cards WHERE id = ?", (card_id,))
                row = cursor.fetchone()
                if not row:
                    return

                ease_factor = float(row["ease_factor"])
                interval_days = int(row["interval_days"])
                repetition_count = int(row["repetition_count"])

                # SM-2 algorithm
                if quality < 3:
                    # Incorrect: reset interval to 1
                    new_interval = 1
                    new_repetition = 0
                    ease_factor = max(1.3, ease_factor - 0.2)
                else:
                    # Correct: increase interval
                    new_repetition = repetition_count + 1
                    if new_repetition == 1:
                        new_interval = 1
                    elif new_repetition == 2:
                        new_interval = 6
                    else:
                        new_interval = int(round(interval_days * ease_factor))

                    # Adjust ease factor
                    ease_factor = max(
                        1.3,
                        ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
                    )

                next_review = (datetime.now(timezone.utc) + timedelta(days=new_interval)).date()

                conn.execute(
                    """
                    UPDATE vocabulary_cards
                    SET ease_factor = ?, interval_days = ?, repetition_count = ?,
                        next_review_date = ?, last_review_date = ?
                    WHERE id = ?
                    """,
                    (
                        ease_factor,
                        new_interval,
                        new_repetition,
                        next_review.isoformat(),
                        date.today().isoformat(),
                        card_id,
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Failed to update vocabulary card %s: %s", card_id, exc, exc_info=True)

    def _row_to_card(self, row: sqlite3.Row) -> VocabularyCard:
        """Convert SQLite row to VocabularyCard."""

        def parse_dt(value: Optional[str]) -> datetime:
            if not value:
                return datetime.fromtimestamp(0, tz=timezone.utc)
            try:
                dt = datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                return datetime.fromtimestamp(0, tz=timezone.utc)

        def parse_date(value: Optional[str]) -> Optional[date]:
            if not value:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None

        return VocabularyCard(
            id=row["id"],
            user_id=row["user_id"],
            word=row["word"],
            translation=row["translation"],
            example=row["example"],
            introduced_week=row["introduced_week"] or 0,
            introduced_at=parse_dt(row["introduced_at"]),
            ease_factor=float(row["ease_factor"]) if row["ease_factor"] is not None else 2.5,
            interval_days=int(row["interval_days"]) if row["interval_days"] is not None else 1,
            repetition_count=int(row["repetition_count"]) if row["repetition_count"] is not None else 0,
            next_review_date=parse_date(row["next_review_date"]),
            last_review_date=parse_date(row["last_review_date"]),
        )

    async def get_mastery_stats(self, user_id: str) -> dict:
        """Return vocabulary mastery statistics for a user."""
        return await asyncio.to_thread(self._get_mastery_stats_sync, user_id)

    def _get_mastery_stats_sync(self, user_id: str) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(1) FROM vocabulary_cards WHERE user_id = ?",
                    (user_id,),
                )
                total = cursor.fetchone()[0] or 0

                # Mastered: repetition_count >= 3 and interval_days >= 14
                cursor = conn.execute(
                    "SELECT COUNT(1) FROM vocabulary_cards WHERE user_id = ? AND repetition_count >= 3 AND interval_days >= 14",
                    (user_id,),
                )
                mastered = cursor.fetchone()[0] or 0

                # Learning: 1 <= repetition_count < 3
                cursor = conn.execute(
                    "SELECT COUNT(1) FROM vocabulary_cards WHERE user_id = ? AND repetition_count >= 1 AND repetition_count < 3",
                    (user_id,),
                )
                learning = cursor.fetchone()[0] or 0

                # New: repetition_count == 0
                new_count = total - mastered - learning

                return {
                    "total": total,
                    "mastered": mastered,
                    "learning": learning,
                    "new": new_count,
                }
        except Exception as exc:
            logger.error("Failed to fetch mastery stats for user %s: %s", user_id, exc, exc_info=True)
            return {"total": 0, "mastered": 0, "learning": 0, "new": 0}


# Global instance
vocabulary_manager = VocabularyManager()

