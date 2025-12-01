# 🇪🇸 Spanish Study Telegram Bot

An AI-powered Spanish tutor bot for progressing from B1 to B2 through conversation with Sofía, a friendly teacher from Madrid.

> **Note:** This is an educational/hobby project, open-sourced for learning. Contributions welcome!

## Quick Start

```bash
git clone https://github.com/ACNoonan/spanish-study-telegram-bot.git
cd spanish-study-telegram-bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your keys
python main.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | From [@BotFather](https://t.me/botfather) |
| `OPENAI_API_KEY` | ✅ | For LLM, voice transcription (Whisper), and TTS |
| `AUTHORIZED_USER_IDS` | | Comma-separated Telegram user IDs (restricts access) |
| `OPENROUTER_API_KEY` | | Fallback LLM provider |
| `OPENAI_MODEL` | | Default: `gpt-4o-mini` |
| `DEFAULT_USER_TIMEZONE` | | Default: `Europe/Madrid` |

## Features

- **Conversational Spanish practice** with character personality (Sofía)
- **Voice messages** - send voice, receive voice (Whisper STT + OpenAI TTS)
- **16-week B1→B2 curriculum** with structured grammar/vocabulary
- **Spaced repetition** (SM-2 algorithm) for vocabulary retention
- **Intelligent corrections** with escalation on repeated errors
- **Scheduled engagement** - morning pings, inactivity nudges
- **Weather-aware mood** - integrates Madrid weather for natural conversation

## Project Structure

```
├── main.py              # Entry point
├── src/
│   ├── bot.py           # Main bot logic
│   ├── llm_client.py    # OpenAI/OpenRouter integration
│   ├── voice_handler.py # Whisper STT + TTS
│   ├── curriculum.py    # 16-week lesson system
│   └── vocabulary.py    # Spaced repetition
├── config/
│   ├── character_profile.yaml
│   ├── curriculum.yaml
│   └── prompts/         # System prompts, templates
└── data/                # SQLite conversation store
```

## Contributing

PRs and issues welcome. This started as a personal learning project - feel free to fork and adapt for your own language learning goals.

## License

MIT - see [LICENSE](LICENSE)
