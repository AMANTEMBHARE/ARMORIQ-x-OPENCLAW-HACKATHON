"""
Configuration layer for AirGuard AI.
Loads environment variables from .env (if present), then falls back to
whatever is already set in the shell environment.
Paths are resolved relative to this file so the bot works regardless
of which directory you launch it from.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file (airguard-ai/.env)
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── aqicn.org free API token ──────────────────────────────────────────────────
# Get one at https://aqicn.org/data-platform/token/
AQICN_TOKEN: str = os.environ.get("AQICN_TOKEN", "")

# ── OpenAI API key (unused — replaced by Groq) ───────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# ── Groq API key ──────────────────────────────────────────────────────────────
# Get a free key at https://console.groq.com/keys
# Leave blank to fall back to regex-based intent parsing
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")

# ── Directories ───────────────────────────────────────────────────────────────
_BASE = str(_HERE)
DATA_DIR:    str = os.environ.get("AIRGUARD_DATA_DIR",    os.path.join(_BASE, "data"))
OUTPUT_DIR:  str = os.environ.get("AIRGUARD_OUTPUT_DIR",  os.path.join(_BASE, "output"))
LOG_DIR:     str = os.environ.get("AIRGUARD_LOG_DIR",     os.path.join(_BASE, "logs"))
POLICY_FILE: str = os.environ.get("AIRGUARD_POLICY_FILE", os.path.join(_BASE, "policy.json"))
