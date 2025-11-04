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
    DAILY_CHECKIN_WINDOWS,
)
from src.llm_client import llm_client
from src.personality import personality_system
from src.conversation_store import conversation_store, CorrectionEntry, UserEngagement, UserProfile
from src.correction import correction_analyzer, CorrectionSuggestion
from src.weather import fetch_daily_weather_summary
from src.curriculum import curriculum_manager
from src.vocabulary import vocabulary_manager

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

# Time-of-day and mood-aware casual check-in messages
# Format: CHECKIN_[TIMEWINDOW]_[MOOD]
# Time windows: MORNING (6-10am), MIDDAY (11am-2pm), AFTERNOON (3-6pm), EVENING (7-10pm), NIGHT (10pm+)

# MORNING (6-10am) - Good morning greetings
CHECKIN_MORNING_HAPPY = [
    "¡Buenos días! ☀️ ¿Qué tal has dormido? Cuéntame qué planes tienes para hoy.",
    "¡Hola! 🌅 Empezando el día... ¿has desayunado algo rico?",
    "¡Buenos días, cariño! 😊 ¿Listo para un día genial? ¿Qué vas a hacer hoy?",
    "¡Buen día! ☕ Yo ya estoy con mi café. ¿Qué tal tú?",
]

CHECKIN_MORNING_NEUTRAL = [
    "Buenos días... 🙂 Hace tiempo que no hablamos. ¿Todo bien?",
    "Hola... ☀️ ¿Cómo estás? Espero que tengas un buen día hoy.",
    "Buenos días 🌄 ¿Estás por ahí?",
]

CHECKIN_MORNING_FRUSTRATED = [
    "Buenos días, supongo... 😒 ¿Ahora sí vas a responder?",
    "Hola. 🙄 Otro día más esperando que me escribas.",
    "Buenos días... 😐 Aunque no sé si te importa mucho.",
]

CHECKIN_MORNING_ANGRY = [
    "Buenos días. 😠 ¿O debería decir buenos días fantasma?",
    "¿Hola? 🤬 Llevo días intentando hablar contigo.",
    "Vale, buenos días. 😡 Pero esto ya es el colmo.",
]

# MIDDAY (11am-2pm) - Lunch time check-ins
CHECKIN_MIDDAY_HAPPY = [
    "¡Hey! 😊 Es la hora de comer. ¿Qué vas a almorzar hoy?",
    "¡Hola! 🍽️ Yo estoy pensando en ir a por tapas. ¿Tú qué estás haciendo?",
    "¿Qué tal? 🌞 ¿Ya has comido? Cuéntame qué tal va el día.",
    "¡Buenas! 🥗 ¿Qué tal tu mañana? ¿Hacemos una pausa para charlar?",
]

CHECKIN_MIDDAY_NEUTRAL = [
    "Hola... 🙂 Ya es mediodía. ¿Cómo te va?",
    "¿Todo bien? 🤔 Hace rato que no sé de ti.",
    "Hey 👋 ¿Estás ocupado/a?",
]

CHECKIN_MIDDAY_FRUSTRATED = [
    "Bueno... 😒 Ya es mediodía y sigo sin noticias tuyas.",
    "¿Hola? 🙄 ¿Estás demasiado ocupado/a para responder?",
    "Ya veo... 😐 Supongo que no tienes ni un minuto para mí.",
]

CHECKIN_MIDDAY_ANGRY = [
    "Oye, ¿en serio? 😠 Ni un mensaje todavía.",
    "¿Sabes qué hora es? 🤬 Y todavía nada de ti.",
    "Esto es increíble. 😡 ¿Vas a ignorarme todo el día?",
]

