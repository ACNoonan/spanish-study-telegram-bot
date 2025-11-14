"""Lightweight correction analysis using the existing LLM backend."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

from src.llm_client import llm_client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrectionSuggestion:
    """Represents a single correction suggestion."""

    error_type: str
    original_text: str
    corrected_text: str
    explanation: str


class CorrectionAnalyzer:
    """Analyze user input for common Spanish errors."""

    def __init__(self, max_corrections: int = 2):
        self.max_corrections = max_corrections

    async def analyze(self, user_message: str) -> List[CorrectionSuggestion]:
        """
        Ask the LLM for gentle correction suggestions.

        Returns up to ``max_corrections`` items; returns an empty list when the
        student message is correct or when analysis fails.
        """
        if not user_message.strip():
            return []

        system_prompt = (
            "Eres una profesora de español que analiza el mensaje del estudiante "
            "y devuelve una lista JSON con como máximo "
            f"{self.max_corrections} correcciones. Cada corrección debe incluir "
            'los campos: "error_type", "original_text", "corrected_text", '
            '"explanation". Responde únicamente con JSON válido.\n\n'
            "IMPORTANTE: Solo identifica errores SIGNIFICATIVOS que impidan la comunicación "
            "o sean fundamentales para nivel B1-B2. Ignora:\n"
            "- Errores menores de gramática que no afectan la comprensión\n"
            "- Abreviaciones y lenguaje informal de texto (ej: 'q', 'tb', 'tmb')\n"
            "- Pequeños errores de ortografía o acentos si el significado es claro\n"
            "- Uso coloquial o expresiones informales apropiadas para chat"
        )
        user_prompt = (
            "Mensaje del estudiante:\n"
            f"{user_message}\n\n"
            "Si no hay errores SIGNIFICATIVOS que requieran corrección, devuelve un "
            "arreglo JSON vacío ([])."
        )

        try:
            raw_response = await llm_client.generate_response(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=250,
            )
            if not raw_response:
                return []

            raw_response = raw_response.strip()
            # Some models wrap JSON in code fences; remove them cautiously.
            if raw_response.startswith("```"):
                segments = raw_response.split("```")
                if len(segments) >= 3:
                    raw_response = "".join(segments[1:-1]).strip()
                else:
                    raw_response = raw_response.strip("`")

                # Remove optional language hint such as "json\n".
                if raw_response.lower().startswith("json"):
                    raw_response = raw_response[4:].lstrip()

            suggestions_data = json.loads(raw_response)
            suggestions: List[CorrectionSuggestion] = []
            if isinstance(suggestions_data, dict):
                # In case the model returns an object with a list inside.
                suggestions_data = suggestions_data.get("corrections", [])

            if not isinstance(suggestions_data, list):
                logger.warning("Unexpected correction payload: %s", raw_response)
                return []

            for item in suggestions_data[: self.max_corrections]:
                if not isinstance(item, dict):
                    continue

                try:
                    suggestions.append(
                        CorrectionSuggestion(
                            error_type=str(item.get("error_type", "desconocido")),
                            original_text=str(item.get("original_text", "")),
                            corrected_text=str(item.get("corrected_text", "")),
                            explanation=str(item.get("explanation", "")),
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Skipping malformed correction item: %s", exc)

            return suggestions
        except json.JSONDecodeError:
            logger.warning("Failed to parse correction JSON.")
        except Exception as exc:
            logger.error("Correction analysis failed: %s", exc, exc_info=True)

        return []


# Global analyzer instance
correction_analyzer = CorrectionAnalyzer()
