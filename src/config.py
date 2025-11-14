"""Configuration management for the Spanish Tutor Bot."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = CONFIG_DIR / "prompts"

# Create necessary directories
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
PROMPTS_DIR.mkdir(exist_ok=True)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env file")

# Authorized user IDs (comma-separated list in env, or default to single user)
AUTHORIZED_USER_IDS = os.getenv("AUTHORIZED_USER_IDS", "6089646018")
AUTHORIZED_USER_IDS_SET = set(id.strip() for id in AUTHORIZED_USER_IDS.split(",") if id.strip())

# OpenAI LLM configuration (preferred)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# OpenRouter fallback configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3-8b-instruct")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Active LLM settings resolved from available credentials
LLM_API_KEY = OPENAI_API_KEY or OPENROUTER_API_KEY
LLM_MODEL = OPENAI_MODEL if OPENAI_API_KEY else OPENROUTER_MODEL
LLM_BASE_URL = OPENAI_BASE_URL if OPENAI_API_KEY else OPENROUTER_BASE_URL

# Application Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# LLM Settings
LLM_MAX_RETRIES = 3
LLM_TIMEOUT = 30  # seconds
LLM_MAX_TOKENS = 500
LLM_TEMPERATURE = 0.8  # Higher for more personality

# Character Profile
CHARACTER_PROFILE_PATH = CONFIG_DIR / "character_profile.yaml"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system_prompt.md"
GREETING_PROMPT_PATH = PROMPTS_DIR / "greeting_message.md"
HELP_PROMPT_PATH = PROMPTS_DIR / "help_message.md"

# Conversation history storage
CONVERSATION_DB_PATH = DATA_DIR / "conversations.sqlite"

# Scheduling configuration
DEFAULT_USER_TIMEZONE = os.getenv("DEFAULT_USER_TIMEZONE", "Europe/Madrid")