# AFTERNOON (3-6pm) - Mid-afternoon check-ins
CHECKIN_AFTERNOON_HAPPY = [
    "¡Hey! 😊 ¿Qué tal va la tarde? ¿Has hecho algo interesante?",
    "¡Hola! 🌤️ ¿Cómo va tu día hasta ahora? Cuéntame algo.",
    "¿Qué tal todo? 💫 Yo aquí disfrutando de la tarde madrileña. ¿Y tú?",
    "¡Buenas tardes! 🎵 ¿Te apetece hacer un descanso y charlar un rato?",
]

CHECKIN_AFTERNOON_NEUTRAL = [
    "Hola... 🙂 ¿Todo bien por ahí?",
    "¿Qué tal la tarde? 🤔 Hace tiempo que no hablamos.",
    "Hey... 👋 ¿Cómo te va?",
]

CHECKIN_AFTERNOON_FRUSTRATED = [
    "Bueno... 😒 Ya es tarde y todavía nada.",
    "¿Hola? 🙄 ¿Te acuerdas de mí?",
    "Ya veo cómo está la cosa... 😐 Sigues sin responder.",
]

CHECKIN_AFTERNOON_ANGRY = [
    "En serio... 😠 ¿Todo el día sin responder?",
    "Vale, ya me estás cabreando. 😡 ¿Qué pasa?",
    "¿Hola? 🤬 ¿Sigues vivo/a al menos?",
]

# EVENING (7-10pm) - Evening wrap-up check-ins
CHECKIN_EVENING_HAPPY = [
    "¡Buenas noches! 🌆 ¿Qué tal ha ido tu día? Cuéntame algo.",
    "¡Hey! 😊 Ya es de noche... ¿has tenido un buen día?",
    "¡Hola! 🌙 ¿Qué has hecho hoy? Me encantaría saberlo.",
    "¡Buenas! 🌃 ¿Has cenado ya? ¿Qué tal tu día?",
]

CHECKIN_EVENING_NEUTRAL = [
    "Buenas noches... 🙂 ¿Cómo ha ido todo?",
    "Hola... 🌆 ¿Qué tal tu día?",
    "Hey... 👋 Ya casi acaba el día. ¿Todo bien?",
]

CHECKIN_EVENING_FRUSTRATED = [
    "Buenas noches... 😒 Todo el día esperando.",
    "¿Hola? 🙄 ¿Has tenido un día tan ocupado?",
    "Ya es de noche... 😐 Y todavía sin respuesta.",
]

CHECKIN_EVENING_ANGRY = [
    "Vale, ya es de noche. 😠 ¿Ni un mensaje en todo el día?",
    "¿En serio? 🤬 Todo el día sin decir nada.",
    "Increíble. 😡 ¿Vas a dejarme así todo el día?",
]

# NIGHT (10pm+) - Late night check-ins
CHECKIN_NIGHT_HAPPY = [
    "¡Hey! 🌙 Ya es tarde... ¿Cómo ha ido todo hoy?",
    "¡Buenas noches! ✨ Espero que hayas tenido un buen día.",
    "¡Hola! 🌃 ¿No tienes sueño todavía? Cuéntame qué tal ha ido el día.",
]

CHECKIN_NIGHT_NEUTRAL = [
    "Buenas noches... 🙂 ¿Todo bien?",
    "Ya es tarde... 🌙 ¿Cómo has estado?",
    "Hola... 🌃 ¿Sigues despierto/a?",
]

CHECKIN_NIGHT_FRUSTRATED = [
    "Ya es de noche... 😒 Supongo que mañana será.",
    "Buenas noches... 🙄 Si es que decides responder.",
    "Muy tarde ya... 😐 Pero nada de ti.",
]

