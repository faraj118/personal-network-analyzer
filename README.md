# PNCA — Personal Network & Contact Analyzer

[![CI](https://github.com/faraj118/personal-network-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/faraj118/personal-network-analyzer/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

A **local-first, private CRM for your professional network.** Import your LinkedIn
connections and business cards (English **and Arabic**), and PNCA tells you who matters,
who connects your circles, and who you should reach out to next. Everything runs on your
machine. No cloud, no paid APIs, no data leaves your laptop.

Built in Tripoli, Libya, for people whose networks live in spreadsheets, card holders and
WhatsApp, not in a Salesforce instance.

## What it does

| | |
|---|---|
| **Import** | LinkedIn's official `Connections.csv` export, business-card photos (OCR, Arabic + English), or manual entry |
| **Clean** | Deduplicates contacts: exact email/phone auto-merge, fuzzy name/company matches go to a review queue |
| **Score** | Deterministic, explainable priority score from a YAML rubric (seniority, industry, geography, org prominence). No model assigns scores |
| **Discover** | Graph analytics with NetworkX: hubs, clusters, and **bridge contacts** who connect otherwise separate circles |
| **Enrich** | Optional, opt-in: free public sources (Wikidata, news RSS) add facts and "job change / funding" signals, each with a source URL and confidence, and nothing is saved until you approve it |
| **Act** | Follow-ups, tasks, pipeline stages, interaction timeline, `.ics` calendar export, CSV/JSON export |
| **Assist** | Optional local LLM (Ollama): draft a reconnect message, prep a meeting brief, ask your network in plain English |

## Design principles

- **Local-only.** The server binds to `127.0.0.1`. The SQLite database is gitignored and never leaves your machine.
- **Deterministic where it matters.** The scorer is a pure function of a YAML rubric; the LLM is never in the scoring path.
- **Nothing invented.** The LLM may only extract facts present in the text it's given. Every enriched fact carries its source and stays pending until you accept it.
- **Polite on the web.** Enrichment respects `robots.txt`, rate-limits itself, uses an honest User-Agent, and stops on any block. No scraping of login-walled sites.
- **Erasable.** Deleting a contact cascades to every fact and signal about them. No special-category data (health, religion, politics, etc.) is collected.
- **Degrades gracefully.** With the LLM off, everything except drafting/briefs still works.

## Quickstart (Docker)

```bash
git clone https://github.com/faraj118/personal-network-analyzer.git
cd personal-network-analyzer
docker compose up -d --build
open http://127.0.0.1:8199          # or visit it in your browser
```

Get your LinkedIn data: **LinkedIn → Settings → Data privacy → Get a copy of your data →
Connections**, then upload `Connections.csv` on the home page.

To enable the local LLM (optional):

```bash
docker compose exec ollama ollama pull qwen2.5:1.5b
# then set llm.enabled: true in config/app.yaml
```

## Without Docker

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                 # core
pip install -e ".[ocr,enrich]"          # optional: card OCR (needs tesseract) + enrichment
python -m app.main                      # http://127.0.0.1:8199
pytest -q
```

## Configuration

| File | Purpose |
|---|---|
| [`config/app.yaml`](config/app.yaml) | Server, database, LLM and enrichment settings |
| [`config/rubric.yaml`](config/rubric.yaml) | Scoring weights, your target industries and geographies |
| [`config/gazetteers/`](config/gazetteers/) | Title, seniority and industry keyword lists |

## Architecture

```
inputs (CSV export | card photo | manual)
   -> source_records   (immutable, provenance)
   -> extract -> classify -> dedup -> contacts (canonical, rebuildable)
   -> score (pure rubric)    -> priorities
   -> graph (NetworkX)       -> hubs, clusters, bridges
   -> enrichment (opt-in)    -> pending claims -> your review -> contacts
```

FastAPI + Jinja2/htmx · SQLite (WAL) · pandas · NetworkX · rapidfuzz · Tesseract · Ollama.
See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/ENRICHMENT.md`](docs/ENRICHMENT.md)
and [`docs/LLM.md`](docs/LLM.md). The full engineering spec lives in [`SPEC.md`](SPEC.md).

## Contributing

Issues and pull requests are welcome. Please keep within the hard boundaries in `SPEC.md §15`:
no cloud LLMs or paid data sources, no anti-bot evasion, no scraping of login-walled sites,
single-user and local-only. CI runs `ruff`, `black --check` and `pytest` on every PR.

## License

[Apache License 2.0](LICENSE) © 2026 Faraj Elburkie. Redistributions must keep the
[`NOTICE`](NOTICE) file.
