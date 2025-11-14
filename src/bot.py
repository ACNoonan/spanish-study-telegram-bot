"""Main Telegram bot implementation."""
import inspect
import logging
import random
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

from src.config import (
    TELEGRAM_BOT_TOKEN,
    DEFAULT_USER_TIMEZONE,
    AUTHORIZED_USER_IDS_SET,
)
from src.llm_client import llm_client
from src.personality import personality_system
from src.conversation_store import conversation_store, CorrectionEntry
from src.correction import correction_analyzer, CorrectionSuggestion
from src.curriculum import curriculum_manager

# Configure logging
from src.config import LOGS_DIR
import os

# Create logs directory if it doesn't exist
LOGS_DIR.mkdir(exist_ok=True)

# Set up logging to both console and file
log_file = LOGS_DIR / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to file: {log_file}")


FALLBACK_TECHNICAL = (
    "Ay, perdona... tengo un problema técnico. ¿Puedes intentar de nuevo en un momento? 😅"
)
FALLBACK_ERROR = "¡Ups! Algo salió mal. Por favor, inténtalo de nuevo."

# Simple scheduled messages for different times of day
SCHEDULED_MESSAGES = {
    "morning": [
        "¡Buenos días! ☀️ ¿Listo para practicar un poco de español conmigo hoy?",
        "¡Hola, cariño! ¿Qué planes tienes para hoy?",
        "Buenos días 🌅 ¿Qué tal has dormido?",
        "¡Arriba! 💪 ¿Listo para un día genial?",
    ],
    "afternoon": [
        "¡Hola! 😊 ¿Qué tal va tu día? Cuéntame algo.",
        "¡Hey! 🌞 ¿Ya has comido? ¿Qué estás haciendo?",
        "¿Qué tal? 💫 ¿Hacemos una pausa para charlar?",
    ],
    "evening": [
        "¡Buenas noches! 🌆 ¿Qué tal ha ido tu día?",
        "¡Hola! 🌙 ¿Qué has hecho hoy? Me encantaría saberlo.",
        "¡Buenas! 🌃 ¿Has cenado ya? ¿Qué tal todo?",
    ],
}


