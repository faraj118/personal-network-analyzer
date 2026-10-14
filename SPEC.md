# SPEC.md — Personal Network & Contact Analyzer (PNCA): engineering specification

Authoritative design spec for this repository. Read fully before changing code.
This is a **single-user, local** tool. It has two value pillars:

1. **Type-B discovery** — computing latent structure in the network you already own
   (connectors, clusters, bridges). Pure graph math; needs no LLM and no internet.
2. **Enrichment & profiling** — building richer personal/professional profiles of your
   contacts by (a) a **local LLM** turning messy text into structured facts, and
   (b) **free public web sources** ("listening to the internet") for attributes and
   opportunity signals.

> **Design history:** the original spec was "no-LLM, Type-B only, no enrichment." It was
> deliberately amended to adopt a **local Ollama LLM** and **review-gated enrichment from free
> sources**, with the risk mitigations in §15/§18 as hard rules. Determinism is preserved where
> it matters (scoring, §4).

---

## 0. Settled decisions

| # | Decision | Resolution |
|---|---|---|
| 1 | Enrichment vs. discovery | **Both.** Type-B discovery (§8) is the analytical core; enrichment (§18) enriches node attributes and surfaces opportunity signals. Enrichment is **provenance-tracked and review-gated**, never silent. |
| 2 | Hardware | **CPU-only laptop.** LLM is a **small quantized model, selectively invoked** (not on the bulk CSV path). See §17 for the measured model choice. Speed budget is real — design around it. |
| 3 | OCR engine | PaddleOCR primary, EasyOCR fallback, Tesseract last. Fixed pretrained models, CPU-runnable. |
| 4 | Scoring | **Deterministic** weighted rubric in `config/rubric.yaml`. **No model assigns scores.** LLM/enrichment output is never in the scoring path — it only produces *reviewed facts* that land in `contacts`, which scoring then reads deterministically. |
| 5 | Dedup | Auto-merge on exact email/phone; fuzzy matches → review queue. |
| 6 | LinkedIn data | **Official LinkedIn data export (Connections.csv) only.** No browser automation or scraping of LinkedIn (§9, §15). |
| 7 | Local LLM | **Ollama, local-only, bounded (§17).** Extraction/classification/enrichment *suggestions* only; **constrained to extract-from-provided-text** (no free-form fact invention); cached; off the scoring path. Disabled-degradable: the app runs if Ollama is down. |
| 8 | Enrichment sourcing | **Free public sources only — no paid data brokers, no cloud LLM APIs.** Respect robots/ToS intent, rate-limit, human-scale, **no evasion** (§15/§18). Blocked = stop. |
| 9 | Enrichment scope | **Profile-building is in scope** for the user's own network, single-user. Every enriched fact carries source URL + method + confidence + timestamp and is erasable (§18). No special-category data (§18). |

---

## 1. What this is

Local pipeline that ingests (a) LinkedIn/Facebook exports, (b) business-card images, and
(c) manual entry; normalizes and deduplicates contacts; classifies
them; scores them deterministically; runs **graph analytics** to surface hidden structure;
and **enriches** contacts from a local LLM + free public web sources to build fuller
profiles and flag opportunities.

**Constraint:** runs on your machine. **No paid APIs, no cloud LLM.** Network activity is:
(i) OCR/NLP/LLM models pulled once, and (ii) **enrichment fetches to free public sources**, rate-limited and
robots-respecting (§18).

**Non-goals:** multi-user/auth, mobile app, real-time sync, **paid enrichment / cloud LLM**,
evasion/anti-bot tooling, mass-targeting or scraping people outside your own network. Do not
build these.

---

## 2. Tech stack (authoritative)

