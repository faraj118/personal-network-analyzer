# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Community and governance files: code of conduct, contributing guide, governance, security
  policy, support guide, issue and PR templates, CODEOWNERS, Dependabot.
- Attribution policy, enforced by a commit-msg hook and a CI check.
- README and architecture docs with system, data-flow, deduplication and data-model diagrams.

### Initial public release (2026-10-14)

- Ingest of LinkedIn `Connections.csv`, business-card photos (OCR, Arabic + English) and
  manual entry, with idempotent `source_records`.
- Deduplication (exact email/phone auto-merge, fuzzy matches to review), rule-based
  classification, and a deterministic YAML-rubric priority score.
- Network discovery with NetworkX: hubs, communities, bridge contacts, gaps.
- Review-gated enrichment from free public sources (Wikidata, news RSS) with full provenance,
  plus per-contact profiles.
- CRM features: edit, tags, notes, pipeline kanban, tasks, interaction timeline, saved views,
  `.ics` calendar export, CSV/JSON export, data-health page.
- Optional local LLM (Ollama): card-field extraction, outreach drafts, meeting briefs,
  plain-English questions over your network.
