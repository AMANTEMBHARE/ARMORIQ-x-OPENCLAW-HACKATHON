"""
AirGuard AI — Telegram Bot Interface

Connects the existing AirGuardAgent pipeline to Telegram.
Every user message is passed through the full pipeline:
    User -> agent.process_command() -> Enforcer -> Policy -> Executor -> reply

Run from anywhere:
    python telegram_bot.py
    python airguard-ai/telegram_bot.py

Requirements:
    pip install python-telegram-bot
"""

import sys
import os

# Ensure the airguard-ai package directory is on the path regardless of
# which working directory the user launches from.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import logging
import json
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

import config
from agent import AirGuardAgent

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("airguard.telegram")

# ── Agent (single shared instance) ───────────────────────────────────────────
_agent = AirGuardAgent(
    data_dir=config.DATA_DIR,
    output_dir=config.OUTPUT_DIR,
    log_dir=config.LOG_DIR,
    policy_file=config.POLICY_FILE,
)


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_result(result: dict) -> str:
    """Convert an agent result dict into a readable Telegram message."""
    if not result.get("success"):
        msg = result.get("message", "Unknown error")
        # Blocked actions get a clear visual indicator
        if "BLOCKED" in msg or not result.get("success"):
            # Unknown intent — give a helpful nudge instead of a scary error
            if "unknown" in msg.lower() or "Unknown action" in msg:
                return (
                    "🤔 I didn't understand that command.\n\n"
                    "Try something like:\n"
                    "  • `Delhi pollution`\n"
                    "  • `Analyze AQI in Mumbai`\n"
                    "  • `Fetch live AQI for Bangalore`\n"
                    "  • `Compare Delhi and Mumbai`\n"
                    "  • `Generate report for Delhi`\n"
                    "  • `Send warning alert about pollution in Delhi`\n\n"
                    "Type /help for the full list."
                )
            return f"🚫 *Action Blocked*\n\n{msg}"
        return f"❌ *Error*\n\n{msg}"

    lines = [f"✅ *{result.get('message', 'Done')}*"]

    data = result.get("data") or {}

    # ── analyze_aqi / generate_report summary ────────────────────────────────
    summary = data.get("summary")
    if summary:
        lines.append("")
        lines.append("📊 *Summary*")
        lines.append(f"  Average AQI : `{summary.get('average_aqi', 'N/A')}`")
        lines.append(f"  Min / Max   : `{summary.get('min_aqi', 'N/A')} / {summary.get('max_aqi', 'N/A')}`")
        lines.append(f"  Trend       : `{summary.get('trend', 'N/A').upper()}`")

    advisory = data.get("health_advisory")
    if advisory:
        lines.append(f"\n🏥 *Health Advisory*\n  {advisory}")

    # ── fetch_live_aqi ────────────────────────────────────────────────────────
    if "aqi" in data and "health_label" in data:
        lines.append(f"\n🌍 *{data.get('location')}*")
        lines.append(f"  AQI    : `{data['aqi']}`")
        lines.append(f"  Status : {data['health_label']}")
        pollutants = data.get("pollutants", {})
        if pollutants:
            lines.append("  Pollutants:")
            for p, v in pollutants.items():
                lines.append(f"    {p}: `{v}` µg/m³")

    # ── compare_cities ────────────────────────────────────────────────────────
    ranking = data.get("ranking")
    if ranking:
        lines.append("\n🏙️ *City Ranking (worst → best)*")
        for r in ranking:
            lines.append(
                f"  {r['rank']}. {r['city']} - AQI `{r['aqi']}` ({r['health_label']})"
            )
        insight = data.get("insight")
        if insight:
            lines.append(f"\n💡 {insight}")

    # ── send_alert ────────────────────────────────────────────────────────────
    if data.get("alert_sent"):
        lines.append(f"\n🚨 Alert ID : `{data.get('alert_id')}`")
        lines.append(f"  Severity  : `{data.get('severity', '').upper()}`")
        lines.append(f"  Area      : {data.get('area', 'N/A')}")

    # ── pollution_trend ───────────────────────────────────────────────────────
    if "direction" in data and "stats" in data:
        s = data["stats"]
        lines.append(f"\n📈 *Trend for {data.get('location')}*")
        lines.append(f"  Direction : `{data.get('trend_label', data['direction'])}`")
        lines.append(f"  Average   : `{s.get('average_aqi')}` AQI")
        lines.append(f"  Peak      : `{s.get('peak_aqi')}` at {s.get('peak_time')}")
        lines.append(f"  Lowest    : `{s.get('lowest_aqi')}` at {s.get('lowest_time')}")
        lines.append(f"  Change    : `{s.get('change_pct')}%`")
        if data.get("summary"):
            lines.append(f"\n_{data['summary']}_")

    # ── health_advisory ───────────────────────────────────────────────────────
    if "by_group" in data:
        lines.append(f"\n🏥 *Health Advisory — {data.get('location')}*")
        lines.append(f"  AQI       : `{data.get('current_aqi')}` ({data.get('health_label')})")
        lines.append(f"  Color     : {data.get('color_code')}")
        lines.append(f"  Mask      : {'Yes — recommended' if data.get('mask_needed') else 'Not required'}")
        lines.append(f"  Outdoors  : {'OK' if data.get('outdoor_ok') else 'Avoid'}")
        lines.append(f"\n{data.get('general', '')}")
        lines.append("\n*By group:*")
        for group, advice in data.get("by_group", {}).items():
            lines.append(f"  *{group}*: {advice}")

    # ── report file ───────────────────────────────────────────────────────────
    files = result.get("files_created", [])
    if files:
        lines.append(f"\n📄 Report saved: `{files[0]}`")

    exec_time = result.get("execution_time")
    if exec_time is not None:
        lines.append(f"\n⏱ `{exec_time:.2f}s`")

    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed = _agent.get_allowed_actions()
    text = (
        "👋 *Welcome to AirGuard AI*\n\n"
        "I monitor air pollution and enforce strict safety policies.\n\n"
        "*Allowed commands (examples):*\n"
        "  • Analyze AQI in Delhi\n"
        "  • Generate pollution report for Mumbai\n"
        "  • Fetch live AQI for Bangalore\n"
        "  • Compare Delhi and Mumbai\n"
        "  • Send warning alert about high pollution in Delhi\n\n"
        "*Blocked actions:* factory shutdown, issuing fines\n\n"
        f"_Allowed actions: {', '.join(allowed)}_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = _agent.get_system_status()
    text = (
        "📊 *System Status*\n\n"
        f"  Total actions   : `{status['total_actions']}`\n"
        f"  ✅ Successful   : `{status['successful_actions']}`\n"
        f"  🚫 Blocked      : `{status['blocked_actions']}`\n"
        f"  ❌ Errors       : `{status['errors']}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🛡️ *AirGuard AI — Help*\n\n"
        "*Commands:*\n"
        "  /start  — Welcome message & allowed actions\n"
        "  /status — System statistics\n"
        "  /help   — This message\n\n"
        "*Just send any natural language command, e.g.:*\n"
        "  `Analyze AQI in Delhi`\n"
        "  `Fetch live AQI for Mumbai`\n"
        "  `Compare Delhi and Kolkata`\n"
        "  `Generate report for Chennai`\n"
        "  `Send critical alert about hazardous air in Delhi`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text.strip()
    if not user_text:
        return

    logger.info("User %s: %s", update.effective_user.id, user_text)

    # Typing indicator — best-effort, ignore if network is flaky
    try:
        await update.message.chat.send_action("typing")
    except Exception:
        pass

    try:
        # ── Short-circuit for greetings (LLM may classify these) ─────────────
        # Parse intent first to check before running the full pipeline
        from intent import IntentParser as _IP
        _quick = _IP().parse_intent(user_text)
        if _quick.action == "greeting":
            await update.message.reply_text(
                "👋 Hello! I'm AirGuard AI.\n\n"
                "Ask me about air quality, pollution levels, health advice, or city comparisons.\n"
                "Type /help to see what I can do.",
                parse_mode="Markdown",
            )
            return

        result = _agent.process_command(user_text)
        reply = _format_result(result)
    except Exception as exc:
        logger.exception("Unhandled error processing command")
        reply = f"⚠️ Unexpected error: {exc}"

    await update.message.reply_text(reply, parse_mode="Markdown")


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors and notify the user if possible."""
    from telegram.error import NetworkError, TimedOut
    err = context.error

    # Network/timeout errors are transient — log at WARNING, not ERROR
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning("Transient network error (will retry): %s", err)
        return

    logger.error("Unhandled exception", exc_info=err)

    # Try to tell the user something went wrong
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text("⚠️ Something went wrong. Please try again.")
        except Exception:
            pass


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Export it as an environment variable before running."
        )

    # Configure HTTPXRequest with generous timeouts to avoid ConnectError
    # on Windows where TLS handshakes can be slower
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(handle_error)

    logger.info("AirGuard AI Telegram bot starting (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
