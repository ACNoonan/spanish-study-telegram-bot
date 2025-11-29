"""Main Telegram bot implementation."""
import asyncio
import inspect
import logging
import random
from datetime import datetime, timezone, time
from typing import Optional
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
from src.vocabulary import vocabulary_manager
from src.weather import fetch_daily_weather_summary
from src.review_session import review_session_manager
from src.voice_handler import voice_handler

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

# Scheduled message prompts - AI will generate unique personal messages
SCHEDULED_MESSAGE_PROMPTS = {
    "morning": """Genera un mensaje CORTO de buenos días como Sofía. Comparte algo personal sobre:
- Lo que vas a hacer hoy en Madrid
- Cómo te sientes esta mañana
- Algo que te emocionó al despertar
- Un plan que tienes para el día

SIEMPRE termina preguntándole al usuario sobre su día, sus planes, o cómo se siente.
Máximo 3-4 frases cortas. Sé cálida y natural.""",
    
    "afternoon": """Genera un mensaje CORTO de la tarde como Sofía. Comparte algo personal sobre:
- Qué has hecho esta mañana
- Algo interesante que te pasó hoy
- Dónde estás ahora (café, casa, parque)
- Algo que estás pensando o sintiendo

SIEMPRE termina preguntándole al usuario cómo va su día o qué está haciendo.
Máximo 3-4 frases cortas. Sé cálida y curiosa.""",
    
    "evening": """Genera un mensaje CORTO de la noche como Sofía. Comparte algo personal sobre:
- Cómo fue tu día
- Una pequeña historia de algo que te pasó hoy
- Tus planes para esta noche
- Algo en lo que estás pensando

SIEMPRE termina preguntándole al usuario sobre su día o qué tal le fue.
Máximo 3-4 frases cortas. Sé cálida y reflexiva.""",
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
        self.application.add_handler(CommandHandler("vocab", self.vocab_command))
        self.application.add_handler(CommandHandler("progress", self.progress_command))
        self.application.add_handler(CommandHandler("advance", self.advance_command))
        
        # Message handlers
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
        self.application.add_handler(
            MessageHandler(filters.VOICE, self.handle_voice_message)
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
    
    async def vocab_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /vocab command - start vocabulary review session."""
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} attempted /vocab")
            return
        
        # Check if already in a review session
        if review_session_manager.has_active_session(user_id):
            await update.message.reply_text(
                "Ya estamos en medio de un repaso, guapo 😊 Sigamos con ese."
            )
            return
        
        # Get due vocabulary cards
        due_cards = await vocabulary_manager.get_due_words(user_id, limit=10)
        
        if not due_cards:
            await update.message.reply_text(
                "¡Genial! No tienes palabras pendientes ahora mismo 🎉\n"
                "Sigue practicando y pronto tendrás más para repasar."
            )
            return
        
        # Create review session
        review_session_manager.create_session(user_id, due_cards)
        
        await update.message.reply_text(
            f"Vale, vamos a repasar {len(due_cards)} palabras 😊\n\n"
            f"Responde de forma natural. Si quieres parar, escribe 'para' o 'stop'."
        )
        
        # Send first card
        await self._send_vocab_card(update, user_id)
    
    async def progress_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /progress command - show learning progress."""
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} attempted /progress")
            return
        
        try:
            # Get profile
            profile = await conversation_store.get_profile(user_id)
            if not profile:
                await update.message.reply_text(
                    "Hmm, parece que no encuentro tu perfil. Usa /start primero 😊"
                )
                return
            
            # Get vocabulary stats
            vocab_stats = await vocabulary_manager.get_mastery_stats(user_id)
            
            # Get review stats
            review_stats = await conversation_store.get_review_stats(user_id, days=14)
            
            # Get current lesson info
            lesson = curriculum_manager.get_week_lesson(profile.current_week)
            lesson_title = lesson.title if lesson else "Unknown"
            
            # Build progress message
            progress_text = (
                f"📊 *Tu Progreso*\n\n"
                f"🎯 *Nivel actual:* {profile.current_level}\n"
                f"📅 *Semana:* {profile.current_week} de {curriculum_manager.get_total_weeks()}\n"
                f"📚 *Tema actual:* {lesson_title}\n\n"
                f"*Vocabulario:*\n"
                f"• Total: {vocab_stats['total']} palabras\n"
                f"• Dominadas: {vocab_stats['mastered']} ✅\n"
                f"• En aprendizaje: {vocab_stats['learning']} 📝\n"
                f"• Nuevas: {vocab_stats['new']} 🆕\n\n"
                f"*Últimas 2 semanas:*\n"
                f"• Sesiones de repaso: {review_stats['session_count']}\n"
                f"• Palabras repasadas: {review_stats['total_cards_reviewed']}\n"
            )
            
            await update.message.reply_text(progress_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in progress_command: {e}", exc_info=True)
            await update.message.reply_text(
                "Ay perdona, ha habido un problema al cargar tu progreso 😅"
            )
    
    async def advance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /advance command - manually advance to next week."""
        user = update.effective_user
        user_id = str(user.id)
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} attempted /advance")
            return
        
        try:
            profile = await conversation_store.get_profile(user_id)
            if not profile:
                await update.message.reply_text(
                    "Hmm, parece que no encuentro tu perfil. Usa /start primero 😊"
                )
                return
            
            current_week = profile.current_week
            total_weeks = curriculum_manager.get_total_weeks()
            
            if current_week >= total_weeks:
                await update.message.reply_text(
                    "¡Ya has completado todo el currículum, guapo! 🎉\n"
                    "Sigue practicando y perfeccionando tu español."
                )
                return
            
            new_week = current_week + 1
            await conversation_store.upsert_profile(user_id=user_id, current_week=new_week)
            
            lesson = curriculum_manager.get_week_lesson(new_week)
            lesson_title = lesson.title if lesson else "Unknown"
            
            await update.message.reply_text(
                f"¡Genial! Avanzamos a la semana {new_week} 🎉\n\n"
                f"📚 Nuevo tema: *{lesson_title}*\n\n"
                f"Vamos a practicar esto de forma natural en nuestras conversaciones 😊"
                ,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in advance_command: {e}", exc_info=True)
            await update.message.reply_text(
                "Ay perdona, ha habido un problema 😅"
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        user = update.effective_user
        user_message = update.message.text.strip()
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
        
        # Check for exit keywords FIRST (highest priority)
        exit_keywords = ["para", "stop", "luego", "salir", "later", "exit"]
        if user_message.lower() in exit_keywords and review_session_manager.has_active_session(user_id):
            await self._exit_review_session(update, user_id, reason="user_request")
            return
        
        # Check if user is in an active review session
        if review_session_manager.has_active_session(user_id):
            session = review_session_manager.get_session(user_id)
            
            # Check for timeout
            if session and session.is_inactive(timeout_minutes=10):
                await self._exit_review_session(update, user_id, reason="timeout")
                # Now process message as normal conversation
                await self._handle_normal_conversation(update, context, user_message, user_id, timezone_name, message_date)
            else:
                # Process as review response
                await self._handle_review_response(update, user_message, user_id)
            return
        
        # Normal conversation handling
        await self._handle_normal_conversation(update, context, user_message, user_id, timezone_name, message_date)
    
    async def handle_voice_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming voice messages."""
        user = update.effective_user
        user_id = str(user.id)
        timezone_name = self._resolve_timezone(update)
        
        message_date = update.message.date or datetime.now(timezone.utc)
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        
        logger.info(f"Voice message from {user.id}")
        
        # Check if user is authorized
        if user_id not in AUTHORIZED_USER_IDS_SET:
            logger.warning(f"Unauthorized user {user.id} (@{user.username}) attempted to send voice message")
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
        
        try:
            # Get the voice file
            voice_file = await update.message.voice.get_file()
            
            # Transcribe the voice message
            transcribed_text = await voice_handler.transcribe_voice(voice_file)
            
            if not transcribed_text:
                await update.message.reply_text(
                    "Ay perdona, cariño... no pude entender tu mensaje de voz 😅 ¿Puedes intentarlo otra vez?"
                )
                return
            
            logger.info(f"Transcribed voice from {user.id}: {transcribed_text}")
            
            # Process the transcribed text as a normal message
            response_text, corrections = await self._process_message_and_get_response(
                user_id, transcribed_text, timezone_name, message_date
            )
            
            if not response_text:
                response_text = FALLBACK_TECHNICAL
                await update.message.reply_text(response_text)
                return
            
            # Send corrections FIRST as a separate message (if any)
            if corrections:
                correction_message = self._format_correction_message(corrections)
                if correction_message:
                    await update.message.reply_text(
                        correction_message,
                        parse_mode='Markdown'
                    )
                    # Brief pause before the personality response
                    await asyncio.sleep(0.5)
            
            # Send text response
            await update.message.reply_text(response_text)
            
            # Generate voice response
            await update.message.chat.send_action(ChatAction.RECORD_VOICE)
            audio_data = await voice_handler.text_to_speech(response_text)
            
            if audio_data:
                # Send voice message
                await update.message.reply_voice(voice=audio_data)
                logger.info(f"Sent voice response to {user.id}")
            else:
                logger.warning(f"Could not generate voice response for {user.id}")
            
            # Proactive vocabulary review suggestion (occasionally)
            await self._maybe_suggest_vocab_review(update, user_id)
            
        except Exception as e:
            logger.error(f"Error handling voice message: {e}", exc_info=True)
            await update.message.reply_text(FALLBACK_ERROR)
    
    async def _process_message_and_get_response(
        self,
        user_id: str,
        user_message: str,
        timezone_name: str,
        message_date: datetime,
    ) -> tuple[Optional[str], list[CorrectionSuggestion]]:
        """
        Process a user message and generate a response.
        
        Returns a tuple of (response_text, correction_suggestions).
        Returns (None, []) on failure.
        Also stores conversation history and corrections.
        """
        response_text = None
        correction_suggestions: list[CorrectionSuggestion] = []
        try:
            # Get user profile for curriculum context
            profile = await conversation_store.get_profile(user_id)
            current_week = profile.current_week if profile else 1

            # Build conversation messages for LLM with curriculum context
            lesson_context = curriculum_manager.build_lesson_context_prompt(current_week)
            
            # Add weather context if available
            weather_context = ""
            weather_data = await fetch_daily_weather_summary()
            if weather_data:
                category, temp_c = weather_data
                weather_context = f"\n\nCONTEXTO DEL DÍA: En Madrid hoy está {category} con {temp_c:.0f}°C."
            
            system_prompt = personality_system.get_system_prompt(lesson_context=lesson_context) + weather_context

            # Analyze message for potential corrections (but DON'T add them to the system prompt)
            correction_suggestions = await correction_analyzer.analyze(user_message)

            history_messages = await conversation_store.get_recent_messages(user_id)

            messages = [{"role": "system", "content": system_prompt}]
            for history_message in history_messages:
                messages.append(
                    {"role": history_message.role, "content": history_message.content}
                )
            messages.append({"role": "user", "content": user_message})

            # Get response from LLM
            response_text = await llm_client.generate_response(messages)
            
            if not response_text:
                # Fallback if LLM fails
                response_text = FALLBACK_TECHNICAL
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            response_text = FALLBACK_ERROR
        
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
        
        return response_text, correction_suggestions
    
    def _format_correction_message(self, corrections: list[CorrectionSuggestion]) -> str:
        """
        Format corrections as a friendly, emoji-decorated message.
        
        This message is sent separately from the AI personality response.
        """
        if not corrections:
            return ""
        
        # Start with a friendly header
        header = "📝 *Pequeña corrección:*" if len(corrections) == 1 else "📝 *Pequeñas correcciones:*"
        message_parts = [header]
        
        for i, correction in enumerate(corrections, 1):
            # Add each correction with clear formatting
            message_parts.append(
                f"✏️ _{correction.original_text}_ → *{correction.corrected_text}*"
            )
            message_parts.append(f"💡 {correction.explanation}")
            
            # Add spacing between corrections (but not after the last one)
            if i < len(corrections):
                message_parts.append("")
        
        return "\n".join(message_parts)
    
    async def _handle_normal_conversation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_message: str,
        user_id: str,
        timezone_name: str,
        message_date: datetime,
    ):
        """Handle normal conversation (not in review mode)."""
        # Show typing indicator
        await update.message.chat.send_action(ChatAction.TYPING)
        
        try:
            # Process message and get response with corrections
            response_text, corrections = await self._process_message_and_get_response(
                user_id, user_message, timezone_name, message_date
            )
            
            if response_text:
                # Send corrections FIRST as a separate message (if any)
                if corrections:
                    correction_message = self._format_correction_message(corrections)
                    if correction_message:
                        await update.message.reply_text(
                            correction_message,
                            parse_mode='Markdown'
                        )
                        # Brief pause before the personality response
                        await asyncio.sleep(0.5)
                
                # Then send the AI personality response
                await update.message.reply_text(response_text)
                
                # Generate and send audio version of the response
                await update.message.chat.send_action(ChatAction.RECORD_VOICE)
                audio_data = await voice_handler.text_to_speech(response_text)
                if audio_data:
                    await update.message.reply_voice(voice=audio_data)
                else:
                    logger.warning(f"Could not generate voice response for {user_id}")
                
                # Proactive vocabulary review suggestion (occasionally)
                await self._maybe_suggest_vocab_review(update, user_id)
            else:
                # Fallback if processing fails
                await update.message.reply_text(FALLBACK_TECHNICAL)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text(FALLBACK_ERROR)

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

    async def _generate_scheduled_message(self, message_type: str) -> Optional[str]:
        """
        Generate a unique, personal scheduled message using AI.
        
        The message will have Sofía share something about her day and ask
        the user a question to encourage practice.
        """
        try:
            # Get the prompt template for this time of day
            prompt_template = SCHEDULED_MESSAGE_PROMPTS.get(
                message_type, 
                SCHEDULED_MESSAGE_PROMPTS["morning"]
            )
            
            # Build context with weather if available
            weather_context = ""
            weather_data = await fetch_daily_weather_summary()
            if weather_data:
                category, temp_c = weather_data
                weather_context = f"\n\nEl tiempo hoy en Madrid: {category}, {temp_c:.0f}°C. Puedes mencionarlo si encaja naturalmente."
            
            # Get profile for personality consistency
            profile = personality_system.profile
            
            system_prompt = f"""Eres {profile.get('name', 'Sofía')}, una profesora de español de {profile.get('age', 28)} años que vive en {profile.get('location', 'Madrid')}.

Tu personalidad:
- Cálida, cercana y un poco coqueta (pero apropiada)
- Usas expresiones cariñosas como 'guapo', 'cariño'
- Compartes cosas de tu vida cotidiana
- Te gusta conectar genuinamente con tu estudiante

{weather_context}

IMPORTANTE: 
- Escribe SOLO el mensaje, sin comillas ni explicaciones.
- NO uses emojis en exceso (máximo 1-2).
- Sé auténtica y varía el estilo, no repitas frases típicas.
- El mensaje debe sonar como un audio de WhatsApp de una amiga."""
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_template},
            ]
            
            # Generate with slightly higher temperature for variety
            response = await llm_client.generate_response(
                messages, 
                temperature=0.9,
                max_tokens=150,
            )
            
            if response:
                # Clean up any quotes or extra formatting
                response = response.strip().strip('"').strip("'")
                logger.info(f"Generated {message_type} message: {response[:50]}...")
                return response
            
            return None
            
        except Exception as e:
            logger.error(f"Error generating scheduled message: {e}", exc_info=True)
            return None
    
    async def _send_scheduled_message(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send an AI-generated scheduled message with audio to all authorized users."""
        message_type = context.job.data.get("message_type", "morning")
        
        now_utc = datetime.now(timezone.utc)
        timezone_name = DEFAULT_USER_TIMEZONE
        
        # Generate unique AI message
        message = await self._generate_scheduled_message(message_type)
        
        if not message:
            # Fallback to a simple message if AI generation fails
            fallback_messages = {
                "morning": "¡Buenos días, guapo! ¿Qué tal has dormido? 😊",
                "afternoon": "¡Hola! ¿Qué tal va tu día? Cuéntame algo 😊",
                "evening": "¡Buenas noches! ¿Cómo te fue hoy? 🌙",
            }
            message = fallback_messages.get(message_type, fallback_messages["morning"])
            logger.warning(f"Using fallback message for {message_type}")
        
        # Send to all authorized users
        for user_id_str in AUTHORIZED_USER_IDS_SET:
            try:
                chat_id = int(user_id_str)
                
                # Send text message first
                await context.bot.send_message(chat_id=chat_id, text=message)
                
                # Generate and send audio version
                audio_data = await voice_handler.text_to_speech(message)
                if audio_data:
                    await context.bot.send_voice(chat_id=chat_id, voice=audio_data)
                    logger.info(f"Sent {message_type} message + audio to user {chat_id}")
                else:
                    logger.warning(f"Could not generate audio for {message_type} message to {chat_id}")
                
                # Record bot activity
                await conversation_store.record_bot_activity(
                    user_id_str,
                    timezone_name,
                    now_utc,
                )
                
                # Store in conversation history for context
                await conversation_store.append_message(user_id_str, "assistant", message)
                
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
    
    async def _send_vocab_card(self, update: Update, user_id: str) -> None:
        """Send the current vocabulary card for review."""
        session = review_session_manager.get_session(user_id)
        if not session:
            return
        
        card = session.current_card
        if not card:
            return
        
        card_number = session.current_card_index + 1
        total_cards = len(session.cards)
        
        # Create a natural prompt based on the word
        prompt_message = (
            f"{card_number}/{total_cards}: *{card.word}*\n\n"
            f"Úsala en una frase o cuéntame algo usando esta palabra 😊"
        )
        
        if card.example:
            prompt_message += f"\n\n_Ejemplo: {card.example}_"
        
        await update.message.reply_text(prompt_message, parse_mode='Markdown')
    
    async def _handle_review_response(
        self,
        update: Update,
        user_message: str,
        user_id: str,
    ) -> None:
        """Handle a user's response during vocabulary review."""
        try:
            session = review_session_manager.get_session(user_id)
            if not session:
                # Session disappeared, fall back to normal conversation
                await update.message.reply_text(
                    "Hmm, parece que perdí el hilo. Sigamos charlando normalmente 😊"
                )
                return
            
            current_card = session.current_card
            if not current_card:
                return
            
            # Evaluate if they used the word correctly
            used_correctly = await self._evaluate_vocab_usage(user_message, current_card)
            
            # Determine quality score for SM-2 algorithm
            quality = 4 if used_correctly else 2
            
            # Save card progress immediately
            try:
                await vocabulary_manager.update_card_after_review(current_card.id, quality)
                logger.info(f"Updated card {current_card.id} for user {user_id} with quality {quality}")
            except Exception as e:
                logger.error(f"Failed to save card progress: {e}", exc_info=True)
                # Continue anyway - don't break the flow
            
            # Give feedback
            if used_correctly:
                feedback = random.choice([
                    "¡Perfecto! ✅",
                    "¡Muy bien! ✅",
                    "¡Excelente! 🌟",
                    "¡Genial, guapo! ✅",
                ])
            else:
                feedback = f"Casi, guapo 😊 Un ejemplo: _{current_card.example}_"
            
            await update.message.reply_text(feedback, parse_mode='Markdown')
            
            # Move to next card
            session.advance()
            
            if session.is_complete:
                # Review complete!
                await self._exit_review_session(update, user_id, reason="completion")
            else:
                # Brief pause then send next card
                await asyncio.sleep(0.5)
                await self._send_vocab_card(update, user_id)
                
        except Exception as e:
            logger.error(f"Error in review handler for {user_id}: {e}", exc_info=True)
            await self._exit_review_session(update, user_id, reason="error")
            await update.message.reply_text(
                "Ay perdona guapo, ha habido un problemita técnico 😅\n"
                "Tu progreso está guardado. ¿Seguimos charlando?"
            )
    
    async def _evaluate_vocab_usage(self, user_message: str, card) -> bool:
        """
        Evaluate if the user correctly used the vocabulary word.
        Simple check: word appears in their message.
        Could be enhanced with LLM evaluation in the future.
        """
        word_lower = card.word.lower()
        message_lower = user_message.lower()
        
        # Check if the word or its root appears
        # Simple heuristic - could be improved
        return word_lower in message_lower or any(
            word_lower in token for token in message_lower.split()
        )
    
    async def _exit_review_session(
        self,
        update: Update,
        user_id: str,
        reason: str = "user_request",
    ) -> None:
        """
        Gracefully exit review session with proper cleanup.
        
        Args:
            reason: "user_request", "timeout", "completion", "error"
        """
        session = review_session_manager.end_session(user_id)
        
        if not session:
            return  # No active session
        
        # Log exit
        cards_completed = session.cards_completed
        cards_total = len(session.cards)
        duration = (datetime.now(timezone.utc) - session.started_at).total_seconds()
        
        logger.info(
            f"Review session ended for {user_id}: {reason} "
            f"({cards_completed}/{cards_total} completed)"
        )
        
        # Save session stats to database for analytics
        try:
            await conversation_store.log_review_session(
                user_id=user_id,
                cards_total=cards_total,
                cards_completed=cards_completed,
                duration_seconds=duration,
                exit_reason=reason,
            )
        except Exception as e:
            logger.error(f"Failed to log review session: {e}")
        
        # Send appropriate message based on reason
        if reason == "user_request":
            remaining = cards_total - cards_completed
            await update.message.reply_text(
                f"Vale guapo, lo dejamos aquí 😊\n\n"
                f"Has repasado {cards_completed} de {cards_total} palabras. "
                f"Las {remaining} restantes las verás la próxima vez.\n\n"
                f"¿De qué quieres hablar?"
            )
        elif reason == "timeout":
            await update.message.reply_text(
                "Parece que te has distraído 😊 No pasa nada, seguimos cuando quieras."
            )
        elif reason == "completion":
            await update.message.reply_text(
                f"¡Has terminado! 🎉 Has repasado {cards_completed} palabras.\n\n"
                f"¿De qué quieres hablar ahora?"
            )
        # For "error", message already sent elsewhere
    
    async def _maybe_suggest_vocab_review(self, update: Update, user_id: str) -> None:
        """
        Occasionally suggest vocabulary review if user has many due cards.
        Only suggest once per day to avoid being annoying.
        """
        try:
            # Check if we already suggested today
            # For now, use a simple random check (20% chance)
            if random.random() > 0.2:
                return
            
            # Get due cards count
            due_cards = await vocabulary_manager.get_due_words(user_id, limit=5)
            
            if len(due_cards) >= 5:
                await update.message.reply_text(
                    f"Oye guapo, tienes {len(due_cards)} palabras esperando para repasar 📚\n"
                    f"¿Las repasamos? Usa /vocab cuando quieras 😊"
                )
        except Exception as e:
            logger.error(f"Error in suggest vocab review: {e}", exc_info=True)



def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()