| Layer | Choice | Notes |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn | Orchestration. Dev/runtime via Docker (host is 3.14, no pip). |
| CSV/JSON | pandas | Structured already — just map + clean |
| Image preprocessing | OpenCV | Crop, deskew, contrast, denoise |
| OCR | PaddleOCR → EasyOCR → Tesseract cascade | `en` + `ar` passes |
| Deterministic extraction | `re` (regex), `phonenumbers`, `email-validator` | Email/phone/URL — high reliability, always tried first |
| Name/company/title | **spaCy** (`en_core_web_lg`) NER + title gazetteer, **+ local LLM fallback** | LLM used for Arabic / low-confidence (§16, §17) |
| Local LLM | **Ollama** (small quantized model, §17) | Extraction/enrichment suggestions; extract-from-text only; cached; off scoring path |
| Classification | rule dictionaries; **optional LLM suggestion**; sklearn later | Rules first; LLM suggestion is review-gated |
| Enrichment | httpx + selectolax/BeautifulSoup + feedparser over **free public sources** | Robots-respecting, rate-limited, no evasion (§18) |
| Dedup / entity res. | **rapidfuzz** + `recordlinkage` | |
| Discovery | **NetworkX** | Type-B engine (no LLM, no internet) |
| DB | SQLite (WAL) | Postgres only past ~100k rows |
| Config | YAML | rubric, gazetteers, target lists, llm + enrichment settings |
| Frontend | Jinja2 + htmx (or small React SPA) | Local-only, bind 127.0.0.1 |

> **LLM is local-only (Ollama) and bounded.** No LangChain, no cloud LLM, no paid APIs. The
> deterministic regex+NER+rules stack always runs first; the LLM is a *fallback/assist* whose
> output is constrained, cached, provenance-tagged, and kept off the scoring path.

---

## 3. Directory layout

```
pnca/
  app/
    main.py
    config.py             # loads config/app.yaml (single source of truth; no hardcoding)
    api/                  # ingest, contacts, review, score, graph, discovery, import,
                          #   enrich, signals
    pipeline/
      ingest_csv.py       # pandas -> source_records
      preprocess.py       # OpenCV
      ocr.py              # PaddleOCR/EasyOCR/Tesseract cascade
      extract.py          # regex + phonenumbers + spaCy NER + gazetteer + LLM fallback
      classify.py         # rule dictionaries (+ optional LLM suggestion)
      score.py            # deterministic rubric (pure fn) — never sees the LLM
      dedup.py            # rapidfuzz entity resolution
    llm/
      client.py           # Ollama client wrapper (timeouts, retries, cache, degrade-if-down)
      extractor.py        # LLM-backed Extractor impl (extract-from-text only)
      prompts/            # versioned, constrained prompt templates
    enrichment/
      base.py             # Enricher protocol + provenance/confidence contract
      fetch.py            # robots-respecting, rate-limited HTTP/RSS fetch (no evasion)
      sources/            # per-source adapters (free public sources only)
      signals.py          # Tier-1 opportunity-signal detection over known contacts
      profile.py          # Tier-3 profile assembly from enrichment_records
    discovery/
      graph.py            # build NetworkX graph from contacts
      metrics.py          # centrality, communities, bridges, gaps
    models/               # Pydantic + SQLAlchemy
    db.py                 # only module with DB side-effects
  config/
    app.yaml              # server, db, paths, llm, enrichment
    rubric.yaml
    gazetteers/           # titles, seniority, industry keyword lists
  db/migrations/          # *.sql applied idempotently
  data/
    uploads/  pnca.db     # gitignored
  tests/golden/           # labeled cards + expected extraction
  Dockerfile  docker-compose.yml   # python:3.14-slim app + ollama service
  SPEC.md
```

---

## 4. Data model (SQLite)

`source_records` (immutable, provenance) → `contacts` (canonical, rebuildable). Enrichment
adds two immutable, provenance-heavy tables that **never write to `contacts` directly** —
promotion to `contacts` is review-gated (§18).

