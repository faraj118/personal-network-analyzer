# Enrichment & Profiles — design & risk mitigations

Per `SPEC.md §8, §18`. Free public sources only, provenance-first, review-gated. This is the
"listen to the internet" capability, scoped to the owner's own network.

## Tiers (shipped in order)

| Tier | Module | What | Risk | Phase |
|---|---|---|---|---|
| 1 | `enrichment/signals.py` | Opportunity signals (job change, funding, promotion) on **known** contacts from free news/RSS | Low | 5 |
| 2 | `enrichment/sources/*` | Fill missing attributes (title, company, location, public profile URL) from free public pages | Medium | 6 |
| 3 | `enrichment/profile.py` | Assemble a per-contact profile from **accepted** claims + signals | Higher | 7 |

## Non-negotiable rules (enforced in code, not just here)

1. **Free sources only** — no paid data brokers, no cloud LLM. (`enrichment.free_sources_only`)
2. **Provenance mandatory** — every `enrichment_record` has `source_url` + `method` +
   `confidence` + `fetched_at`. Web methods without a `source_url` are rejected at the model
   layer (`EnrichmentClaim` validator).
3. **Review-gated** — claims land as `pending`; they never write `contacts` directly.
   `enrichment.auto_accept_confidence` (default 0.95) may auto-accept high-confidence claims,
   still fully sourced. Everything else waits for a human decision (`POST /review/{id}`).
4. **Supersede, don't overwrite** — conflicting claims are kept; old ones become `superseded`.
5. **No evasion** (applies to all HTTP) — respect robots.txt, real User-Agent,
   rate-limit with human-scale jitter, **stop on 403/429/CAPTCHA**. Never circumvent a block.
6. **Data minimization** — only professionally-relevant fields.
7. **No special-category data** — health, religion, ethnicity, politics, sexuality are excluded
   (`enrichment.exclude_special_category`).
8. **Own-network scope** — enrich people already in your contacts; no mass-targeting of strangers.
9. **Erasure** — deleting a contact cascades to its `enrichment_records` and `signals`.

## Why this is defensible

Owner is a single user in **Libya**, enriching **their own professional network** for
relationship management and opportunity timing — a legitimate personal-CRM use. Some contacts
may still be EU/GCC data subjects; provenance + erasure + minimization + no-special-category
keep the posture clean. Not legal advice — if scope ever widens beyond the owner's own network,
revisit. LLM output is treated as a *claim with a source*, never as truth (`SPEC.md §16`).

## Data flow

```
known contact -> Enricher (one free source) -> EnrichmentClaim(+provenance)
  -> enrichment_records(status=pending)
  -> review (accept/reject)  OR  auto-accept (>= threshold)
  -> accepted claims feed contacts (field_provenance) + profile assembly
Scoring never sees any of this until a claim is an accepted contacts field (deterministic).
```
