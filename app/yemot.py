"""Helpers for the Yemot HaMashiach (ימות המשיח) API protocol.

Yemot calls our endpoint with the call parameters as the query string. We
answer with a single line of text in Yemot's response DSL. The two pieces we
use here:

* ``read``  - speak a prompt and collect input. We use speech recognition so
  the caller can simply say what business they need. The recognized text comes
  back on the next request under the variable name we chose.
* ``id_list_message`` - speak a final text message; we then hang up.

NOTE: Yemot's ``read`` parameter order differs slightly between system
versions / extension settings. ``SPEECH_READ_TEMPLATE`` is intentionally a
single place to adjust to match your Yemot extension docs.
"""

# {prompt} = TTS text, {var} = variable name the recognized speech is returned under.
SPEECH_READ_TEMPLATE = "read=t-{prompt}={var},,voice,,,,,,,,,he-IL"

# Variable name that will carry the recognized speech back to us.
INTENT_VAR = "intent"

_PROMPT = "שלום, איזה עסק או שירות אתם מחפשים? דברו אחרי הצליל."


def _sanitize(text: str) -> str:
    """Strip characters that would break the Yemot response line."""
    if not text:
        return ""
    for ch in ("&", "=", ",", "\n", "\r", "\t"):
        text = text.replace(ch, " ")
    return text.strip()


def ask_for_intent() -> str:
    """Response that asks the caller (by voice) what they are looking for."""
    return SPEECH_READ_TEMPLATE.format(prompt=_sanitize(_PROMPT), var=INTENT_VAR)


def say_and_hangup(message: str) -> str:
    """Response that reads ``message`` to the caller and ends the call."""
    return f"id_list_message=t-{_sanitize(message)}&hangup=yes"


def extract_intent(params: dict) -> str:
    """Pull the recognized speech / typed intent out of Yemot's params."""
    return (params.get(INTENT_VAR) or "").strip()


def call_id(params: dict) -> str:
    """Stable per-call id, used to key the agent conversation session."""
    return (params.get("ApiCallId") or params.get("ApiPhone") or "anon").strip()
