"""Main Telegram bot implementation."""
import inspect
import logging
import random
from datetime import datetime, timezone, timedelta
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
    ENGAGEMENT_CHECK_INTERVAL_SECONDS,
    MORNING_MESSAGE_HOUR,
)
from src.llm_client import llm_client
from src.personality import personality_system
from src.conversation_store import conversation_store, CorrectionEntry, UserEngagement
from src.correction import correction_analyzer, CorrectionSuggestion

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


FALLBACK_TECHNICAL = (
    "Ay, perdona... tengo un problema técnico. ¿Puedes intentar de nuevo en un momento? 😅"
)
FALLBACK_ERROR = "¡Ups! Algo salió mal. Por favor, inténtalo de nuevo."

MORNING_MESSAGES = [
    "¡Buenos días! ☀️ ¿Listo para practicar un poco de español conmigo hoy? Cuéntame algo divertido de tu mañana.",
    "¡Hola, cariño! Hoy quiero que me digas tres cosas por las que estás agradecido. ¿Te animas?",
    "Buenos días 🌅 Aquí en Madrid huele a café y churros. ¿Qué planes tienes para hoy?",
    "¡Arriba! 💪 Te propongo un mini reto: usa el pretérito perfecto en una frase sobre lo que has hecho esta mañana.",
    "¡Feliz día! 🎶 Hoy te dejo esta palabra para practicar: *aprovechar*. ¿Puedes usarla en una frase?",
    "¡Hola hola! 😊 ¿Sabías que hoy en Madrid hay un mercadillo precioso en El Rastro? ¿Qué mercadillo o mercado te gusta a ti?",
]

REENGAGEMENT_CHECKS = [
    (timedelta(hours=12), 1, "¿Todo bien? 😊 Estoy aquí cuando quieras seguir practicando."),
    (timedelta(hours=24), 2, "Te echo un poquito de menos... ¿Qué tal tu día? Cuéntame algo."),
    (timedelta(hours=48), 3, "¡Hola extraño! 😜 Hace dos días que no hablamos. ¿Te apetece ponerte al día?"),
    (timedelta(days=7), 4, "¡Hola! Solo quería recordarte que sigo aquí para ayudarte con tu español cuando quieras. 💛"),
]


class SpanishTutorBot:
    """Spanish Tutor Bot with personality."""
    
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.application.post_init = self._on_startup
        self._setup_handlers()

    async def _on_startup(self, application: Application):
        """Ensure supporting services are ready before handling updates."""
        await conversation_store.initialize()
        logger.info("SpanishTutorBot startup complete.")
        await self._schedule_engagement_jobs(application)
    
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
        logger.info(f"User {user.id} ({user.username}) started the bot")
        
        greeting = personality_system.get_greeting_message()
        await update.message.reply_text(greeting)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
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
        
        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)
        
        response_text = None
        correction_suggestions: list[CorrectionSuggestion] = []
        try:
            # Build conversation messages for LLM
            system_prompt = personality_system.get_system_prompt()

            # Analyze message for potential corrections
            correction_suggestions = await correction_analyzer.analyze(user_message)
            correction_hint = ""
            if correction_suggestions:
                hint_lines = []
                for suggestion in correction_suggestions:
                    hint_lines.append(
                        f"- Tipo: {suggestion.error_type}; original: \"{suggestion.original_text}\"; corrección: \"{suggestion.corrected_text}\". Explica brevemente: {suggestion.explanation}"
                    )
                correction_hint = (
                    "\nCORRECCIONES DETECTADAS:\n"
                    + "\n".join(hint_lines)
                    + "\nIntegra estas correcciones de forma natural usando el método sandwich y un tono positivo. "
                    "No enumeres literalmente las correcciones; incorpóralas en tu respuesta."
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

    async def _schedule_engagement_jobs(self, application: Application) -> None:
        """Register background engagement jobs."""
        job_queue = application.job_queue
        if not job_queue:
            logger.warning("Job queue not available; scheduled events disabled.")
            return

        job_queue.run_repeating(
            self._engagement_tick,
            interval=ENGAGEMENT_CHECK_INTERVAL_SECONDS,
            first=0,
            name="engagement_tick",
        )
        logger.info(
            "Scheduled engagement job every %s seconds",
            ENGAGEMENT_CHECK_INTERVAL_SECONDS,
        )

    async def _engagement_tick(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Periodic engagement check for morning pings and inactivity reminders.

        This job runs frequently but may choose not to send anything if the
        criteria are not met.
        """
        now_utc = datetime.now(timezone.utc)
        try:
            engagements = await conversation_store.get_all_engagements()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to retrieve engagement data: %s", exc, exc_info=True)
            return

        for engagement in engagements:
            timezone_name = engagement.timezone or DEFAULT_USER_TIMEZONE
            try:
                zone = ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError:
                zone = ZoneInfo(DEFAULT_USER_TIMEZONE)
                logger.debug("Unknown timezone %s for user %s. Using default.", timezone_name, engagement.user_id)

            local_now = now_utc.astimezone(zone)
            user_chat_id = int(engagement.user_id)

            await self._maybe_send_morning_message(
                context,
                user_chat_id,
                engagement,
                timezone_name,
                local_now,
                now_utc,
            )
            await self._maybe_send_reengagement_message(
                context,
                user_chat_id,
                engagement,
                timezone_name,
                now_utc,
            )

    async def _maybe_send_morning_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        engagement: UserEngagement,
        timezone_name: str,
        local_now: datetime,
        now_utc: datetime,
    ) -> None:
        """Send a morning ping if it hasn't been delivered today."""
        if local_now.hour < MORNING_MESSAGE_HOUR or local_now.hour >= MORNING_MESSAGE_HOUR + 2:
            return

        if engagement.last_morning_ping_date == local_now.date():
            return

        message = random.choice(MORNING_MESSAGES)
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            await conversation_store.mark_morning_ping(
                str(chat_id),
                timezone_name,
                local_now.date(),
            )
            await conversation_store.record_bot_activity(
                str(chat_id),
                timezone_name,
                now_utc,
            )
            logger.info("Sent morning ping to user %s", chat_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to send morning message to %s: %s", chat_id, exc, exc_info=True)

    async def _maybe_send_reengagement_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        engagement: UserEngagement,
        timezone_name: str,
        now_utc: datetime,
    ) -> None:
        """Send inactivity reminders based on last user message time."""
        last_user_message = engagement.last_user_message_at
        if not last_user_message:
            return

        idle_time = now_utc - last_user_message
        for threshold, level, text in REENGAGEMENT_CHECKS:
            if idle_time >= threshold and engagement.reengagement_level < level:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                    await conversation_store.update_reengagement_level(
                        str(chat_id),
                        timezone_name,
                        level,
                    )
                    await conversation_store.record_bot_activity(
                        str(chat_id),
                        timezone_name,
                        now_utc,
                    )
                    logger.info(
                        "Sent re-engagement level %s message to user %s after %s hours.",
                        level,
                        chat_id,
                        idle_time.total_seconds() / 3600.0,
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("Failed to send re-engagement message to %s: %s", chat_id, exc, exc_info=True)
                finally:
                    break

    def _resolve_timezone(self, update: Update) -> str:
        """
        Resolve the user's timezone.

        Telegram does not expose timezone directly. For now we default to the
        configured timezone but this hook allows future per-user overrides.
        """
        return DEFAULT_USER_TIMEZONE


def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()
