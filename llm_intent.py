"""
LLM-based Intent Classifier for AirGuard AI.

Uses Groq (llama-3.3-70b-versatile) to classify free-form user input into
one of the system's supported intents. Falls back gracefully to regex when
the API key is not set or the call fails.

Usage:
    from llm_intent import classify_intent
    action, confidence = classify_intent("Why is pollution high in Delhi?")
    # -> ("analyze_aqi", 0.95)

Get a free Groq API key at: https://console.groq.com/keys
"""

import json
import logging
from typing import Tuple

import config

logger = logging.getLogger("airguard.llm_intent")

# ── Model ─────────────────────────────────────────────────────────────────────
_GROQ_MODEL = "llama-3.3-70b-versatile"   # fast, free-tier friendly

# ── Prompt ────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are an AI assistant for an air pollution monitoring system called AirGuard.
Your task is to classify the user's input into one of the following intents:

analyze_aqi      -> Questions about pollution, AQI, air quality, city pollution status, reasons/causes
give_advice      -> Questions about precautions, safety tips, what user should do
shutdown_factory -> Commands or suggestions to stop pollution sources like factories
greeting         -> Hello, hi, greetings
unknown          -> Anything unclear, random, or unrelated

Rules:
- Understand natural language, not just keywords
- "Why", "Reason", "Cause" should map to analyze_aqi
- Be concise and deterministic
- Return ONLY valid JSON in this format: {"intent": "intent_name", "confidence": 0.0-1.0}"""

_USER_PROMPT_TEMPLATE = 'User Input: "{user_input}"'

# ── LLM intent -> system action mapping ──────────────────────────────────────
LLM_TO_ACTION: dict = {
    "analyze_aqi":      "analyze_aqi",
    "give_advice":      "health_advisory",   # routes to health_advisory tool
    "shutdown_factory": "shutdown_factory",  # blocked by policy — intentional
    "greeting":         "greeting",          # handled in bot layer, not executor
    "unknown":          "unknown",
}


def classify_intent(user_input: str) -> Tuple[str, float]:
    """
    Classify user input using Groq LLM.

    Returns (action_name, confidence).
    Falls back to ("unknown", 0.0) on any error so the regex layer takes over.

    Args:
        user_input: Raw text from the user.

    Returns:
        Tuple[str, float]: (action, confidence)
    """
    api_key = config.GROQ_API_KEY
    if not api_key:
        logger.debug("GROQ_API_KEY not set — skipping LLM classification")
        return ("unknown", 0.0)

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model=_GROQ_MODEL,
            temperature=0,      # deterministic output
            max_tokens=64,      # only need a small JSON blob
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": _USER_PROMPT_TEMPLATE.format(user_input=user_input)},
            ],
        )

        raw = response.choices[0].message.content.strip()
        logger.debug("Groq raw response: %s", raw)

        # Strip markdown code fences if the model wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        parsed = json.loads(raw)
        llm_intent: str = parsed.get("intent", "unknown").strip().lower()
        confidence: float = float(parsed.get("confidence", 0.0))

        # Clamp to valid range
        confidence = max(0.0, min(1.0, confidence))

        # Low-confidence → fall through to regex
        if confidence < 0.5:
            logger.debug("Groq confidence %.2f below threshold — treating as unknown", confidence)
            return ("unknown", confidence)

        action = LLM_TO_ACTION.get(llm_intent, "unknown")
        logger.info("Groq classified %r -> %s (%.2f)", user_input, action, confidence)
        return (action, confidence)

    except json.JSONDecodeError as exc:
        logger.warning("Groq returned invalid JSON: %s", exc)
        return ("unknown", 0.0)

    except Exception as exc:
        logger.warning("Groq classification failed: %s", exc)
        return ("unknown", 0.0)
