"""LLM outreach drafting (assistant, ux-direction). Local Ollama, degrade-if-down.

Composes a short, ready-to-edit outreach message from what we already know (role, company,
last interaction, latest signal). Unlike fact-extraction (§15: extract-from-text only), this
is legitimately generative — it drafts the USER's own message for them to review/send. It is
NOT in the scoring/data path and writes no facts about the person.
"""

from __future__ import annotations

from app.llm.client import LlmUnavailable, OllamaClient

_INTENTS = {
    "reconnect": "reconnect after a while",
    "congratulate": "congratulate them on recent news",
    "intro": "open a conversation / introduce yourself",
    "follow_up": "follow up on a prior conversation",
}


def build_prompt(profile: dict, intent: str = "reconnect") -> str:
    c = profile.get("contact", {})
    name = f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip() or "them"
    role = c.get("job_title") or ""
    company = c.get("company") or ""
    last = profile.get("last_contact")
    signals = profile.get("signals") or []
    latest_signal = signals[0]["summary"] if signals else ""
    goal = _INTENTS.get(intent, _INTENTS["reconnect"])

    ctx = []
    if role or company:
        ctx.append(f"They are {role}{' at ' if role and company else ''}{company}.")
    if last:
        ctx.append(f"Last contacted on {last}.")
    if latest_signal:
        ctx.append(f"Recent news about them: {latest_signal}.")
    context = " ".join(ctx) or "No extra context."

    return (
        f"Write a short, warm, professional outreach message from me to {name}. "
        f"Purpose: {goal}. Context: {context} "
        "Keep it 3-4 sentences, natural, specific, and ready to send — no placeholders, "
        "no subject line, no sign-off name. Output only the message text."
    )


def draft_outreach(
    profile: dict, intent: str = "reconnect", client: OllamaClient | None = None
) -> str | None:
    """Return a drafted message, or None if the local LLM is disabled/unreachable."""
    client = client or OllamaClient()
    if not client.available():
        return None
    try:
        return client.generate(build_prompt(profile, intent)).strip()
    except LlmUnavailable:
        return None
