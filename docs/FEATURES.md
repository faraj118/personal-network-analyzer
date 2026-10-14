# PNCA Feature Backlog

The product vision beyond the core pipeline: turn PNCA from a **database you look at** into an
**assistant that tells you who to reach out to, why, and helps you act** — local, private,
free. Captured from the UX/product review (2026-09-23). Status: ✅ done · 🚧 in progress · ☐ planned.

Guardrails still apply (SPEC.md §15): local-first, single-user, no cloud/paid services, free
enrichment only, local LLM (Ollama) only.

## 0. Foundations (built)
- ✅ Ingest (CSV) · classify · score · dedup · discovery · enrichment backbone · profile · planning
- ✅ CRM: add / edit / delete / correct, seniority, website, tags, notes; persists across rebuilds; re-scores on edit
- ✅ Pages: Contacts, Contact/Profile, Network, Review, Calendar

## 0b. Pages / Information architecture (UX review 2026-09-24)
Current pages: Dashboard, Contact/Profile, Network, Review, Calendar. Missing pages, ranked:
- 🚧 **Persistent top nav** across all pages (Home · People · Companies · Network · Pipeline · Signals · Calendar · Settings) — biggest discoverability win.
- 🚧 **🏢 Companies** — network grouped by org: prominence tier, #contacts, seniority gaps, "pursuing".
- ☐ **🎯 Opportunities / Pipeline** — Kanban of pursuits (Idea→Talking→Proposal→Won/Lost) linked to contacts.
- ☐ **⚙️ Settings** — edit rubric weights/targets, toggle LLM/enrichment, run scans (no YAML).
- ☐ **📰 Signals feed** — chronological "what's new in my network" stream (daily habit).
- ☐ **🏷️ Segments / saved views** — saved smart filters ("Fintech in GCC", "investors").
- ☐ **📊 Insights** — coverage vs targets, growth over time, outreach→outcome.
- ☐ **🗺️ Network graph (visual)** — interactive node-graph (vendored JS, local) vs tables.
- ☐ **🧹 Data health** — duplicates, missing fields, stale info, backup/export.

## 1. Clarity & UX (plain language, assistant-first)
- 🚧 Plain-language relabel of jargon (value→"the info", importance→"Priority", bridges→"key connectors", "sourced claim"→"info found online")
- 🚧 **"Today" home** — action list (overdue follow-ups, top opportunities to reach out to) instead of a raw table
- 🚧 Search + industry/seniority filters on the dashboard
- ☐ "Why?" breakdown on the Priority score (e.g. "C-Level +40, Tech +30")
- ☐ Contact page reorder: Who they are → How I know them → What's new → What to do next
- ☐ Progressive disclosure — hide graph metrics behind a plain "why?"

## 2. Turn insight into action (uses the local LLM)
- ☐ **Draft outreach for me** — one-click warm message using role + last interaction + latest signal
- ☐ **Call/meeting prep brief** — one-click "brief me on this person"
- ☐ **Ask my network in plain English** — NL question → deterministic filter over local data
- ☐ Paste conversation/email → auto-notes + action items + suggested follow-up date

## 3. Opportunity / pipeline
- ☐ Lightweight **opportunities** (pilot/partnership/job) linked to contacts, with stage + next action
- ☐ Goal-driven targeting ("break into GCC manufacturing" → which contacts/bridges get me there)
- ☐ Signal → suggested action (job change → "congratulate / re-engage")

## 4. Relationship intelligence
- ☐ **Interaction timeline + last-contacted** (dated notes; foundation for the below)
- ☐ Cadence & strength (desired touch frequency per tier) + **dormant-VIP nudges**
- ☐ "Who can introduce me to X?" — warm intro paths via the graph
- ☐ Give/get log (favors & intros); name your circles (communities)

## 5. Capture & portability (low friction)
- ☐ **vCard (.vcf) import/export** (phone contacts in/out)
- ☐ Paste email-signature / LinkedIn URL → contact (LLM parse)
- ☐ **Business-card photo (JPG/PNG) → OCR → structured contact** (Phase 1b). Note
  (2026-09-23): card input is an **image**, not CSV — upload jpg/png → OpenCV preprocess →
  OCR (en+ar) → LLM extract (already built) → review-gated → contact. High priority.
- ☐ Bulk actions (tag / set opportunity on many)
- ☐ CSV/JSON export

## 6. Trust & safety (our edge)
- ☐ Encryption at rest (SQLCipher) + one-click backup/restore
- ☐ Data health (duplicates, missing fields, stale info)
- ☐ Undo / restore deleted contacts

## 7. Remaining core build
- ☐ Card OCR (Phase 1b) · Robots-permitted signal feed

## Out of scope (would require moving the SPEC.md §15 boundary)
Sending email/SMS, live calendar sync, paid enrichment, mobile app. Local equivalents (in-app
digest, `.ics` export, free enrichment) stay in scope.