```sql
CREATE TABLE source_records (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,           -- linkedin_export | facebook | business_card
  origin_file TEXT,
  raw_text TEXT,                  -- OCR blob / CSV row (JSON) / captured fields (JSON)
  image_path TEXT,
  extracted_json TEXT,
  ocr_confidence REAL,            -- cards only
  ingested_at TEXT NOT NULL,
  content_hash TEXT NOT NULL      -- idempotency
);

CREATE TABLE contacts (
  id TEXT PRIMARY KEY,
  first_name TEXT, last_name TEXT, job_title TEXT, company TEXT,
  email TEXT, phone TEXT, location TEXT,
  industry TEXT, seniority TEXT, opportunity TEXT,
  importance INTEGER,             -- 0..100 deterministic
  sources TEXT,                   -- JSON array of source_record ids
  needs_review INTEGER DEFAULT 0,
  field_provenance TEXT,          -- JSON: which source set each field
  created_at TEXT, updated_at TEXT
);
CREATE UNIQUE INDEX idx_contacts_email ON contacts(email) WHERE email IS NOT NULL;

-- One row per enriched fact/claim about a contact. Immutable, fully sourced.
CREATE TABLE enrichment_records (
  id TEXT PRIMARY KEY,
  contact_id TEXT NOT NULL,       -- FK -> contacts.id
  field TEXT NOT NULL,            -- e.g. job_title | company | location | bio | profile_url
  value TEXT NOT NULL,
  source_url TEXT,                -- exact page the claim came from (mandatory for web)
  method TEXT NOT NULL,           -- rss | web_public | llm_extract
  model TEXT,                     -- LLM model+version if method involved the LLM
  confidence REAL NOT NULL,       -- 0..1
  fetched_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,     -- idempotency (contact_id+field+value+source_url)
  status TEXT NOT NULL DEFAULT 'pending',  -- pending | accepted | rejected | superseded
  reviewed_at TEXT
);
CREATE UNIQUE INDEX idx_enrich_hash ON enrichment_records(content_hash);
CREATE INDEX idx_enrich_contact ON enrichment_records(contact_id);

-- Opportunity signals (Tier-1): events about known contacts (job change, funding, move).
CREATE TABLE signals (
  id TEXT PRIMARY KEY,
  contact_id TEXT NOT NULL,       -- FK -> contacts.id
  kind TEXT NOT NULL,             -- job_change | funding | promotion | company_news | mention
  summary TEXT NOT NULL,
  source_url TEXT NOT NULL,
  detected_at TEXT NOT NULL,
  confidence REAL NOT NULL,
  content_hash TEXT NOT NULL,     -- idempotency
  acknowledged INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX idx_signals_hash ON signals(content_hash);
```

Field provenance is mandatory so merge conflicts are explainable. **No enriched value enters
`contacts` without provenance and (by default) review.**

---

## 5. Input reality (build to this)

- **LinkedIn export**: First/Last, Company, Position, Connected-On; **email usually blank**.
- **Facebook export**: minimal professional value; ingest but expect low yield.
- **Cards**: mixed Arabic/English, logos, QR, double-sided. Below-threshold → review queue.
- **Enrichment**: free public web is **noisy and incomplete**. Expect partial hits, conflicting
  claims, and stale data. Treat every fetched fact as a *claim with a source*, not truth.

---

## 6. Extraction & classification

**CSV path:** pandas maps columns → schema. No model, no LLM. Graph-ready immediately.

**Card path:** OCR blob → `extract.py`, deterministic-first:
- email → regex + `email-validator`; phone → `phonenumbers` (E.164); URL → regex
- person / org → spaCy NER (`PERSON`, `ORG`); title → gazetteer
- **LLM fallback (§17):** only when deterministic extraction is empty/low-confidence *or*
  the text is Arabic. The LLM is prompted to **extract fields that appear in the text**, and
  to return `null` for anything not present. It never invents. Output confidence is recorded.

Output is a typed `ExtractionResult` with per-field `confidence`. Validate types; route
low-confidence to review.

**Classification (`classify.py`):** industry/seniority/opportunity via keyword dictionaries
(closed enums in `rubric.yaml`). LLM may *suggest* a class for ambiguous cases; suggestions
are review-gated and never auto-applied to the scoring inputs. Unknown → `Unknown`.

**Scoring (`score.py`, pure):** `importance = min(100, Σ matched weights)`. Same input →
same score. **The scorer never calls the LLM or enrichment**; it reads confirmed `contacts`
fields only.