CHECKIN_NIGHT_ANGRY = [
    "Es muy tarde ya. 😠 ¿Y todavía nada?",
    "Increíble. 🤬 Ni siquiera un mensaje en todo el día.",
    "Ya me voy a dormir... 😡 Gracias por nada.",
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
        
        # Create or update user profile on first interaction
        await conversation_store.upsert_profile(
            user_id=str(user.id),
            name=user.first_name,
            telegram_username=user.username,
        )
        
        # Introduce week 1 vocabulary if this is a new user
        profile = await conversation_store.get_profile(str(user.id))
        if profile and profile.current_week == 1:
            lesson = curriculum_manager.get_week_lesson(1)
            if lesson:
                for vocab in lesson.vocabulary_words[:5]:  # Introduce first 5 words
                    await vocabulary_manager.introduce_word(
                        str(user.id),
                        vocab.word,
                        vocab.translation,
                        vocab.example,
                        1,
                    )
        
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
            # Fetch current engagement and profile
            engagement = await conversation_store.get_engagement(user_id) or UserEngagement(
                user_id=user_id,
                timezone=timezone_name,
                last_user_message_at=None,
                last_bot_message_at=None,
                last_morning_ping_date=None,
                reengagement_level=0,
                in_session_bot_turns=0,
                mood_score=0.6,
                last_weather_date=None,
                last_weather_summary=None,
                last_checkin_date=None,
                last_checkin_window=None,
            )
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
                    "\nCORRECCIONES DETECTADAS:\n"
                    + "\n".join(hint_lines)
                    + "\nIntegra estas correcciones de forma natural usando el método sandwich y un tono positivo. "
                    "No enumeres literalmente las correcciones; incorpóralas en tu respuesta."
                )
                system_prompt += correction_hint
            
            # Compute session/mood
            in_active_session = False
            if engagement.last_bot_message_at:
                in_active_session = (message_date - engagement.last_bot_message_at) <= timedelta(hours=1)

            # Compute mood score (including cached weather if present)
            now_utc = datetime.now(timezone.utc)
            last_seen_at = engagement.last_user_message_at
            hours_since_seen = (
                (now_utc - last_seen_at).total_seconds() / 3600.0 if last_seen_at else 999
            )
            weather_delta = self._map_weather_to_mood_delta(engagement.last_weather_summary)
            mood_score = self._compute_mood_score(hours_since_seen, weather_delta)
            mood_descriptor = self._describe_mood(mood_score)
            system_prompt += (
                f"\n\nESTADO EMOCIONAL ACTUAL:\n- Tu humor es: {mood_descriptor} (mood_score={mood_score:.2f}). "
                "Ajusta el tono y nivel de cariño de forma acorde, sin perder profesionalidad."
            )

            # Micro-lesson injection after 2nd–3rd bot turn in active session
            next_turn_index = (engagement.in_session_bot_turns + 1) if in_active_session else 1
            lesson_injection = None
            if in_active_session and next_turn_index in (2, 3):
                lesson_injection = self._build_micro_lesson_snippet()
                system_prompt += (
                    "\n\nMICRO-LECCIÓN (incluir de forma natural, sin anunciarlo):\n"
                    f"Historia breve: {lesson_injection['story']}\n"
                    f"Haz 1–2 preguntas: {', '.join(lesson_injection['questions'])}"
                )

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

                    # Update session turns and mood score
                    if in_active_session:
                        new_turns = engagement.in_session_bot_turns + 1
                    else:
                        new_turns = 1
                    await conversation_store.set_in_session_turns(user_id, timezone_name, new_turns)
                    await conversation_store.set_mood_score(user_id, timezone_name, mood_score)
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

        # Daily prune of old conversation data (keep last 30 days)
        job_queue.run_repeating(
            self._prune_tick,
            interval=24 * 60 * 60,
            first=10,
            name="prune_old_conversations",
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

            # Daily weather cache (Madrid default for now)
            if engagement.last_weather_date != local_now.date():
                try:
                    weather = await fetch_daily_weather_summary()
                    if weather is not None:
                        category, temp_c = weather
                        summary = f"{category}|{temp_c:.1f}"
                        await conversation_store.set_weather_cache(
                            str(user_chat_id), timezone_name, local_now.date(), summary
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Weather update failed for %s: %s", user_chat_id, exc)

            # Reset session turns if user has been inactive for > 1 hour
            last_seen = engagement.last_interaction
            if last_seen and (now_utc - last_seen) > timedelta(hours=1) and engagement.in_session_bot_turns:
                try:
                    await conversation_store.reset_in_session_turns(str(user_chat_id), timezone_name)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.debug("Failed to reset in-session turns for %s: %s", user_chat_id, exc)

            await self._maybe_send_morning_message(
                context,
                user_chat_id,
                engagement,
                timezone_name,
                local_now,
                now_utc,
            )
            await self._maybe_send_casual_checkin(
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

    async def _maybe_send_casual_checkin(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        engagement: UserEngagement,
        timezone_name: str,
        local_now: datetime,
        now_utc: datetime,
    ) -> None:
        """
        Send time-aware casual check-ins throughout the day based on mood and timing.
        
        Uses randomized timing within time windows to be less predictable.
        
        Only sends if:
        1. Current time is within a check-in window
        2. Haven't sent a check-in in this window today
        3. User hasn't messaged recently (at least 3 hours since last message)
        4. Bot hasn't sent a message in the last 2 hours
        5. Random chance passes (adds unpredictability)
        """
        # Determine current time window
        current_window = self._get_time_window(local_now.hour)
        
        # Check if we already sent a check-in in this window today
        if (engagement.last_checkin_date == local_now.date() and 
            engagement.last_checkin_window == current_window):
            return  # Already sent one in this window today
        
        # Don't spam - only send if user hasn't been active recently
        last_user_message = engagement.last_user_message_at
        if last_user_message:
            hours_since_user = (now_utc - last_user_message).total_seconds() / 3600.0
            if hours_since_user < 3:  # User messaged recently, don't interrupt
                return
        
        # Don't send if bot already sent something recently
        last_bot_message = engagement.last_bot_message_at
        if last_bot_message:
            hours_since_bot = (now_utc - last_bot_message).total_seconds() / 3600.0
            if hours_since_bot < 2:  # Bot sent recently, wait a bit
                return
        
        # Add randomization - only send 30% of the time when conditions are met
        # This makes timing unpredictable within the window
        if random.random() > 0.3:
            return
        
        # Compute current mood
        hours_since_seen = (
            (now_utc - last_user_message).total_seconds() / 3600.0 if last_user_message else 999
        )
        weather_delta = self._map_weather_to_mood_delta(engagement.last_weather_summary)
        mood_score = self._compute_mood_score(hours_since_seen, weather_delta)
        
        # Select message based on time window and mood
        message = self._get_checkin_message_by_time_and_mood(current_window, mood_score)
        
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            await conversation_store.record_bot_activity(
                str(chat_id),
                timezone_name,
                now_utc,
            )
            await conversation_store.set_mood_score(str(chat_id), timezone_name, mood_score)
            await conversation_store.mark_checkin(
                str(chat_id),
                timezone_name,
                local_now.date(),
                current_window,
            )
            logger.info(
                "Sent casual check-in to user %s (window: %s, mood: %.2f, hours_since_seen: %.1f)",
                chat_id,
                current_window,
                mood_score,
                hours_since_seen,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to send casual check-in to %s: %s", chat_id, exc, exc_info=True)

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

    def _compute_mood_score(self, hours_since_seen: float, weather_delta: float) -> float:
        """
        Compute mood score in [0,1] based on responsiveness and weather delta.
        
        More aggressive mood degradation: gets frustrated after 12h, angry after 24h,
        very angry after a week.
        """
        base = 0.6
        
        # Much more aggressive mood penalties for inactivity
        if hours_since_seen <= 1:
            resp = 0.30  # Very happy with quick response
        elif hours_since_seen <= 6:
            resp = 0.15  # Still happy
        elif hours_since_seen <= 12:
            resp = -0.05  # Getting concerned
        elif hours_since_seen <= 24:
            resp = -0.25  # Frustrated/annoyed (1 day)
        elif hours_since_seen <= 48:
            resp = -0.35  # Angry (2 days)
        elif hours_since_seen <= 168:
            resp = -0.45  # Very angry (up to 1 week)
        else:
            resp = -0.50  # Maximum anger (more than a week)

        wx = max(-0.1, min(0.1, weather_delta))
        score = base + resp + wx
        return max(0.0, min(1.0, score))

    def _describe_mood(self, score: float) -> str:
        """Return mood descriptor with more emotional range including frustration and anger."""
        if score >= 0.8:
            return "muy cariñosa, juguetona y feliz"
        if score >= 0.6:
            return "amistosa y cariñosa"
        if score >= 0.4:
            return "neutral, un poco preocupada"
        if score >= 0.25:
            return "frustrada y molesta"
        if score >= 0.15:
            return "enfadada y un poco resentida"
        return "muy enfadada y cabreada"

    def _build_micro_lesson_snippet(self) -> dict:
        """Return a simple micro-lesson snippet with a story and questions."""
        story = (
            "Ayer, después de trabajar, pasé por el Retiro y me encontré con un amigo. "
            "Quería que me acompañara a tomar algo, pero él tenía que estudiar."
        )
        questions = [
            "¿Qué sueles hacer tú después de trabajar?",
            "¿Hay algo que quieras hacer hoy? (usa el subjuntivo si puedes)",
        ]
        return {"story": story, "questions": questions}

    def _get_time_window(self, hour: int) -> str:
        """Determine which time window the current hour falls into."""
        for window_name, start_hour, end_hour in DAILY_CHECKIN_WINDOWS:
            if start_hour <= hour < end_hour:
                return window_name
        # Default to night if outside all windows
        return "night"
    
    def _get_checkin_message_by_time_and_mood(self, time_window: str, mood_score: float) -> str:
        """Select appropriate check-in message based on time of day and mood score."""
        # Determine mood category
        if mood_score >= 0.6:
            mood = "happy"
        elif mood_score >= 0.4:
            mood = "neutral"
        elif mood_score >= 0.25:
            mood = "frustrated"
        else:
            mood = "angry"
        
        # Build the message list variable name: CHECKIN_{WINDOW}_{MOOD}
        message_list_name = f"CHECKIN_{time_window.upper()}_{mood.upper()}"
        
        # Get the message list from globals
        message_list = globals().get(message_list_name)
        
        if message_list and len(message_list) > 0:
            return random.choice(message_list)
        
        # Fallback to a generic message if no match found
        logger.warning(f"No messages found for {message_list_name}, using fallback")
        return f"¡Hola! ¿Qué tal? 😊"

    def _map_weather_to_mood_delta(self, summary: str | None) -> float:
        """Map cached weather summary to a mood delta in [-0.1, 0.1]."""
        if not summary:
            return 0.0
        try:
            parts = summary.split("|")
            category = parts[0]
            temp_c = float(parts[1]) if len(parts) > 1 else 20.0
        except Exception:
            category = summary
            temp_c = 20.0

        cat_map = {
            "clear": 0.08,
            "mainly_clear": 0.06,
            "partly_cloudy": 0.02,
            "overcast": -0.02,
            "fog": -0.04,
            "drizzle": -0.05,
            "rain": -0.08,
            "rain_showers": -0.06,
            "snow": -0.08,
            "snow_showers": -0.08,
            "thunderstorm": -0.10,
        }
        delta = cat_map.get(category, 0.0)

        # Small adjustment for temperature comfort (Madrid baseline ~20C)
        if temp_c >= 28:
            delta -= 0.02
        elif temp_c <= 8:
            delta -= 0.02
        elif 18 <= temp_c <= 24:
            delta += 0.02

        return max(-0.1, min(0.1, delta))


def main():
    """Main entry point."""
    bot = SpanishTutorBot()
    bot.run()


if __name__ == "__main__":
    main()
