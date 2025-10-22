# Spanish Tutor Bot - Development Roadmap

## 📋 Project Overview
**Goal:** Create an engaging, AI-powered Spanish tutor bot that guides learners from B1 to B2 level through natural conversation, voice interaction, and visual content.

**Target User:** Intermediate Spanish learner seeking B1→B2 progression  
**Deployment:** Telegram bot with cloud LLM → self-hosted migration path  
**Estimated Timeline:** 16 weeks MVP, ongoing iteration

---

## 🎯 Phase 0: Foundation Setup
**Duration:** Week 1 | **Goal:** Working conversational bot with personality

### Milestone 0.1: Telegram Bot Infrastructure
**Tasks:**
- Set up Python 3.10+ environment with `python-telegram-bot>=20.0`
- Implement basic message handling (echo, commands: /start, /help)
- Configure webhook or polling (polling recommended for dev)

**Testing:**
- [ ] Bot receives and responds to text messages
- [ ] Command handling works correctly
- [ ] Error handling for network issues

**Tech Stack:**
- `python-telegram-bot` library (async)
- `python-dotenv` for config management

---

### Milestone 0.2: LLM Integration
**Tasks:**
- Set up OpenRouter account (https://openrouter.ai)
- Implement API wrapper with retry logic and rate limiting
- Start with cost-effective model for testing
- Add streaming response support (optional, better UX)

**Model Recommendations:**
| Model | Cost/1M tokens | Pros | Cons |
|-------|---------------|------|------|
| Meta Llama 3 8B | ~$0.10 | Fast, cheap | Less creative |
| Nous Hermes 2 Mixtral 8x7B | ~$0.50 | Good balance | Medium cost |
| GPT-4o-mini | ~$0.60 | High quality | OpenAI dependency |

**Start with:** Meta Llama 3 8B for development, upgrade to Mixtral for personality

**Testing:**
- [ ] API calls succeed with proper error handling
- [ ] Response latency < 3 seconds
- [ ] Spanish output is grammatically correct

**Implementation Notes:**
- Use environment variables for API keys (never commit!)
- Implement exponential backoff for rate limits
- Log all API calls for cost tracking

---

### Milestone 0.3: Character Personality System
**Tasks:**
- Design character profile (save as `character_profile.yaml`)
- Write layered system prompt (personality + tutoring role)
- Implement dynamic prompt injection based on context
- Add personality consistency checks

**Character Design Elements:**
```yaml
name: "Sofía"
age: 28
location: "Madrid, España"
background: "Language teacher, loves tapas and flamenco"
personality_traits:
  - flirty_level: 6/10 (context-aware)
  - humor: witty, uses Spanish cultural references
  - patience: high (it's her job!)
  - formality: informal (uses tú, not usted)
speech_patterns:
  - Uses "cariño", "guapo/a" occasionally
  - Mixes encouragement with gentle correction
  - Asks about your day/interests
  - Shares "her day" in Madrid
```

**System Prompt Structure:**
1. **Core Identity** (always present)
2. **Tutoring Behavior** (correction style, encouragement)
3. **Current Lesson Context** (injected dynamically)
4. **Conversation History** (last 10-20 messages)

**Testing:**
- [ ] Personality feels consistent across conversations
- [ ] Character stays in Spanish tutor role
- [ ] Flirtiness is appropriate, not creepy
- [ ] References Spanish culture naturally

**Deliverable:** Engaging chatbot with consistent personality that teaches Spanish conversationally

---

## 💬 Phase 1: Core Conversation Features
**Duration:** Week 2 | **Goal:** Context-aware tutoring with natural corrections

### Milestone 1.1: Conversation Memory System
**Database Choice:**
- **Development:** SQLite (simple, file-based)
- **Production:** PostgreSQL (better for concurrent users) or Redis (fast, ephemeral)

**Schema Design:**
```sql
-- conversations table
id, user_id, timestamp, user_message, bot_response, lesson_week, error_logged

-- user_profiles table
user_id, name, telegram_username, current_level, preferences, created_at

-- errors_log table
id, user_id, timestamp, error_type, incorrect_text, correct_form, grammar_topic
```

**Implementation:**
- Use SQLAlchemy ORM for database abstraction
- Implement conversation pruning (keep last 30 days)
- Context window: last 20 messages (~2000 tokens)
- Add user_id based session management

**Testing:**
- [ ] Bot recalls information from previous conversation
- [ ] Context window properly maintained
- [ ] Database queries are optimized (< 50ms)
- [ ] Handles new vs. returning users correctly

---

### Milestone 1.2: Intelligent Correction System
**Correction Strategies:**

1. **Gentle Sandwich Method:**
   - Acknowledge understanding ✓
   - Natural correction (embedded in response)
   - Continue conversation flow

   Example:
   - User: "*Yo fui a la playa ayer y nadar mucho*"
   - Bot: "¡Qué bien! Seguro que disfrutaste nadando en la playa. ¿El agua estaba fría?"
   - (Naturally models correct form without explicitly correcting)

2. **Explicit Teaching (for repeated errors):**
   - After 3rd occurrence, gentle explanation
   - "Por cierto, cuando hablamos del pasado, usamos 'nadé' en lugar de 'nadar' 😊"

**Error Detection Implementation:**
- **Option A:** Use spaCy Spanish model for basic grammar checking
- **Option B:** LLM-based detection (ask LLM to identify errors in separate API call)
- **Option C:** Hybrid approach (spaCy for common errors, LLM for nuanced ones)

**Error Categories to Track:**
- Verb conjugation (tense, mood, person)
- Gender agreement (noun-adjective)
- Ser vs. Estar
- Por vs. Para
- Subjunctive mood triggers
- Preposition usage

**Implementation:**
```python
# Example error detection flow
1. Store user message in DB
2. Check for error patterns (async, non-blocking)
3. Log errors to database
4. Decision: correct now or accumulate for later?
5. Generate response with natural correction
```

**Testing:**
- [ ] Corrections feel natural, not pedantic
- [ ] Bot doesn't over-correct (max 1-2 per message)
- [ ] Repeated errors trigger explanations
- [ ] Error logs populate correctly

---

### Milestone 1.3: Enhanced UX with Telegram Features
**Native Features to Implement:**

1. **Typing Indicators**
   ```python
   await context.bot.send_chat_action(
       chat_id=update.effective_chat.id,
       action=ChatAction.TYPING
   )
   ```

2. **Message Reactions** (Telegram Bot API 6.0+)
   - React to user's correct Spanish with 👏, ❤️, 🔥
   - React to complex sentences with 🤯, 🎉
   - Use contextually (don't overdo it)

3. **Text Formatting**
   - **Bold** for vocabulary emphasis
   - *Italic* for grammar notes
   - `Code blocks` for conjugation tables
   - [Links] to resources

4. **Interactive Elements (Future):**
   - Inline keyboards for quiz responses
   - Reply keyboards for quick responses

**Testing:**
- [ ] Typing indicator appears before response
- [ ] Reactions are contextually appropriate
- [ ] Formatting enhances readability
- [ ] No formatting breaks message display

**Deliverable:** Smart tutor that remembers context, corrects naturally, and feels human

---

## 📚 Phase 2: Structured Curriculum System
**Duration:** Week 3 | **Goal:** CEFR B1-aligned lesson progression

### Milestone 2.1: B1 Curriculum Design

**Core Grammar Topics (16-week progression):**

| Week | Primary Topic | Secondary Focus | Vocabulary Theme |
|------|--------------|-----------------|------------------|
| 1-2  | Subjunctive (present) intro | Regular verbs | Emotions & desires |
| 3-4  | Subjunctive triggers | WEIRDO acronym | Opinions & doubt |
| 5-6  | Por vs. Para mastery | Idiomatic uses | Travel & movement |
| 7-8  | Preterite vs. Imperfect nuances | Storytelling | Past experiences |
| 9-10 | Future & Conditional | Hypothetical situations | Plans & dreams |
| 11-12 | Ser vs. Estar (advanced) | + past participles | Descriptions |
| 13-14 | Commands (tú, usted, nosotros) | Indirect commands | Instructions & advice |
| 15-16 | Subjunctive (imperfect) | Conditional si clauses | Hypotheticals |

**Vocabulary Strategy:**
- 1,500 high-frequency B1 words (from Instituto Cervantes lists)
- 20-30 new words per week
- Spaced repetition: Review on days 1, 3, 7, 14, 30
- Thematic grouping (food, emotions, work, relationships, etc.)

**Madrid Cultural Integration:**
- Madrid slang: "tío/tía", "molar", "flipar", "guay"
- Food culture: "menú del día", tapas etiquette, "sobremesa"
- Local references: Retiro Park, Gran Vía, neighborhoods
- Customs: late dinners, siesta myth, greeting kisses

**Conversation Themes:**
- Week 1-4: Daily routines, hobbies, past experiences
- Week 5-8: Travel stories, opinions, giving advice
- Week 9-12: Hypotheticals, future plans, debates
- Week 13-16: Complex narratives, formal situations

**Data Storage:**
```python
# curriculum.yaml structure
lessons:
  week_1:
    grammar: ["subjunctive_intro", "present_subjunctive_regular"]
    vocabulary: ["emotions.yaml", "desires.yaml"]
    conversation_prompts: ["desires_prompt.txt"]
    cultural_topic: "spanish_greetings"
```

---

### Milestone 2.2: Adaptive Lesson Delivery

**Lesson State Machine:**
```python
1. Check user's current week (from user_profile)
2. Load week's curriculum content
3. Inject into system prompt as teaching goals
4. During conversation:
   - Naturally introduce target grammar
   - Use target vocabulary in responses
   - Create opportunities for practice
5. Track completion metrics
6. Advance to next week when ready
```

**Intelligent Weaving:**
- Don't announce "Today we're learning subjunctive!"
- Instead: Share a desire/emotion that requires subjunctive response
- Example: "Espero que tengas un buen día. ¿Hay algo que quieras hacer hoy?"
- User response will likely trigger subjunctive practice

**Morning Mini-Lessons:**
- Time: 8:00 AM Madrid time (configurable per user)
- Format options (rotate daily):
  - **Monday:** Grammar tip with example
  - **Tuesday:** 5 new vocabulary words
  - **Wednesday:** Cultural tidbit about Madrid
  - **Thursday:** Pronunciation tip
  - **Friday:** Weekend conversation starter
  - **Saturday:** Fun challenge/game
  - **Sunday:** Weekly progress recap

**Implementation:**
- Use APScheduler or Celery for scheduled messages
- Store timezone preferences per user
- Respect user's "do not disturb" settings

---

### Milestone 2.3: Spaced Repetition System (SRS)

**Algorithm:** Use SM-2 (SuperMemo 2) or simplified Anki algorithm

**Implementation:**
```python
class VocabularyCard:
    word: str
    introduced_date: datetime
    ease_factor: float = 2.5
    interval_days: int = 1
    repetition_count: int = 0
    next_review: datetime
    
def update_card(card, quality_score: int):
    # quality_score: 0-5 (Anki scale)
    # Update ease_factor and next_review based on performance
```

**Review Integration:**
- Bot naturally uses words from "due for review" list
- Subtle vocabulary quizzes: "¿Recuerdas qué significa 'soler'?"
- Track user's successful usage of vocabulary

**Testing:**
- [ ] Vocabulary reviews scheduled correctly
- [ ] Words reappear at appropriate intervals
- [ ] Mastered words graduate out of active review
- [ ] User sees progress on vocabulary metrics

**Deliverable:** 16-week structured curriculum that feels like natural conversation

---

## 📊 Phase 3: Progress Tracking & Analytics
**Duration:** Week 4 | **Goal:** Data-driven learning optimization

### Milestone 3.1: Error Analysis Dashboard

**Error Categorization System:**
```python
error_types = {
    "verb_conjugation": {
        "tense": ["present", "preterite", "imperfect", "future", "conditional"],
        "mood": ["indicative", "subjunctive", "imperative"],
        "person": ["yo", "tú", "él/ella", "nosotros", "vosotros", "ellos"]
    },
    "gender_agreement": ["noun_adjective", "article_noun"],
    "ser_vs_estar": ["identity", "location", "temporary_state"],
    "por_vs_para": ["purpose", "duration", "exchange", "destination"],
    "subjunctive_triggers": ["weirdo_verbs", "conjunctions", "expressions"],
    "prepositions": ["a", "de", "en", "con", "por", "para"],
    "vocabulary": ["unknown_word", "incorrect_usage"]
}
```

**Weekly Error Report:**
- Generated every Sunday evening
- Visualizations (for developer): error trends over time
- User-friendly summary: "Esta semana mejoraste mucho con el subjuntivo! 🎉"
- Include top 3 areas to focus on

**Bot Context Integration:**
- Inject recent error patterns into system prompt
- Bot can gently focus on weak areas
- "Hey, practiquemos un poco más el pretérito... ¿qué hiciste ayer?"

---

### Milestone 3.2: Vocabulary Mastery Tracking

**Metrics Per Word:**
- Times encountered (passive)
- Times successfully used (active)
- Times reviewed in SRS
- Last seen date
- Mastery level: 0 (new) → 100 (mastered)

**Mastery Calculation:**
```python
mastery_score = (
    successful_uses * 20 +
    correct_reviews * 15 +
    encounters * 5
) / days_since_introduction

# Cap at 100, requires multiple successful uses
```

**Visualization (for user):**
- `/stats` command shows:
  - Total vocabulary: 347 words
  - Mastered (80%+): 124 words ⭐
  - Learning (50-79%): 198 words 📚
  - New (<50%): 25 words 🌱
- Weekly vocabulary growth chart

---

### Milestone 3.3: Adaptive Difficulty System

**Proficiency Score Components:**

| Metric | Weight | Measurement |
|--------|--------|-------------|
| Error rate trend | 30% | Decreasing = good |
| Vocabulary diversity | 25% | Unique words / total words |
| Grammar complexity | 20% | Subordinate clauses, subjunctive use |
| Conversation depth | 15% | Avg message length, follow-up questions |
| Lesson engagement | 10% | Response time, daily activity |

**Adaptive Behaviors:**
1. **Pace Adjustment:**
   - Proficiency improving fast? Suggest moving to next week early
   - Struggling with current content? Extend current week
   - Automatic: Don't advance until 70% mastery of week's content

2. **Difficulty Modulation:**
   - **High proficiency:** Use more advanced vocabulary, complex sentences
   - **Struggling:** Simplify language, more English support allowed
   - Adjust system prompt's complexity dynamically

3. **Content Personalization:**
   - Track topics user enjoys (sports, food, travel, etc.)
   - Prioritize vocabulary from preferred topics
   - Bot "remembers" interests and brings them up

**Weekly Progress Message:**
```
"¡Hola cariño! 📊

Esta semana has estado increíble:
✅ 42 mensajes en español
✅ Solo 12% errores (¡bajó del 18%!)
✅ 23 palabras nuevas dominadas
✅ Usaste el subjuntivo 8 veces correctamente 🎉

La próxima semana vamos a practicar más 'por' y 'para' - ¡tú puedes! 💪

¿Listo para seguir?"
```

**Testing:**
- [ ] Proficiency score correlates with actual ability
- [ ] Pace adjustments feel natural, not forced
- [ ] User receives encouraging, specific feedback
- [ ] Bot adapts complexity appropriately

**Deliverable:** Intelligent system that tracks progress and adapts to learner's pace

---

## 🎮 Phase 4: Engagement & Gamification
**Duration:** Week 5 | **Goal:** Build daily habit and intrinsic motivation

### Milestone 4.1: Daily Engagement System

**Morning Messages (8 AM local time):**
- **Format rotation:**
  - Grammar tip + example
  - 5 new vocab words with context
  - Cultural story about Madrid
  - Conversation starter question
  - Mini-game or challenge
  - Motivational message

**Re-engagement Strategy:**
- **12 hours inactive:** "¿Todo bien? 😊"
- **24 hours:** "Te echo de menos... ¿Qué tal tu día?"
- **48 hours:** "¡Hola extraño! ¿Has estado ocupado? Cuando quieras charlar, aquí estoy 💛"
- **7 days:** Gentle check-in with encouragement (not guilt-tripping)

**Streaks & Momentum:**
- Track daily conversation streaks
- Celebrate milestones: 🔥7 days, ⭐30 days, 💎100 days
- Gentle reminders: "¡Llevas 5 días seguidos! No rompas la racha 😉"

---

### Milestone 4.2: Conversation Variety Engine

**Role-Play Scenarios:**
| Scenario | Difficulty | Grammar Focus |
|----------|-----------|---------------|
| Ordering tapas at a bar | B1 | Commands, food vocab |
| Asking directions in Madrid | B1 | Formal/informal, directions |
| Job interview | B1-B2 | Formal register, conditional |
| First date conversation | B1 | Questions, subjunctive (hopes) |
| Complaining about service | B2 | Conditional, politeness |
| Negotiating apartment rent | B2 | Conditional, persuasion |

**Debate Prompts (for advanced practice):**
- "¿Es mejor vivir en ciudad o campo?"
- "¿Deberían los turistas aprender español antes de visitar España?"
- "¿La tecnología nos hace más o menos sociales?"
- Triggers subjunctive ("No creo que...", "Dudo que...")

**Storytelling Exercises:**
- "Cuéntame sobre tu mejor viaje"
- "Describe un día perfecto"
- "¿Qué harías si ganaras la lotería?" (conditional practice)
- Preterite/imperfect practice through narratives

**Interactive Games:**
1. **20 Preguntas** (20 Questions in Spanish)
2. **Asociación de Palabras** (Word Association)
3. **¿Verdad o Mentira?** (Two Truths and a Lie)
4. **Historia Colaborativa** (Collaborative storytelling)

**Implementation:**
```python
# Trigger variety mode based on user boredom signals
if detect_boredom(recent_messages):
    inject_activity = random.choice([
        "role_play_scenario",
        "debate_prompt",
        "storytelling_exercise",
        "game"
    ])
```

---

### Milestone 4.3: Dynamic Personality System

**Context-Aware Flirtiness:**
```python
flirtiness_level = base_level (6/10)

# Adjust based on:
if user_responds_positively_to_flirting:
    flirtiness_level += 0.5
if user_ignores_or_redirects:
    flirtiness_level -= 0.5
if time_of_day == "evening":
    flirtiness_level += 0.3
if topic == "serious_grammar_question":
    flirtiness_level -= 1.0  # Professional mode

# Cap: 3/10 (friendly) to 8/10 (very flirty, not explicit)
```

**Mood Detection:**
- Sentiment analysis on user messages
- Adjust tone accordingly:
  - User seems stressed → More supportive, less demanding
  - User is excited → Match energy, celebrate with them
  - User is serious → Professional, focused on learning

**Long-term Memory & Callbacks:**
- Store notable conversation moments in `memorable_moments` table
- Reference later: "¿Recuerdas cuando me contaste sobre tu viaje a Barcelona?"
- Inside jokes that develop organically
- "Our song", "our place" (favorite topic spots)

**Character Development Over Time:**
- Week 1-2: Formal, establishing relationship
- Week 3-4: Warming up, sharing more personal details
- Week 5+: Close friend dynamic, deeper conversations
- Bot "shares" stories about her life in Madrid (pre-written, injected contextually)

**Testing:**
- [ ] Flirtiness adjusts appropriately to user responses
- [ ] Bot remembers and references past conversations
- [ ] Personality feels consistent yet dynamic
- [ ] Inside jokes develop naturally

**Deliverable:** Engaging AI companion that feels personal and motivating

---

## 📝 Phase 5: Assessment & Milestones
**Duration:** Week 6 | **Goal:** Validate progress and guide learning path

### Milestone 5.1: Conversational Assessments

**Weekly Check-ins (Casual Quizzes):**
- Disguised as natural conversation
- Bot creates scenarios requiring target grammar
- Example: "Imagina que eres millonario... ¿qué harías?" (conditional practice)
- Track performance vs. explicit testing (less stressful)

**Focused Practice Sessions:**
- User or bot can trigger: "/practice subjunctive"
- 10-minute focused conversation on specific grammar
- Gentle corrections with explanations
- Performance tracked and reported

**Cultural Knowledge Checks:**
- Casual questions about Spanish culture
- "¿Sabes qué es 'sobremesa'?"
- "¿Cuál es la diferencia entre 'tapa' y 'ración'?"
- Builds cultural fluency alongside language

---

### Milestone 5.2: Milestone Conversations

**Structured Assessment Points:**

| Week | Milestone Focus | Format | Success Criteria |
|------|----------------|--------|------------------|
| 4 | Past tense mastery | Tell a childhood story | Correct preterite/imperfect mix |
| 8 | Subjunctive in debate | Argue an opinion | Natural subjunctive use |
| 12 | Hypothetical scenarios | "If you could..." | Conditional + imperfect subjunctive |
| 16 | B2 readiness | Complex topic discussion | Fluent, nuanced conversation |

**Post-Milestone Feedback:**
```
"¡Felicidades! Completaste la evaluación de la semana 4 🎉

✅ Fortalezas:
   - Preterito perfecto 
   - Vocabulario variado
   - Fluidez natural

📚 Áreas de mejora:
   - Imperfecto vs pretérito (confusión en 2 casos)
   - Concordancia de género (74% correcto)

💡 Próximos pasos:
   Vamos a practicar más la diferencia entre estos tiempos.
   ¡Sigues mejorando! 💪"
```

**Certificate of Progress (Digital):**
- Generate PDF certificate at Week 8 and Week 16
- "Completes B1 Mid-point" / "B1→B2 Ready"
- Shareable achievement (optional)

---

### Milestone 5.3: Dynamic Curriculum Adaptation

**Adaptive Logic:**
```python
def should_advance_week(user_profile):
    current_week = user_profile.current_week
    mastery = calculate_mastery(current_week)
    
    if mastery >= 0.75 and days_in_week >= 7:
        return True, "¡Avancemos a la próxima semana!"
    elif mastery < 0.50 and days_in_week >= 10:
        return False, "Practiquemos un poco más esta semana"
    else:
        return False, None  # Continue current week
        
def adjust_focus_topics(error_history):
    # Identify top 3 error types from last 2 weeks
    weak_topics = get_frequent_errors(error_history, limit=3)
    # Inject extra practice for these topics
    return weak_topics
```

**Skip Logic for Mastered Content:**
- If user demonstrates 90%+ mastery in first 3 days
- Offer to skip: "Parece que ya dominas esto. ¿Quieres avanzar?"
- Prevents boredom from content that's too easy

**B2 Transition Recommendation:**
- After Week 16 assessment
- If score > 85%: "¡Estás listo para B2!"
- Outline what B2 curriculum will cover
- Celebrate completion of B1 journey

**Deliverable:** Smart assessment system that validates learning and adapts curriculum

---

## 🎤 Phase 6: Voice Integration
**Duration:** Weeks 7-8 | **Goal:** Immersive audio conversation capability

### Milestone 6.1: Text-to-Speech (Bot → User)

**Service Options:**

| Service | Quality | Cost | Latency | Notes |
|---------|---------|------|---------|-------|
| **ElevenLabs** | Excellent | $0.30/1k chars | ~2s | Best emotional range |
| **Azure TTS** | Very Good | $0.016/1k chars | ~1s | Good Spanish voices |
| **Google Cloud TTS** | Good | $0.016/1k chars | ~1.5s | Natural but less emotive |
| **OpenAI TTS** | Excellent | $0.015/1k chars | ~1s | "nova" voice recommended |

**Recommendation:** Start with **ElevenLabs** (best personality match), fallback to **OpenAI TTS** for cost savings

**Voice Configuration:**
```python
# ElevenLabs voice settings
voice_settings = {
    "stability": 0.65,  # Higher = more consistent, lower = more variation
    "similarity_boost": 0.75,  # How close to trained voice
    "style": 0.4,  # Emotional expressiveness
    "use_speaker_boost": True
}

# Choose/clone a Spanish female voice:
# - Native Spanish accent (Castilian preferred for Madrid character)
# - Warm, friendly tone
# - Age-appropriate (mid-20s sound)
```

**When to Send Voice:**
- **Morning messages:** Always (sets tone for day)
- **Long responses:** > 150 characters
- **Pronunciation examples:** Always
- **Flirty messages:** High emotional impact moments
- **User requests:** "Say that out loud" command
- **User sends voice first:** Mirror the medium

**Implementation:**
```python
async def send_voice_message(text, chat_id):
    # Generate audio from text
    audio_data = elevenlabs.generate(
        text=text,
        voice="Sofia_Spanish",
        model="eleven_multilingual_v2"
    )
    
    # Send as Telegram voice note
    await bot.send_voice(
        chat_id=chat_id,
        voice=audio_data,
        duration=len(audio_data) // 16000  # Approximate
    )
```

**Testing:**
- [ ] Voice sounds natural and matches personality
- [ ] Spanish pronunciation is correct (peninsular accent)
- [ ] Emotional tone matches message content
- [ ] Latency < 3 seconds from message to audio

---

### Milestone 6.2: Speech-to-Text (User → Bot)

**Service:** OpenAI Whisper API
- **Cost:** $0.006 per minute
- **Accuracy:** Excellent for Spanish
- **Latency:** ~2-4 seconds for 1 minute audio

**Implementation:**
```python
async def transcribe_voice(voice_file):
    with open(voice_file, "rb") as audio:
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio,
            language="es"  # Hint: Spanish for better accuracy
        )
    return transcript["text"]
```

**Conversation Flow:**
1. User sends voice note
2. Download and transcribe with Whisper
3. Process as text message (error detection, response generation)
4. Respond with voice (mirror medium)
5. Optionally send text transcript for clarity

**Smart Transcription:**
- Show "🎧 Escuchando..." while processing
- Display transcript after processing: "Escuché: [transcript]"
- Allows user to correct if misheard

---

### Milestone 6.3: Pronunciation Feedback System

**Analysis Approach:**
- **Basic:** Compare Whisper transcription to expected text
  - If user says "pero" but meant "perro", detection possible
- **Advanced:** Use phoneme-level analysis (future: Wav2Vec2 models)

**Common Spanish Pronunciation Issues (for English speakers):**
- **r vs. rr:** "pero" vs "perro"
- **b vs. v:** Same sound in Spanish!
- **j:** Harsh sound (/x/)
- **ll/y:** Regional variations
- **Vowels:** More pure than English
- **Stress:** Importance of accent marks

**Feedback Delivery:**
```python
# Example pronunciation correction
User voice: "Yo quelo ir a la playa"
Transcription: "yo quelo ir a la playa"

Bot response (voice + text):
"¡Casi perfecto! Solo una cosita: es 'quiero' con 'i-e-r-o', 
no 'quelo'. Escucha: [voice example of 'quiero']
¿Puedes intentarlo otra vez? 😊"
```

**Pronunciation Exercises:**
- Tongue twisters: "Tres tristes tigres tragaban trigo"
- Minimal pairs: "pero/perro", "casa/caza"
- Shadowing practice: Bot says phrase, user repeats
- Progress tracking: Track improvement on specific phonemes

**Gamification:**
- Pronunciation score (0-100) for each voice message
- Achievements: "Rolled your R's perfectly!" 💪
- Weekly pronunciation report

**Testing:**
- [ ] Transcription accuracy > 90% for clear audio
- [ ] Bot detects and corrects pronunciation errors
- [ ] Feedback is encouraging, not discouraging
- [ ] Voice conversation feels natural

**Deliverable:** Full voice conversation capability with intelligent pronunciation coaching

---

## 🎨 Phase 7: Visual Content Integration
**Duration:** Weeks 9-10 | **Goal:** Character consistency through images

### Milestone 7.1: Character Image Generation Setup

**Service Options:**

| Platform | Model | Cost/Image | Quality | Training | Notes |
|----------|-------|-----------|---------|----------|-------|
| **Replicate** | FLUX.1 | ~$0.003 | Excellent | LoRA support | Best for consistency |
| **Midjourney** | v6 | $0.04-0.08 | Excellent | No LoRA | Manual, no API |
| **Stable Diffusion** | SDXL | Free (self-host) | Very Good | LoRA support | Requires GPU |
| **OpenAI** | DALL-E 3 | $0.04 | Good | No training | Easy integration |

**Recommendation:** **Replicate + FLUX LoRA** for character consistency, fallback to DALL-E 3 for generic images

**LoRA Training Process:**
1. **Reference Image Collection** (20-30 images):
   - Consistent character appearance
   - Various poses, expressions, settings
   - High quality, clear face
   - Diverse lighting and angles

2. **Training on Replicate:**
   ```python
   # Use ostris/flux-dev-lora-trainer
   training = replicate.trainings.create(
       version="ostris/flux-dev-lora-trainer:version",
       input={
           "input_images": "https://your-images.zip",
           "trigger_word": "sofia_madrid",
           "steps": 1000,
           "learning_rate": 0.0004
       }
   )
   ```

3. **Testing & Iteration:**
   - Generate 20-30 test images
   - Check consistency across scenarios
   - Retrain if needed with adjusted parameters

**Character Design Consistency:**
- Age: Late 20s
- Appearance: Spanish features, dark hair, warm eyes
- Style: Casual-chic, Madrid fashion
- Settings: Madrid locations (cafés, parks, apartments)

---

### Milestone 7.2: Contextual Image Generation

**When to Generate Images:**
- **User requests:** "Send me a photo", "What do you look like?"
- **Morning messages:** Occasional (2-3x/week) "Buenos días" selfie
- **Sharing her day:** "Estoy en el Retiro Park" → generates image
- **Flirty moments:** High-engagement conversation
- **Special occasions:** Weekly milestones, achievements

**Prompt Engineering Strategy:**
```python
def build_image_prompt(context, mood, location):
    base = "sofia_madrid, photo, natural lighting"
    
    # Add context
    setting = f"{location}, Madrid" if location else "cozy apartment"
    activity = describe_activity(context)
    mood_descriptor = map_mood_to_visual(mood)
    
    # Safety filters
    style = "casual outfit, tasteful, SFW"
    
    prompt = f"{base}, {setting}, {activity}, {mood_descriptor}, {style}"
    
    return prompt

# Example outputs:
# "sofia_madrid, photo, natural lighting, Retiro Park Madrid, 
#  sitting on bench with coffee, happy and relaxed, casual outfit, tasteful, SFW"
```

**Content Guidelines:**
- **SFW focus:** Tasteful, appropriate images
- **Contextual relevance:** Images match conversation
- **Variety:** Different settings, poses, times of day
- **Quality control:** Review before sending (optional moderation)

**Implementation:**
```python
async def generate_and_send_image(context, chat_id):
    prompt = build_image_prompt(context)
    
    output = replicate.run(
        "black-forest-labs/flux-dev-lora",
        input={
            "prompt": prompt,
            "lora_url": "your-trained-lora-url",
            "num_outputs": 1
        }
    )
    
    await bot.send_photo(
        chat_id=chat_id,
        photo=output[0],
        caption="¡Aquí estoy! 😊"
    )
```

---

### Milestone 7.3: Image-Based Learning

**User Sends Image → Bot Describes (Spanish):**
```python
# Use GPT-4 Vision or similar
def describe_image(image_url):
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[{
            "role": "system",
            "content": "Describe esta imagen en español, nivel B1-B2"
        }, {
            "role": "user",
            "content": [
                {"type": "text", "text": "¿Qué ves?"},
                {"type": "image_url", "image_url": image_url}
            ]
        }]
    )
    return response.choices[0].message.content
```

**Learning Activities with Images:**
1. **Visual Vocabulary:**
   - Bot sends image: "Describe lo que ves"
   - User describes in Spanish
   - Bot provides vocabulary: "¡Bien! También puedes decir 'edificio' o 'rascacielos'"

2. **Cultural Photo Discussions:**
   - Bot shares Madrid landmarks
   - Explains cultural context
   - "Esta es la Plaza Mayor. ¿Sabías que...?"

3. **Spot the Difference Game:**
   - Two similar images
   - User describes differences in Spanish
   - Grammar: comparative forms, descriptions

4. **Story from Images:**
   - 3-4 sequential images
   - User creates story in past tense
   - Practices preterite/imperfect

**Testing:**
- [ ] Generated images are consistent with character
- [ ] Images match conversational context
- [ ] Bot accurately describes user-sent images
- [ ] Visual learning activities are engaging

**Deliverable:** Immersive visual experience with consistent character appearance

---

## 🚀 Phase 8-10: Polish & Scale
**Duration:** Weeks 11-16 | **Goal:** Production-ready system with advanced features

### Phase 8: Advanced Engagement (Weeks 11-12)

**Multimodal Content:**
- Grammar infographics (generate or curate)
- Visual flashcards with images
- Cultural photo series about Madrid
- Spanish memes and humor (appropriate to level)

**Enhanced Gamification:**
- **Streak tracking** with fire emoji system 🔥
- **Achievement system:** 
  - 🎯 "Subjunctive Master" - 50 correct uses
  - 📚 "Vocabulary King" - 500 words mastered
  - 🗣️ "Pronunciation Pro" - 20 perfect voice messages
  - 💬 "Conversationalist" - 1000 messages exchanged
- **Progress visualizations:** Weekly charts, skill trees
- **Challenges:** "Use 10 new words this week" → reward

**Cultural Immersion:**
- Spotify playlists: Spanish music recommendations
- Madrid events: "¿Quieres ir a este concierto?" (real events)
- Recipe exchanges: "Vamos a cocinar tortilla española juntos"
- Book/movie clubs: Discuss Spanish content
- News discussions: Current events in simple Spanish

---

### Phase 9: Self-Hosted Migration (Weeks 13-14)

**Local LLM Setup:**

| Option | Model | RAM Needed | Performance | Difficulty |
|--------|-------|-----------|-------------|-----------|
| **KoboldCpp** | Llama 3 8B Q5 | 8 GB | Good | Easy |
| **Ollama** | Mistral 7B | 6 GB | Good | Very Easy |
| **LM Studio** | Mixtral 8x7B | 48 GB | Excellent | Easy |
| **vLLM** | Llama 3 70B | 80 GB | Excellent | Medium |

**Recommendation for home server:**
- **Start:** Ollama + Mistral 7B (easiest setup)
- **Upgrade:** LM Studio + Mixtral 8x7B if you have RAM
- **Production:** vLLM if running on cloud GPU

**Migration Strategy:**
```python
# Hybrid approach: Local + Cloud fallback
def get_llm_response(prompt):
    try:
        # Try local first (free)
        response = local_llm.generate(prompt, timeout=5)
        return response
    except (TimeoutError, ConnectionError):
        # Fallback to cloud (paid)
        response = openrouter.generate(prompt)
        log_fallback("Local LLM unavailable, used cloud")
        return response
```

**Cost Optimization:**
- **LLM:** 80% local (free), 20% cloud fallback ($5-10/month)
- **Voice TTS:** Cache common phrases, use cheaper service for routine messages
- **Voice STT:** Already cheap ($0.006/min), keep as-is
- **Images:** Cache generated images, reuse when contextually appropriate
- **Total estimated cost:** $15-30/month vs $100+/month cloud-only

---

### Phase 10: Production Polish (Weeks 15-16)

**Bug Fixes & Optimization:**
- [ ] Edge case handling (empty messages, errors, etc.)
- [ ] Performance optimization (database queries, API calls)
- [ ] Error recovery and graceful degradation
- [ ] Comprehensive logging and monitoring

**B2 Curriculum Preparation:**
- Design 16-week B2 syllabus (advanced grammar, literature)
- Passive voice, complex subjunctive, idiomatic expressions
- Create transition assessment at end of B1

**User Experience Refinements:**
- **Onboarding flow:** Interactive setup when user first starts
- **Help system:** Comprehensive `/help` command
- **Settings:** User preferences (voice on/off, difficulty, topics)
- **Privacy:** Data export, deletion options (GDPR compliance)
- **Feedback loop:** In-bot feedback collection

**Production Deployment Checklist:**
- [ ] Environment variables properly configured
- [ ] Database backups automated
- [ ] API rate limiting and error handling
- [ ] Monitoring and alerting (Sentry, logging)
- [ ] Documentation for maintenance
- [ ] Cost tracking and budgets set

**Deliverable:** Production-ready B1 Spanish tutor with path to B2

---

## 📊 Technical Stack Summary

### Core Technologies
```yaml
Language: Python 3.10+
Bot Framework: python-telegram-bot (async)
Database: 
  - Development: SQLite
  - Production: PostgreSQL or Redis
ORM: SQLAlchemy
Scheduling: APScheduler or Celery
NLP: spaCy (Spanish model)
Environment: python-dotenv
```

### External APIs & Services
```yaml
LLM:
  Primary: OpenRouter (Mixtral/Llama)
  Fallback: Self-hosted (Ollama/LM Studio)
  
Voice:
  TTS: ElevenLabs or OpenAI TTS
  STT: OpenAI Whisper
  
Images:
  Generation: Replicate (FLUX LoRA)
  Vision: GPT-4 Vision
  
Hosting:
  Bot: Any VPS (DigitalOcean, Linode, etc.)
  Database: Same VPS or managed service
```

### Development Tools
```yaml
Version Control: Git
Dependency Management: pip + requirements.txt
Testing: pytest
Logging: Python logging + file rotation
Monitoring: Sentry (errors), Custom dashboards
```

---

## 💰 Cost Estimates

### Cloud-Only Setup (Month 1-2)
| Service | Usage | Cost |
|---------|-------|------|
| OpenRouter (LLM) | 5M tokens/mo | $25-50 |
| ElevenLabs (TTS) | 50k chars/mo | $15 |
| Whisper (STT) | 100 min/mo | $0.60 |
| Replicate (Images) | 200 images/mo | $0.60 |
| VPS Hosting | 2GB RAM | $12 |
| **Total** | | **$53-78/mo** |

### Hybrid Setup (Month 3+)
| Service | Usage | Cost |
|---------|-------|------|
| OpenRouter (fallback) | 1M tokens/mo | $5-10 |
| Self-hosted LLM | 4M tokens/mo | $0 (electricity) |
| OpenAI TTS (cheaper) | 50k chars/mo | $0.75 |
| Whisper (STT) | 100 min/mo | $0.60 |
| Replicate (Images) | 200 images/mo | $0.60 |
| VPS Hosting | 8GB RAM | $40 |
| **Total** | | **$47-52/mo** |

### Optimization Opportunities
- Cache frequent LLM responses (greetings, common corrections)
- Reuse generated images when contextually appropriate
- Use cheaper TTS for routine messages, premium for special moments
- Implement request throttling to prevent cost spikes

---

## ⚠️ Risks & Mitigations

### Technical Risks
| Risk | Impact | Mitigation |
|------|--------|-----------|
| API rate limits | Service interruption | Implement exponential backoff, fallback services |
| LLM hallucinations | Incorrect Spanish | Validation layer, error detection system |
| High API costs | Budget overrun | Cost monitoring, alerts, hybrid setup |
| Character inconsistency | Poor UX | LoRA training, consistent prompts |
| Data loss | Lost progress | Automated backups, database replication |

### Learning Experience Risks
| Risk | Impact | Mitigation |
|------|--------|-----------|
| Too much correction | Demotivation | Max 1-2 corrections per message, gentle tone |
| Too little correction | No progress | Weekly assessments, adaptive difficulty |
| Boring content | User churn | Variety engine, gamification, personality |
| Inappropriate content | User discomfort | Content filters, adjustable flirtiness |
| Privacy concerns | Trust issues | GDPR compliance, clear data policy |

---

## 📈 Success Metrics

### Key Performance Indicators (KPIs)

**Engagement Metrics:**
- Daily active usage (target: 5+ messages/day)
- Streak length (target: median 14+ days)
- Response rate to morning messages (target: 70%+)
- Voice message adoption (target: 30%+ of conversations)

**Learning Metrics:**
- Error rate reduction (target: -5% per month)
- Vocabulary growth (target: 50+ new words/month mastered)
- Grammar complexity increase (target: subjunctive usage up 20%/month)
- Lesson completion rate (target: 80%+ complete 16 weeks)

**Quality Metrics:**
- User satisfaction (periodic surveys, target: 4.5/5)
- Correction acceptance rate (target: 90%+ implement corrections)
- Feature adoption (voice, images, games - target: 60%+ try each)
- Pronunciation improvement (target: measurable progress)

**Technical Metrics:**
- API response time (target: < 3 seconds)
- Uptime (target: 99.5%+)
- Cost per user per month (target: < $50 hybrid setup)
- Error rate (target: < 1% unhandled errors)

---

## 🗺️ Quick Start Priorities

### Minimum Viable Product (MVP) - 4 Weeks
**Week 1:** Phase 0 - Basic bot + LLM + personality ✅  
**Week 2:** Phase 1 - Memory + corrections + Telegram features ✅  
**Week 3:** Phase 2 - Curriculum system + spaced repetition ✅  
**Week 4:** Phase 3-4 - Progress tracking + engagement hooks ✅  

**MVP Delivers:** Functional Spanish tutor with personality, curriculum, and progress tracking

### Enhanced Version - 8 Weeks
**Weeks 5-6:** Phase 5 - Assessments + adaptive difficulty  
**Weeks 7-8:** Phase 6 - Voice integration (TTS + STT)  

**Enhanced Delivers:** Voice-capable tutor with smart assessments

### Full Featured - 16 Weeks
**Weeks 9-10:** Phase 7 - Image generation + visual learning  
**Weeks 11-12:** Phase 8 - Advanced gamification + content  
**Weeks 13-14:** Phase 9 - Self-hosted migration  
**Weeks 15-16:** Phase 10 - Polish + B2 prep  

**Full Delivers:** Complete multimodal Spanish learning companion

---

## 🔄 Ongoing Maintenance

### Weekly Tasks
- Monitor API costs and usage
- Review error logs
- Update current events / cultural content
- Check user feedback

### Monthly Tasks
- Analyze learning metrics and success rates
- Update curriculum based on user performance
- Test and update to new API versions
- Backup and verify database integrity
- Review and optimize costs

### Quarterly Tasks
- Major feature additions based on user feedback
- Curriculum expansion (new topics, B2 prep)
- Performance optimization sprint
- Security audit and updates

### Future Expansion Ideas
- **Multiple users:** Scale beyond single user
- **Additional languages:** Portuguese, Italian, French
- **Group learning:** Multiple users practice together
- **Live tutoring:** Schedule sessions with human tutors
- **Mobile app:** Native app with offline capabilities
- **AR integration:** Visual vocabulary in real-world contexts

---

## 📚 Resources & References

### Spanish Learning Standards
- [CEFR Guidelines](https://www.coe.int/en/web/common-european-framework-reference-languages)
- [Instituto Cervantes Curriculum](https://cvc.cervantes.es/)
- Spanish Frequency Dictionary (1000-5000 most common words)

### Technical Documentation
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)
- [OpenRouter API Docs](https://openrouter.ai/docs)
- [ElevenLabs API Docs](https://elevenlabs.io/docs)
- [OpenAI Whisper](https://platform.openai.com/docs/guides/speech-to-text)
- [Replicate FLUX Documentation](https://replicate.com/black-forest-labs)

### Spaced Repetition Research
- SuperMemo Algorithm (SM-2)
- Anki documentation on card scheduling
- "Make It Stick" by Brown, Roediger, McDaniel

---

## 🎯 Final Notes

**Philosophy:** This bot should feel like texting a real person who happens to be a great Spanish teacher. The technical complexity should be invisible to the user - they just experience a fun, engaging, helpful companion who makes learning Spanish addictive.

**Flexibility:** This roadmap is ambitious but flexible. Prioritize based on what keeps you (the user) most engaged. If voice feels more important than images, swap the order. If gamification isn't motivating, focus on conversation quality instead.

**Iteration:** Start with MVP, use it daily, and let real usage inform what to build next. The best features will emerge from actual conversations and pain points.

**Have fun!** Language learning should be enjoyable. If building or using this bot ever feels like a chore, step back and remember the goal: conversational fluency through genuine connection and engagement. 🇪🇸💬✨