class SpanishTutorBot:
    """Spanish Tutor Bot with personality."""
    
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(self._on_startup).build()
        self._setup_handlers()

    async def _on_startup(self, application: Application):
        """Ensure supporting services are ready before handling updates."""
        await conversation_store.initialize()
        logger.info("SpanishTutorBot startup complete.")
        await self._schedule_daily_messages(application)
    
    def _setup_handlers(self):
        """Set up command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        
        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        user_id = str(user.id)
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} (@{user.username}) attempted to start bot")
            unauthorized_message = (
                "¡Hola! 👋 Soy un bot privado de aprendizaje de español. "
                "Este bot está configurado solo para uso personal.\n\n"
                "Si te interesa tener acceso, por favor contacta al administrador. "
                "¡Gracias por tu comprensión! 😊"
            )
            await update.message.reply_text(unauthorized_message)
            return
        
        # Create or update user profile on first interaction
        await conversation_store.upsert_profile(
            user_id=user_id,
            name=user.first_name,
            telegram_username=user.username,
        )
        
        greeting = personality_system.get_greeting_message()
        await update.message.reply_text(greeting)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} (@{user.username}) attempted to use help command")
            unauthorized_message = (
                "¡Hola! 👋 Soy un bot privado de aprendizaje de español. "
                "Este bot está configurado solo para uso personal.\n\n"
                "Si te interesa tener acceso, por favor contacta al administrador. "
                "¡Gracias por tu comprensión! 😊"
            )
            await update.message.reply_text(unauthorized_message)
            return
        
        help_text = personality_system.get_help_message()
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        user = update.effective_user
        user_message = update.message.text
        user_id = str(user.id)
        timezone_name = self._resolve_timezone(update)

        message_date = update.message.date or datetime.now(timezone.utc)
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        
        logger.info(f"Message from {user.id}: {user_message}")
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} (@{user.username}) attempted to use bot")
            unauthorized_message = (
                "¡Hola! 👋 Soy un bot privado de aprendizaje de español. "
                "Este bot está configurado solo para uso personal.\n\n"
                "Si te interesa tener acceso, por favor contacta al administrador. "
                "¡Gracias por tu comprensión! 😊"
            )
            await update.message.reply_text(unauthorized_message)
            return
        
        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)
        
        response_text = None
        correction_suggestions: list[CorrectionSuggestion] = []
        try:
            # Get user profile for curriculum context
            profile = await conversation_store.get_profile(user_id)
            current_week = profile.current_week if profile else 1

            # Build conversation messages for LLM with curriculum context
            lesson_context = curriculum_manager.build_lesson_context_prompt(current_week)
            system_prompt = personality_system.get_system_prompt(lesson_context=lesson_context)

            # Analyze message for potential corrections
            correction_suggestions = await correction_analyzer.analyze(user_message)
            correction_hint = ""
            if correction_suggestions:
                hint_lines = []
                for suggestion in correction_suggestions:
                    # Count prior occurrences to trigger explicit teaching after 3rd time
                    prior_count = await conversation_store.get_correction_count(
                        user_id, suggestion.error_type, window_days=14
                    )
                    explicit_note = (
                        " Añade una explicación explícita y corta (1-2 frases) porque es un error repetido."
                        if prior_count >= 2
                        else ""
                    )
                    hint_lines.append(
                        f"- Tipo: {suggestion.error_type}; original: \"{suggestion.original_text}\"; corrección: \"{suggestion.corrected_text}\". Explica brevemente: {suggestion.explanation}.{explicit_note}"
                    )
                correction_hint = (
                    "\nCORRECCIONES SUGERIDAS (OPCIONALES):\n"
                    + "\n".join(hint_lines)
                    + "\n\nPuedes mencionar estas correcciones SI SON REALMENTE IMPORTANTES para la comunicación. "
                    "Recuerda ser MUY tolerante con:\n"
                    "- Errores menores que no afectan la comprensión\n"
                    "- Abreviaciones o lenguaje informal de chat\n"
                    "- Pequeños errores de ortografía o acentos\n\n"
                    "Si decides corregir algo, hazlo de forma muy sutil y natural en tu respuesta, "
                    "sin interrumpir el flujo de la conversación. Prioriza mantener la conversación natural y divertida."
                )
                system_prompt += correction_hint

            history_messages = await conversation_store.get_recent_messages(user_id)

            messages = [{"role": "system", "content": system_prompt}]
            for history_message in history_messages:
                messages.append(
                    {"role": history_message.role, "content": history_message.content}
                )
            messages.append({"role": "user", "content": user_message})

            # Get response from LLM
            response_text = await llm_client.generate_response(messages)
            
            if response_text:
                await update.message.reply_text(response_text)
                await self._maybe_send_reaction(update, correction_suggestions)
            else:
                # Fallback if LLM fails
                response_text = FALLBACK_TECHNICAL
                await update.message.reply_text(response_text)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            response_text = FALLBACK_ERROR
            await update.message.reply_text(response_text)
        
        finally:
            # Persist conversation history for future context
            try:
                await conversation_store.append_message(user_id, "user", user_message)
                if response_text:
                    await conversation_store.append_message(user_id, "assistant", response_text)
                for suggestion in correction_suggestions:
                    await conversation_store.log_correction(
                        user_id,
                        CorrectionEntry(
                            error_type=suggestion.error_type,
                            original_text=suggestion.original_text,
                            corrected_text=suggestion.corrected_text,
                            explanation=suggestion.explanation,
                        ),
                    )
                await conversation_store.record_user_activity(
                    user_id,
                    timezone_name,
                    message_date,
                )
                if response_text:
                    await conversation_store.record_bot_activity(
                        user_id,
                        timezone_name,
                        datetime.now(timezone.utc),
                    )
            except Exception as store_error:
                logger.error(
                    "Failed to persist conversation messages for user %s: %s",
                    user_id,
                    store_error,
                    exc_info=True,
                )

    def run(self):
        """Start the bot with polling."""
        logger.info("Starting Spanish Tutor Bot...")
        logger.info(f"Model: {llm_client.model}")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _maybe_send_reaction(
        self,
        update: Update,
        correction_suggestions: list[CorrectionSuggestion],
    ) -> None:
        """
        Provide lightweight positive reinforcement via emoji reaction.

        Telegram reactions are not available on all clients, so this call is
        best-effort and silently ignored when unsupported.
        """
        if correction_suggestions:
            return

        message = update.message
        if not message:
            return

        for attr_name in ("react", "set_reaction"):
            reaction_callable = getattr(message, attr_name, None)
            if reaction_callable is None:
                continue

            try:
                result = reaction_callable("👏")
                if inspect.isawaitable(result):
                    await result
                return
            except TypeError:
                # Some methods may expect keyword arguments
                try:
                    result = reaction_callable(emoji="👏")
                    if inspect.isawaitable(result):
                        await result
                    return
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Reaction attempt failed (%s): %s", attr_name, exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Reaction attempt failed (%s): %s", attr_name, exc)
                return

    async def _schedule_daily_messages(self, application: Application) -> None:
        """Schedule simple daily messages at fixed times."""
        job_queue = application.job_queue
        if not job_queue:
            logger.warning("Job queue not available; scheduled messages disabled.")
            return

        timezone_name = DEFAULT_USER_TIMEZONE
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            logger.error(f"Invalid timezone {timezone_name}, using UTC")
            zone = timezone.utc

        # Create timezone-aware time objects
        morning_time = time(9, 0, tzinfo=zone)
        afternoon_time = time(14, 0, tzinfo=zone)
        evening_time = time(19, 0, tzinfo=zone)

        # Schedule morning message at 9:00 AM
        job_queue.run_daily(
            self._send_scheduled_message,
            time=morning_time,
            days=(0, 1, 2, 3, 4, 5, 6),  # Every day
            name="morning_message",
            data={"message_type": "morning"},
        )

        # Schedule afternoon message at 2:00 PM
        job_queue.run_daily(
            self._send_scheduled_message,
            time=afternoon_time,
            days=(0, 1, 2, 3, 4, 5, 6),  # Every day
            name="afternoon_message",
            data={"message_type": "afternoon"},
        )

        # Schedule evening message at 7:00 PM
        job_queue.run_daily(
            self._send_scheduled_message,
            time=evening_time,
            days=(0, 1, 2, 3, 4, 5, 6),  # Every day
            name="evening_message",
            data={"message_type": "evening"},
        )

        # Daily prune of old conversation data (keep last 30 days)
        job_queue.run_repeating(
            self._prune_tick,
            interval=24 * 60 * 60,
            first=10,
            name="prune_old_conversations",
        )

        logger.info("Scheduled daily messages: 9:00 AM, 2:00 PM, 7:00 PM")

    async def _send_scheduled_message(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a scheduled message to all authorized users."""
        message_type = context.job.data.get("message_type", "morning")
        messages = SCHEDULED_MESSAGES.get(message_type, SCHEDULED_MESSAGES["morning"])
        message = random.choice(messages)
        
        now_utc = datetime.now(timezone.utc)
        timezone_name = DEFAULT_USER_TIMEZONE
        
        # Send to all authorized users
        for user_id_str in AUTHORIZED_USER_IDS_SET:
            try:
                chat_id = int(user_id_str)
                await context.bot.send_message(chat_id=chat_id, text=message)
                await conversation_store.record_bot_activity(
                    user_id_str,
                    timezone_name,
                    now_utc,
                )
                logger.info(f"Sent {message_type} message to user {chat_id}")
            except Exception as exc:
                logger.error(f"Failed to send {message_type} message to {user_id_str}: {exc}", exc_info=True)

    def _resolve_timezone(self, update: Update) -> str:
        """
        Resolve the user's timezone.

        Telegram does not expose timezone directly. For now we default to the
        configured timezone but this hook allows future per-user overrides.
        """
        return DEFAULT_USER_TIMEZONE

    async def _prune_tick(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Periodic pruning of old conversation data (keep last 30 days)."""
        try:
            await conversation_store.prune_older_than_days(30)
            logger.info("Pruned conversation data older than 30 days")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to prune conversation data: %s", exc, exc_info=True)



def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()
