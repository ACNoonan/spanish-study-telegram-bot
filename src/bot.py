"""Main Telegram bot implementation."""
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
from src.conversation_store import conversation_store

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
        try:
            # Build conversation messages for LLM
            system_prompt = personality_system.get_system_prompt()
            
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


def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()

