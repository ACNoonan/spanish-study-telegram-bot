"""Character personality system for Sofía."""
from __future__ import annotations

import logging
from typing import Optional

import yaml

from src.config import (
    CHARACTER_PROFILE_PATH,
    SYSTEM_PROMPT_PATH,
    GREETING_PROMPT_PATH,
    HELP_PROMPT_PATH,
)

logger = logging.getLogger(__name__)


class PersonalitySystem:
    """Manages Sofía's personality, prompts, and persona data."""

    def __init__(self) -> None:
        self.profile = self._load_profile()
        self.base_flirtiness = self.profile.get("personality_traits", {}).get("flirty_level", 6)
        self.system_prompt_template = self._load_prompt_file(
            SYSTEM_PROMPT_PATH,
            self._default_system_prompt(),
        )
        self.greeting_template = self._load_prompt_file(
            GREETING_PROMPT_PATH,
            self._default_greeting(),
        )
        self.help_template = self._load_prompt_file(
            HELP_PROMPT_PATH,
            self._default_help(),
        )

    def _load_profile(self) -> dict:
        """Load character profile from YAML."""
        try:
            with open(CHARACTER_PROFILE_PATH, "r", encoding="utf-8") as profile_file:
                return yaml.safe_load(profile_file)
        except FileNotFoundError:
            logger.warning(
                "Character profile file %s not found; using built-in defaults.",
                CHARACTER_PROFILE_PATH,
            )
        except Exception as exc:
            logger.error("Failed to load character profile: %s", exc, exc_info=True)
        return self._get_default_profile()

    def _get_default_profile(self) -> dict:
        """Return a minimal default profile if file loading fails."""
        return {
            "name": "Sofía",
            "age": 28,
            "location": "Madrid, España",
            "personality_traits": {"flirty_level": 6},
            "speech_patterns": [],
            "teaching_style": {"correction_method": "sandwich", "max_corrections_per_message": 2},
        }

    def _load_prompt_file(self, path, fallback: str) -> str:
        """Load a prompt template from disk; fall back to default text on failure."""
        try:
            with open(path, "r", encoding="utf-8") as prompt_file:
                content = prompt_file.read().strip()
                if content:
                    return content
        except FileNotFoundError:
            logger.warning("Prompt file %s not found; using built-in default.", path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to read prompt file %s: %s", path, exc, exc_info=True)
        return fallback

    def _default_system_prompt(self) -> str:
        """Built-in system prompt used if config file missing."""
        return (
            "Eres {name}, una profesora de español de {age} años que vive en {location}.\n\n"
            "PERSONALIDAD Y ROL:\n"
            "- Eres cálida, paciente y entusiasta sobre enseñar español.\n"
            "- Tu estilo es informal (usas 'tú', no 'usted').\n"
            "- Tienes un toque coqueto pero siempre apropiado y profesional.\n"
            "- Compartes detalles de tu vida cotidiana en Madrid para mantener la conversación viva.\n"
            "- Usas expresiones cariñosas como 'cariño' o 'guapo/a' cuando sea natural.\n\n"
            "ESTILO DE ENSEÑANZA:\n"
            "- NO corrijas errores gramaticales en tu respuesta - eso se maneja por separado.\n"
            "- Tu trabajo es mantener una conversación natural, fluida y divertida.\n"
            "- Nunca seas pedante o condescendiente.\n"
            "- Integra explicaciones gramaticales o de vocabulario de forma orgánica cuando sea relevante.\n"
            "- Haz preguntas frecuentes para fomentar respuestas en español.\n"
            "- Celebra cualquier progreso, por pequeño que sea.\n\n"
            "REGLAS IMPORTANTES:\n"
            "- Responde siempre en español; usa inglés solo si es imprescindible.\n"
            "- Mantén las respuestas conversacionales y naturales.\n"
            "- Adapta el vocabulario a un nivel B1-B2.\n"
            "- Integra referencias culturales de España, especialmente Madrid.\n"
            "- NO corrijas errores en tu respuesta - simplemente mantén una conversación natural."
        )

    def _default_greeting(self) -> str:
        """Built-in greeting used if config file missing."""
        return (
            "¡Hola! Soy {name}, tu profe de español 😊\n\n"
            "Vivo en {location} y me encanta ayudar a la gente a mejorar su español de forma natural y divertida.\n\n"
            "Vamos a practicar conversando como amigos, y yo te acompañaré para que pases del nivel B1 al B2. "
            "¡No tengas miedo de cometer errores! Son parte del camino 💪\n\n"
            "¿Listo para empezar? Cuéntame... ¿qué te trae por aquí?"
        )

    def _default_help(self) -> str:
        """Built-in help text used if the config file is missing."""
        return (
            "📚 *Comandos disponibles:*\n\n"
            "/start - Comenzar o reiniciar la conversación\n"
            "/help - Ver este mensaje\n\n"
            "*¿Cómo funciona?*\n"
            "Simplemente chatea conmigo en español como si fuéramos amigos. "
            "Yo te ayudaré a mejorar de forma natural, corrigiendo errores sutilmente y enseñándote cosas nuevas "
            "durante nuestras conversaciones.\n\n"
            "¡No te preocupes por cometer errores! Son parte del aprendizaje 😊\n\n"
            "¿Alguna pregunta? Pregúntame en español (o en inglés si lo necesitas)."
        )

    def get_system_prompt(
        self,
        lesson_context: Optional[str] = None,
        conversation_history: Optional[list] = None,
    ) -> str:
        """
        Generate the system prompt for the LLM.

        Args:
            lesson_context: Current lesson/week focus (e.g., "subjunctive intro")
            conversation_history: Recent conversation summary for context

        Returns:
            Complete system prompt string
        """
        profile = self.profile
        teaching = profile.get("teaching_style", {})

        base_prompt = self.system_prompt_template.format(
            name=profile.get("name", "Sofía"),
            age=profile.get("age", 28),
            location=profile.get("location", "Madrid, España"),
            correction_method=teaching.get("correction_method", "sandwich"),
            max_corrections_per_message=teaching.get("max_corrections_per_message", 2),
        )

        lesson_section = ""
        if lesson_context:
            lesson_section = (
                "\nENFOQUE DE LA LECCIÓN ACTUAL:\n"
                f"{lesson_context}\n"
                "- Introduce este tema de forma natural en la conversación\n"
                "- Crea oportunidades para que el estudiante practique\n"
                "- No anuncies \"hoy vamos a aprender X\", simplemente úsalo\n"
            )

        history_section = ""
        if conversation_history:
            history_section = "\nCONTEXTO DE CONVERSACIÓN RECIENTE:\n" + "\n".join(conversation_history[-5:])

        return base_prompt + lesson_section + history_section

    def get_greeting_message(self) -> str:
        """Get a personalized greeting for new users."""
        return self.greeting_template.format(
            name=self.profile.get("name", "Sofía"),
            location=self.profile.get("location", "Madrid, España"),
        )

    def get_help_message(self) -> str:
        """Get help/instructions message."""
        return self.help_template


# Global instance
personality_system = PersonalitySystem()
