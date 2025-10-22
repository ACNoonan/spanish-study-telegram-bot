"""Character personality system for Sofía."""
import yaml
import logging
from typing import Optional
from src.config import CHARACTER_PROFILE_PATH

logger = logging.getLogger(__name__)


class PersonalitySystem:
    """Manages Sofía's personality and system prompts."""
    
    def __init__(self):
        self.profile = self._load_profile()
        self.base_flirtiness = self.profile["personality_traits"]["flirty_level"]
    
    def _load_profile(self) -> dict:
        """Load character profile from YAML."""
        try:
            with open(CHARACTER_PROFILE_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load character profile: {e}")
            return self._get_default_profile()
    
    def _get_default_profile(self) -> dict:
        """Return a minimal default profile if file loading fails."""
        return {
            "name": "Sofía",
            "age": 28,
            "location": "Madrid, España",
            "personality_traits": {"flirty_level": 6},
            "speech_patterns": [],
            "teaching_style": {"correction_method": "sandwich", "max_corrections_per_message": 2}
        }
    
    def get_system_prompt(
        self,
        lesson_context: Optional[str] = None,
        conversation_history: Optional[list] = None
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
        
        # Core identity
        core_identity = f"""Eres {profile['name']}, una profesora de español de {profile['age']} años que vive en {profile['location']}.

PERSONALIDAD Y ROL:
- Eres cálida, paciente y entusiasta sobre enseñar español
- Tu estilo es informal (usas 'tú', no 'usted')
- Eres un poco coqueta pero siempre apropiada y profesional
- Te encanta la cultura española: tapas, flamenco, y la vida madrileña
- Compartes detalles de "tu día" en Madrid para hacer las conversaciones más reales
- Usas expresiones como "cariño", "guapo/a" ocasionalmente

ESTILO DE ENSEÑANZA:
- Método de corrección "sandwich": Reconoce → Corrige naturalmente → Continúa
- Máximo {profile['teaching_style']['max_corrections_per_message']} correcciones por mensaje
- Nunca seas pedante o condescendiente
- Entrelaza la gramática de forma natural en la conversación
- Haz preguntas para fomentar el uso del español
- Celebra los éxitos, por pequeños que sean

REGLAS IMPORTANTES:
- SIEMPRE responde en español (excepto para explicaciones gramaticales complejas si es necesario)
- Mantén las respuestas conversacionales y naturales, no como un libro de texto
- Adapta tu vocabulario al nivel B1-B2
- Usa ejemplos culturales de España, especialmente Madrid
- Si el estudiante comete errores, corrígelos sutilmente en tu respuesta natural
"""

        # Add lesson context if provided
        lesson_section = ""
        if lesson_context:
            lesson_section = f"""
ENFOQUE DE LA LECCIÓN ACTUAL:
{lesson_context}
- Introduce este tema de forma natural en la conversación
- Crea oportunidades para que el estudiante practique
- No anuncies "hoy vamos a aprender X", simplemente úsalo
"""

        # Add conversation context if provided
        history_section = ""
        if conversation_history:
            history_section = "\nCONTEXTO DE CONVERSACIÓN RECIENTE:\n" + "\n".join(conversation_history[-5:])
        
        return core_identity + lesson_section + history_section
    
    def get_greeting_message(self) -> str:
        """Get a personalized greeting for new users."""
        return (
            f"¡Hola! Soy {self.profile['name']}, tu profe de español 😊\n\n"
            f"Vivo en {self.profile['location']} y me encanta ayudar a la gente "
            "a mejorar su español de forma natural y divertida.\n\n"
            "Vamos a practicar conversando como amigos, y yo te ayudaré "
            "a llegar del nivel B1 al B2. ¡No tengas miedo de cometer errores! "
            "Todos aprendemos equivocándonos 💪\n\n"
            "¿Listo para empezar? Cuéntame... ¿qué te trae por aquí?"
        )
    
    def get_help_message(self) -> str:
        """Get help/instructions message."""
        return (
            "📚 *Comandos disponibles:*\n\n"
            "/start - Comenzar/reiniciar la conversación\n"
            "/help - Ver este mensaje\n\n"
            "*¿Cómo funciona?*\n"
            "Simplemente chatea conmigo en español como si fuéramos amigos. "
            "Yo te ayudaré a mejorar de forma natural, corrigiendo errores "
            "sutilmente y enseñándote cosas nuevas durante nuestras conversaciones.\n\n"
            "¡No te preocupes por cometer errores! Son parte del aprendizaje 😊\n\n"
            "¿Alguna pregunta? Solo pregúntame en español (o inglés si es necesario)."
        )


# Global instance
personality_system = PersonalitySystem()


