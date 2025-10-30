"""Curriculum management system for B1→B2 Spanish learning progression."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from src.config import CONFIG_DIR

logger = logging.getLogger(__name__)

CURRICULUM_PATH = CONFIG_DIR / "curriculum.yaml"


@dataclass(frozen=True)
class VocabularyWord:
    """Single vocabulary word with context."""

    word: str
    translation: str
    example: str


@dataclass(frozen=True)
class WeekLesson:
    """Represents one week of curriculum content."""

    week_number: int
    title: str
    grammar_topics: list[str]
    grammar_notes: str
    vocabulary_theme: str
    vocabulary_words: list[VocabularyWord]
    conversation_prompts: list[str]
    cultural_topic: str


class CurriculumManager:
    """Load and serve curriculum content for adaptive lesson delivery."""

    def __init__(self, curriculum_path: Path = CURRICULUM_PATH):
        self.curriculum_path = curriculum_path
        self._curriculum_data: Optional[dict] = None

    def _load_curriculum(self) -> dict:
        """Load curriculum YAML once and cache."""
        if self._curriculum_data is not None:
            return self._curriculum_data

        try:
            with open(self.curriculum_path, "r", encoding="utf-8") as f:
                self._curriculum_data = yaml.safe_load(f)
            logger.info("Curriculum loaded from %s", self.curriculum_path)
            return self._curriculum_data
        except FileNotFoundError:
            logger.error("Curriculum file not found: %s", self.curriculum_path)
            return {"lessons": {}, "metadata": {}}
        except Exception as exc:
            logger.error("Failed to load curriculum: %s", exc, exc_info=True)
            return {"lessons": {}, "metadata": {}}

    def get_week_lesson(self, week: int) -> Optional[WeekLesson]:
        """Retrieve lesson content for a specific week."""
        curriculum = self._load_curriculum()
        lessons = curriculum.get("lessons", {})
        week_key = f"week_{week}"
        lesson_data = lessons.get(week_key)

        if not lesson_data:
            logger.warning("No lesson found for week %s", week)
            return None

        vocab_list = []
        for vocab_entry in lesson_data.get("vocabulary_words", []):
            vocab_list.append(
                VocabularyWord(
                    word=vocab_entry.get("word", ""),
                    translation=vocab_entry.get("translation", ""),
                    example=vocab_entry.get("example", ""),
                )
            )

        return WeekLesson(
            week_number=week,
            title=lesson_data.get("title", ""),
            grammar_topics=lesson_data.get("grammar_topics", []),
            grammar_notes=lesson_data.get("grammar_notes", ""),
            vocabulary_theme=lesson_data.get("vocabulary_theme", ""),
            vocabulary_words=vocab_list,
            conversation_prompts=lesson_data.get("conversation_prompts", []),
            cultural_topic=lesson_data.get("cultural_topic", ""),
        )

    def get_total_weeks(self) -> int:
        """Return total curriculum weeks from metadata."""
        curriculum = self._load_curriculum()
        return curriculum.get("metadata", {}).get("total_weeks", 16)

    def build_lesson_context_prompt(self, week: int) -> str:
        """
        Generate a focused lesson context string for injection into system prompt.

        This will guide the bot to naturally weave grammar and vocabulary into
        conversation without announcing "Today we're learning X."
        """
        lesson = self.get_week_lesson(week)
        if not lesson:
            return ""

        vocab_examples = "\n".join(
            f"  - {v.word}: {v.example}" for v in lesson.vocabulary_words[:3]
        )
        prompts_text = ", ".join(lesson.conversation_prompts[:2])

        context = (
            f"SEMANA {week}: {lesson.title}\n"
            f"Tema gramatical: {', '.join(lesson.grammar_topics)}\n"
            f"Notas: {lesson.grammar_notes[:150]}...\n"
            f"Vocabulario clave:\n{vocab_examples}\n"
            f"Prompts sugeridos: {prompts_text}\n"
            f"Cultura: {lesson.cultural_topic}"
        )
        return context


# Global instance
curriculum_manager = CurriculumManager()

