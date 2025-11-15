"""Vocabulary review session management."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from src.vocabulary import VocabularyCard

logger = logging.getLogger(__name__)


@dataclass
class ReviewSession:
    """Represents an active vocabulary review session for a user."""
    
    user_id: str
    cards: list[VocabularyCard]
    current_card_index: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def current_card(self) -> Optional[VocabularyCard]:
        """Get the current card being reviewed, or None if session complete."""
        if 0 <= self.current_card_index < len(self.cards):
            return self.cards[self.current_card_index]
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if all cards have been reviewed."""
        return self.current_card_index >= len(self.cards)
    
    @property
    def cards_completed(self) -> int:
        """Number of cards completed so far."""
        return min(self.current_card_index, len(self.cards))
    
    @property
    def cards_remaining(self) -> int:
        """Number of cards remaining in this session."""
        return max(0, len(self.cards) - self.current_card_index)
    
    def advance(self) -> None:
        """Move to the next card and update activity timestamp."""
        self.current_card_index += 1
        self.last_activity = datetime.now(timezone.utc)
    
    def is_inactive(self, timeout_minutes: int = 10) -> bool:
        """Check if session has been inactive for too long."""
        inactive_seconds = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
        return inactive_seconds > (timeout_minutes * 60)


class ReviewSessionManager:
    """Manages active vocabulary review sessions."""
    
    def __init__(self):
        self._active_sessions: Dict[str, ReviewSession] = {}
    
    def create_session(self, user_id: str, cards: list[VocabularyCard]) -> ReviewSession:
        """Create and store a new review session."""
        session = ReviewSession(user_id=user_id, cards=cards)
        self._active_sessions[user_id] = session
        logger.info(f"Created review session for user {user_id} with {len(cards)} cards")
        return session
    
    def get_session(self, user_id: str) -> Optional[ReviewSession]:
        """Get active session for a user, or None if no active session."""
        return self._active_sessions.get(user_id)
    
    def has_active_session(self, user_id: str) -> bool:
        """Check if user has an active review session."""
        return user_id in self._active_sessions
    
    def end_session(self, user_id: str) -> Optional[ReviewSession]:
        """End and remove a user's review session, returning the session data."""
        return self._active_sessions.pop(user_id, None)
    
    def cleanup_inactive_sessions(self, timeout_minutes: int = 10) -> list[str]:
        """
        Remove sessions that have been inactive too long.
        Returns list of user_ids whose sessions were cleaned up.
        """
        inactive_users = [
            user_id for user_id, session in self._active_sessions.items()
            if session.is_inactive(timeout_minutes)
        ]
        
        for user_id in inactive_users:
            self._active_sessions.pop(user_id)
            logger.info(f"Cleaned up inactive review session for user {user_id}")
        
        return inactive_users


# Global instance
review_session_manager = ReviewSessionManager()

