"""Main Telegram bot implementation."""
import inspect
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ChatAction

from src.config import TELEGRAM_BOT_TOKEN
from src.llm_client import llm_client
from src.personality import personality_system
from src.conversation_store import conversation_store, CorrectionEntry
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


def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()
