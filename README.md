# 🇪🇸 Spanish Study Telegram Bot

An AI-powered Spanish tutor bot that helps learners progress from B1 to B2 through natural conversation with Sofía, a friendly language teacher from Madrid.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- OpenAI API Key (from [platform.openai.com](https://platform.openai.com))  
  _(Optional fallback: OpenRouter API Key if you prefer OpenRouter)_

### Installation

1. **Clone and navigate to the project:**
   ```bash
   git clone https://github.com/ACNoonan/spanish-study-telegram-bot.git
   cd spanish-study-telegram-bot
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` and add your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   OPENAI_API_KEY=your_openai_key_here
   # Optional fallback if you want to use OpenRouter instead
   # OPENROUTER_API_KEY=your_openrouter_key_here
   ```

5. **Run the bot:**
   ```bash
   python main.py
   ```

## ✨ Features

### Current Implementation
- ✅ **Conversational Bot**: Natural conversation in Spanish
- ✅ **Character Personality**: Meet Sofía, una profe de Madrid
- ✅ **LLM Integration**: OpenAI (default) with retry logic and OpenRouter fallback
- ✅ **Basic Commands**: `/start`, `/help`
- ✅ **Typing Indicators**: Natural conversation feel
- ✅ **Conversation Memory**: SQLite-backed recent-message context
- ✅ **Gentle Corrections**: Automatic error detection with subtle prompts

### Coming Soon (See [ROADMAP.md](docs/ROADMAP.md))
- ✍️ Intelligent error correction
- 📚 Structured B1-B2 curriculum
- 🎯 Progress tracking & analytics
- 🎤 Voice message support
- 🎨 Character images
- 🎮 Gamification & achievements

## 📁 Project Structure

```
spanish-study-telegram-bot/
├── main.py                      # Entry point
├── src/
│   ├── bot.py                   # Main bot logic
│   ├── config.py                # Configuration management
│   ├── llm_client.py           # OpenRouter LLM integration
│   └── personality.py          # Character personality system
├── config/
│   └── character_profile.yaml  # Sofía's personality definition
├── docs/
│   └── ROADMAP.md             # Full development roadmap
├── requirements.txt           # Python dependencies
└── .env                       # Environment variables (not in git)
```

## 🎭 Meet Sofía

Sofía is your Spanish tutor - a 28-year-old language teacher from Madrid who loves tapas, flamenco, and sharing Spanish culture. She's:
- 💛 Warm and encouraging
- 🎓 Patient and professional
- 😊 Slightly flirty but always appropriate
- 🇪🇸 Passionate about Spanish language and Madrid culture

## 🛠️ Development

### Current Phase: Phase 0 (Foundation)
This is the MVP with basic conversational capabilities.

### Running in Development Mode
```bash
# Set environment to development in .env
ENVIRONMENT=development
LOG_LEVEL=DEBUG

python main.py
```

### Testing the Bot
1. Start the bot with `python main.py`
2. Open Telegram and search for your bot
3. Send `/start` to begin
4. Try conversing in Spanish!

Example conversation:
```
User: Hola! ¿Cómo estás?
Sofía: ¡Hola, cariño! Estoy muy bien, gracias 😊 Acabo de volver de pasear 
       por el Retiro Park - ¡qué día tan bonito hace hoy en Madrid! 
       ¿Y tú? ¿Qué tal tu día?
```

## 📊 Tech Stack

- **Bot Framework**: python-telegram-bot (async)
- **LLM**: OpenAI GPT family by default (OpenRouter optional)
- **Config**: python-dotenv, PyYAML
- **Database**: SQLite (coming in Phase 1)

## 🔐 Security Notes

- Never commit `.env` file
- Keep API keys secure
- Conversation history lives in `data/conversations.sqlite`

## 📈 Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the complete 16-week development plan.

**Current Status**: 🔄 Phase 1 In Progress (Week 2)  
**Focus**: Conversation Memory Enhancements & Corrections

## 💰 Cost Estimates (Phase 0)

- **LLM (Meta Llama 3 8B)**: ~$0.10 per 1M tokens
- **Expected monthly cost**: $5-10 for moderate usage
- **Hosting**: Local development (free)

## 🤝 Contributing

This is a personal learning project, but feedback and suggestions are welcome!

## 📝 License

This project is for personal use and learning purposes.

## 🎯 Goals

The ultimate goal is to create an engaging AI companion that makes learning Spanish feel like chatting with a friend, helping you progress from B1 to B2 level naturally through conversation, corrections, and cultural immersion.

---

**Current Version**: 0.1.0 (Phase 0 - Foundation)  
**Status**: 🟢 MVP Working  
**Last Updated**: October 2025