**Thresholds:** `ocr_confidence < 0.75`, low field confidence, or merge conflict → `needs_review = 1`.

---

## 7. Deduplication (`dedup.py`)

1. Exact normalized **email** → auto-merge.
2. Exact E.164 **phone** → auto-merge.
3. Fuzzy (`rapidfuzz`): last name exact AND (company token-set > 0.85 OR first name > 0.9) → **review**.
4. Else → new contact.

Merge: prefer non-null; on conflict keep both in `field_provenance` + set `needs_review`.
`contacts` is always rebuildable from `source_records` (+ accepted `enrichment_records`).

---

## 8. Type-B discovery engine (`discovery/`)

Build a NetworkX graph: nodes = contacts; edges = a **real** shared tie — same company or same
location (weighted by specificity). **Seniority/title tier is NOT an edge** (measured on real
data it produced 74k noise edges vs 1.1k company edges — a hairball that swamps real structure);
it stays a node attribute for gaps/scoring. Compute: **centrality** (hubs), **community detection**
(clusters), **bridge nodes** (high betweenness — flagship), **gap analysis**, **warm leads**.
100% local, no LLM, no internet. Note (§16 #4): exports carry no location, so export-only data
gives company clusters with no cross-company links — **bridges need location/enriched ties**.

---

## 9. LinkedIn data (official export only)

LinkedIn data enters PNCA **only** through the user's own official data export
(Settings → Data privacy → Get a copy of your data → Connections). PNCA does **not** automate a
browser against LinkedIn, log in on the user's behalf, or scrape profiles. Do not add this.

---

## 10. API routes

```
POST /ingest              files[] -> queue
GET  /jobs/{id}
GET  /contacts            q, industry, seniority, min_score, needs_review
GET  /contacts/{id}
PATCH /contacts/{id}      corrections (clears needs_review)
GET  /opportunities       top-N by importance
GET  /review/queue        cards + fuzzy-merge candidates + pending enrichment_records
GET  /review/{id}         side-by-side (source vs proposed)
POST /review/{id}         accept | reject a pending enrichment claim
GET  /graph               nodes/edges for viz
GET  /discovery           centrality, communities, bridges, gaps
POST /enrich/{contact_id} start ONE enrichment pass for a contact (free sources, §18)
GET  /signals             opportunity signals over known contacts (Tier-1)
POST /export              csv|json
```

---

## 11. Idempotency
`content_hash` per item on `source_records`, `enrichment_records`, and `signals`; skip if
seen. Classification, scoring, dedup, graph build, and profile assembly are re-runnable with
no duplication.

## 12. Security & privacy
DB under `data/`, gitignored, `600`; consider SQLCipher. Server bound to `127.0.0.1` only.
Pin versions; no telemetry. Enrichment stores **only professionally-relevant** fields with
provenance; supports **erasure** (delete a contact ⇒ cascade its enrichment/signals). No
special-category personal data (§18).

## 13. Testing
`tests/golden/`: ~15 labeled cards (incl. Arabic + messy) → field-level accuracy — the real
number for deterministic vs LLM extraction. Unit tests: all four dedup tiers, the pure scorer,
graph metrics on a known graph, the LLM client's degrade-if-down path, and enrichment
provenance/idempotency (every enrichment_record has a source_url + confidence + hash).

## 14. Conventions
Type-hinted, Pydantic at boundaries, `ruff`+`black`. Pipeline/LLM/enrichment stages are pure
`input -> typed object`; DB side-effects isolated in `db.py`. Fail loud; never coerce bad
data into `contacts`. LLM/enrichment output is **suggestion → review → accept**, never a
silent write.

## 15. Hard boundaries (do not cross)
- **LLM is local (Ollama) only.** No cloud LLM, no LangChain, no paid model APIs.
- **LLM extracts from provided text only** — never generate/guess facts about a person that
  are not present in the source it was given. No free-form biography invention.
- **LLM is never in the scoring path.** Scores stay deterministic (§4).
- **Enrichment uses free public sources only.** No paid data brokers.
- **No anti-bot evasion of any kind** (§9, §18): no proxy/IP rotation, CAPTCHA-solving,
  UA/fingerprint spoofing, headless evasion. Respect robots/ToS intent. Blocked = **stop**.
- **Own-network scope only.** No mass-targeting or profiling of people outside the user's
  contacts. No special-category data (health, religion, ethnicity, politics, sexuality).
- **No multi-user/auth scope.** Single local user.

## 16. Known risks (surface, don't hide)
1. **Arabic extraction** — spaCy Arabic NER is weak; the LLM fallback (§17) should help, but
   verify on the golden set. Regex still handles email/phone regardless.
2. **LLM hallucination** — mitigated by extract-from-text-only prompts, confidence scoring,
   review-gating, and provenance. Still: treat LLM output as a claim, never truth.
3. **Enrichment noise/staleness** — free web data conflicts and goes stale; `enrichment_records`
   keeps every claim with `source_url`+`fetched_at`+`confidence`, and supersedes rather than
   overwrites. Review-gate before it touches `contacts`.
4. **Legal/privacy** — single-user, own network. Contacts may be
   EU/GCC (or other) data subjects; provenance + erasure + data-minimization + no-special-category keep
   this defensible. Not legal advice.
5. **CPU/LLM latency** — small model + selective invocation only; never on the bulk CSV path.
6. **Classification brittleness** — rules need tuning; LLM suggestion helps but is review-gated.
7. **Discovery quality depends on edge density** — more contacts help more than richer scraping.

## 17. Local LLM (`app/llm/`)
- **Runtime:** Ollama as a Docker service (`ollama/ollama`), reached over the compose network.
  The app degrades gracefully if Ollama is unreachable (deterministic path still works).
- **Model:** chosen to fit this machine (CPU-only, ~4 GB free RAM, low disk). Default set in
  `config/app.yaml` (`llm.model`); see `docs/LLM.md` for the measured benchmark and rationale.
- **Contract:** `llm/client.py` wraps Ollama with timeouts, small-batch limits, and a
  content-hash cache (same input ⇒ same cached output, so re-runs are reproducible). Prompts
  are versioned in `llm/prompts/` and constrained to *extract-from-provided-text*.
- **Config:** `llm.enabled` (bool), `llm.model`, `llm.base_url`, `llm.timeout_s`,
  `llm.max_input_chars`, `llm.invoke_on` (e.g. `[arabic, low_confidence]`).

## 18. Enrichment engine (`app/enrichment/`) — tiered, free, provenance-first
All enrichment writes to `enrichment_records`/`signals`, never `contacts` directly. Promotion
to `contacts` is review-gated by default (`enrichment.auto_accept_confidence` may auto-accept
above a high threshold, still with provenance).

- **Tier 1 — Signal monitoring (lowest risk, ship first):** watch free public news/RSS/company
  pages for events about **contacts you already have** (job change, funding, promotion). Writes
  `signals`. This is the highest-value, lowest-risk "listen to the internet" capability.
- **Tier 2 — Passive enrichment:** fill missing attributes (title, company, location, public
  profile URL) on existing contacts from free public pages, each as an `enrichment_record`.
- **Tier 3 — Contact profile:** assemble a fuller profile per contact from
  accepted enrichment_records + signals (`profile.py`). Built **only** from provenance-tracked,
  free-source, review-gated claims — no invented content.

**Fetch discipline (`fetch.py`) — applies to all web access:**
- Respect `robots.txt` and ToS intent; identify a real User-Agent (no spoofing).
- Rate-limit + randomized human-scale delays; never parallel-hammer a host.
- **Stop on block** (403/429/CAPTCHA) — never circumvent.
- Timeouts + caching; one pass per manual/scheduled trigger; persist partial progress.
- Free sources only; no login-walled scraping of any kind.

**Mitigations recap (enforced in code, not just docs):** provenance mandatory (`source_url`,
`method`, `confidence`, `fetched_at`); LLM extract-from-text-only; review-gated promotion;
supersede-don't-overwrite; erasure cascade; data minimization; no special-category data;
own-network scope only.
