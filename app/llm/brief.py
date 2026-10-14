"""LLM meeting/call prep brief (assistant, ux-direction). Local Ollama, degrade-if-down.

One-click "brief me on this person before I talk to them": a short summary + a few talking
points, composed from what we already know (role, org, history, latest signal). Generative
for the USER's own prep — not facts about the person, not in the scoring path.
"""

from __future__ import annotations

from app.llm.client import LlmUnavailable, OllamaClient


def build_brief_prompt(profile: dict) -> str:
    c = profile.get("contact", {})
    name = f"{c.get('first_name') or ''} {c.get('last_name') or ''}".strip() or "this contact"
    facts = []
    if c.get("job_title") or c.get("company"):
        facts.append(f"Role: {c.get('job_title') or '?'} at {c.get('company') or '?'}.")
    if c.get("org_tier"):
        facts.append(f"Company prominence: {c['org_tier']}.")
    if profile.get("last_contact"):
        facts.append(f"Last contacted: {profile['last_contact']}.")
    interactions = profile.get("interactions") or []
    if interactions:
        recent = "; ".join(
            f"{i.get('occurred_on')} {i.get('kind')}: {i.get('note') or ''}".strip()
            for i in interactions[:3]
        )
        facts.append(f"Recent touchpoints: {recent}.")
    signals = profile.get("signals") or []
    if signals:
        facts.append(f"Recent news: {signals[0].get('summary')}.")
    context = " ".join(facts) or "Little is known beyond their name."

    return (
        f"Prepare me to talk to {name}. Using ONLY the context below, write a very short brief: "
        "2-3 sentences on who they are and where we stand, then 3 concise talking points as a "
        "bullet list. Do not invent facts not in the context. Context: " + context
    )


def prep_brief(profile: dict, client: OllamaClient | None = None) -> str | None:
    """Return a prep brief, or None if the local LLM is disabled/unreachable."""
    client = client or OllamaClient()
    if not client.available():
        return None
    try:
        return client.generate(build_brief_prompt(profile)).strip()
    except LlmUnavailable:
        return None
