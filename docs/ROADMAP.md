# PNCA Roadmap — Phased, Sequenced, Non-Overlapping

Each phase is a shippable slice with its own acceptance criteria, ordered so no phase depends
on a later one. The system stays **runnable and usable at every phase** (owner uses it while
we build). This is the contract that keeps growth controlled, not random.

> Direction (2026-09-21): added a **local Ollama LLM** and **tiered enrichment** (incl. active
> profiles from free sources). See `SPEC.md §7, §17, §18`.
>
> Direction (2026-09-23): product reframed from "database you view" to an **assistant that
> tells you who to reach out to and helps you act** — plain language, a "Today" home, and
> relationship/opportunity features. Full backlog: **[docs/FEATURES.md](FEATURES.md)**.
>
> **Status:** Phases 0–5 + 7 shipped (ingest, LLM extraction, classify/score/dedup, discovery,
> enrichment backbone + first source, profile) plus CRM (add/edit/delete) and planning
> (follow-ups + .ics). Remaining core: card OCR (1b), robots-permitted feed.
> Next focus: the UX/assistant features in FEATURES.md.

| Phase | Name | Delivers | Depends on | Deps |
|------:|------|----------|-----------|------|
| **0** | Scaffold | Dir tree, config loader, SQLite schema, API boot, CI, Docker (+Ollama service), seams | — | core+dev |
| **1** | Ingest & extract | CSV/JSON ingest, card OCR cascade, **deterministic** extraction → `source_records` | 0 | ocr, nlp |
| **2** | LLM integration | Ollama client (degrade-if-down, cache), LLM extractor fallback for Arabic/low-conf | 1 | (ollama) |
| **3** | Classify, score, dedup | Rule classification, deterministic scorer, 4-tier dedup, review queue → `contacts` | 1–2 | dedup |
| **4** | Type-B discovery | NetworkX graph, centrality/communities/bridges/gaps, `/graph` + `/discovery` | 3 | (core) |
| **5** | Enrichment T1 — signals | Robots-respecting fetch, free news/RSS signal detection over known contacts | 3 | enrich |
| **6** | Enrichment T2 — passive | Fill missing attributes from free public pages → `enrichment_records` (review-gated) | 5 | enrich |
| **7** | Enrichment T3 — profile | Assemble per-contact profiles from accepted claims + signals (no invention) | 6 | enrich |
| **8** | UI | Jinja2 + htmx local UI over the API, bound 127.0.0.1 | 3–7 | (core) |

## Definition of Done (every phase)

- Typed at boundaries (Pydantic); `ruff` + `black` clean; tests green in CI.
- No hardcoded config; new settings go in `config/app.yaml` / `rubric.yaml`.
- Docs updated in the **same** change: this file's status + `SPEC.md` if a decision shifts.
- Fail loud; never coerce bad data into `contacts` (`SPEC.md §14`).
- LLM/enrichment output is **suggestion → review → accept**, never a silent write; every
  enriched fact carries `source_url` + `method` + `confidence` + `fetched_at`.
- App still boots and serves existing routes (no phase breaks the running system).

## Phase 0 — acceptance (current)

- [x] `config/app.yaml` sole source of host/port; app binds 127.0.0.1:8199.
- [x] SQLite schema applies idempotently (`source_records`, `contacts`; + enrichment/signals).
- [x] `GET /health` returns the configured bind; feature routes return `501`.
- [x] Smoke tests cover config, schema, health.
- [x] CI runs lint + format-check + tests (core+dev only); green on GitHub.
- [x] Docker dev/runtime verified; **Ollama service** added + model chosen/benchmarked (`docs/LLM.md`).
- [x] LLM + enrichment **seams** (interfaces, config, schema) in place; impls land per phase.
