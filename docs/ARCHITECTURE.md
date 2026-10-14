# PNCA Architecture (as-built, Phase 0)

Mirrors `SPEC.md §2–§8`. This file tracks what actually exists in code; update it in the
same change that alters structure.

## Data flow

```
inputs (CSV/JSON export | card image)
   -> app/pipeline/ingest_csv | preprocess -> ocr -> extract   (typed ExtractionResult)
   -> app/pipeline/classify -> score -> dedup                  (rule/deterministic)
   -> source_records (immutable)  ==rebuild==>  contacts (canonical)
   -> app/discovery/graph -> metrics                           (NetworkX, Type-B)
   -> app/api/*  (FastAPI, bound 127.0.0.1:8199)
```

## Layering / boundaries

- **Config** (`app/config.py`): loads `config/app.yaml` once, validated by Pydantic. The
  only place host/port/asset-paths are defined. Nothing else hardcodes them.
- **DB** (`app/db.py`): the only module with SQLite side-effects. Schema in
  `db/migrations/*.sql`, applied idempotently on boot.
- **Pipeline** (`app/pipeline/`): pure `input -> typed object` stages, no DB access.
- **Discovery** (`app/discovery/`): pure graph build + metrics over contact dicts.
- **API** (`app/api/`): thin routers; one module per §10 group. Phase-0 stubs return `501`.
- **Models** (`app/models/`): Pydantic boundary schemas + closed enums.

## Runtime / deployment

- **Docker** (`Dockerfile`, `docker-compose.yml`) is the supported dev/runtime path:
  `python:3.11-slim` (host is 3.14 with no pip; ML wheels lag it). Runs as non-root UID 1000
  so files on the mounted `./data` volume are host-owned.
- Localhost-only (§12) is enforced by the compose mapping `127.0.0.1:8199:8199`. The
  container process listens on `0.0.0.0` via the `PNCA_HOST` env override; **port 8199 is
  always sourced from `config/app.yaml`** and is never overridable.

## Key invariants

- `contacts` is always rebuildable from `source_records` (`SPEC.md §4, §11`).
- `content_hash` gives idempotent ingest; re-runs never duplicate.
- Closed enums (`config/rubric.yaml`): unknown values become `Unknown`, never guessed.
- Web fetches are robots-respecting and stop on block; no evasion (`SPEC.md §15, §18`).
