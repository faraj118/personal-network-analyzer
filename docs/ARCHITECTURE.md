# PNCA Architecture (as built)

Mirrors `SPEC.md §2–§8`. This file tracks what actually exists in code; update it in the
same change that alters structure.

## Module layout

```mermaid
flowchart TB
  subgraph Web["app/web.py · app/templates/ · app/api/"]
    UI["Pages: Home, Contacts, Companies, Network,<br/>Pipeline, Review, Calendar, Tasks, Insights,<br/>Data health, Settings, Ask"]
    API["JSON API routers"]
  end
  subgraph Core["Pure stages: input → typed object, no DB access"]
    PIPE["app/pipeline/<br/>ingest_csv · ingest_card · preprocess · ocr<br/>extract · classify · score · dedup · build_contacts"]
    DISC["app/discovery/<br/>graph · metrics · service"]
    ENR["app/enrichment/<br/>fetch · sources/ · signals · dossier"]
    LLM["app/llm/<br/>client · extractor · prompts"]
  end
  DB["app/db.py<br/>SQLite connection + migrations<br/>(only DB side effects)"]
  CFG["app/config.py<br/>config/app.yaml · rubric.yaml · gazetteers/"]
  Web --> Core
  Web --> DB
  Core --> CFG
  ENR -. "HTTP, opt-in,<br/>robots-respecting" .-> NET(("Public web"))
  LLM -. "local only" .-> OLL(("Ollama"))
```

## Data flow

```mermaid
flowchart LR
  IN["CSV export · card image · manual"] --> SR[("source_records<br/>immutable")]
  SR == "rebuild (idempotent)" ==> C[("contacts<br/>canonical")]
  OV[("contact_overlay<br/>your edits")] --> C
  ER[("enrichment_records<br/>accepted claims")] --> C
  C --> SC["score"] & GR["graph metrics"] & PL["tasks · interactions · pipeline"]
```

`contacts` can always be rebuilt from `source_records`, plus your manual edits
(`contact_overlay`) and accepted enrichment claims. Ingest is idempotent through
`content_hash`.

## Deduplication rules

Implemented in `app/pipeline/dedup.py` as a pure decision function. Tiers are checked in
order; the first match wins.

```mermaid
flowchart TD
  N["New candidate"] --> E{"Same normalized<br/>email?"}
  E -- "yes" --> M1["Auto-merge"]
  E -- "no" --> P{"Same phone<br/>E.164 digits?"}
  P -- "yes" --> M2["Auto-merge"]
  P -- "no" --> F{"Last name equal AND<br/>company token-set > 85<br/>OR first name > 90?"}
  F -- "yes" --> R["Review queue<br/>never auto-merged"]
  F -- "no" --> NEW["New contact"]
```

On a merge conflict, both values are kept in `field_provenance` and the contact is flagged
`needs_review`.

## Data model

```mermaid
erDiagram
  SOURCE_RECORDS {
    text id PK
    text source "linkedin_export, business_card, ..."
    text raw_text
    real ocr_confidence
    text content_hash "idempotency"
  }
  CONTACTS {
    text id PK
    text first_name
    text last_name
    text job_title
    text company
    text industry
    text seniority
    int importance "0-100, deterministic"
    text field_provenance "JSON"
    int needs_review
  }
  ENRICHMENT_RECORDS {
    text id PK
    text contact_id FK
    text field
    text value
    text source_url
    text method
    real confidence
    text status "pending, accepted, rejected, superseded"
  }
  SIGNALS {
    text id PK
    text contact_id FK
    text kind "job_change, funding, ..."
    text source_url
    real confidence
    int acknowledged
  }
  CONTACT_OVERLAY {
    text contact_key PK
  }
  INTERACTIONS {
    text id PK
    text contact_id FK
    text occurred_on
  }
  TASKS {
    text id PK
    text contact_id FK "optional"
    text completed_at
  }
  COMPANY_INTEL {
    text company_key PK
  }
  SAVED_VIEWS {
    text id PK
  }
  SOURCE_RECORDS }o--o{ CONTACTS : "builds"
  CONTACTS ||--o{ ENRICHMENT_RECORDS : "claims about"
  CONTACTS ||--o{ SIGNALS : "events about"
  CONTACTS ||--o| CONTACT_OVERLAY : "manual edits"
  CONTACTS ||--o{ INTERACTIONS : "timeline"
  CONTACTS ||--o{ TASKS : "follow-ups"
```

Full column lists are in `db/migrations/*.sql`, applied idempotently on start-up. Deleting a
contact cascades to its enrichment records, signals and other personal data (erasure).

## Layering and boundaries

- **Config** (`app/config.py`): loads `config/app.yaml` once, validated by Pydantic. The
  only place host, port and asset paths are defined.
- **DB** (`app/db.py`): the only module with SQLite side effects. Schema in
  `db/migrations/*.sql`.
- **Pipeline** (`app/pipeline/`): pure `input -> typed object` stages, no DB access.
- **Discovery** (`app/discovery/`): pure graph build and metrics over contact dicts.
- **API** (`app/api/`): thin routers, one module per route group.
- **Models** (`app/models/`): Pydantic boundary schemas and closed enums.

## Runtime and deployment

- **Docker** (`Dockerfile`, `docker-compose.yml`) is the supported runtime:
  `python:3.14-slim`, running as non-root UID 1000 so files on the mounted `./data` volume
  are owned by your user.
- Localhost-only (§12) is enforced by the compose mapping `127.0.0.1:8199:8199`. The
  container process listens on `0.0.0.0` via the `PNCA_HOST` env override; port 8199 always
  comes from `config/app.yaml`.

## Key invariants

- `contacts` is always rebuildable (`SPEC.md §4, §11`).
- `content_hash` makes ingest idempotent; re-runs never duplicate.
- Closed enums (`config/rubric.yaml`): unknown values become `Unknown`, never guessed.
- Web fetches respect robots.txt and stop on 401/403/429/CAPTCHA; no evasion (`SPEC.md §15, §18`).
