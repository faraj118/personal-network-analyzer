# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-14

First public release.

### Added

- Ingest of LinkedIn `Connections.csv`, business-card photos (OCR, Arabic + English) and
  manual entry, with idempotent `source_records`.
- Deduplication (exact email/phone auto-merge, fuzzy matches to review), rule-based
  classification, and a deterministic YAML-rubric priority score.
- Network discovery with NetworkX: hubs, communities, bridge contacts, gaps.
- Review-gated enrichment from free public sources (Wikidata, news RSS) with full provenance,
  plus per-contact profiles.
- CRM features: Today page, edit, tags, notes, pipeline kanban, tasks, interaction timeline,
  saved views, `.ics` calendar export, CSV/JSON export, data-health page.
- Optional local LLM (Ollama): card-field extraction, outreach drafts, meeting briefs,
  plain-English questions over your network.
- Synthetic demo data (`docs/demo/`), screenshots and a walkthrough GIF.
- Community and governance files: code of conduct, contributing guide, governance, security
  policy, support guide, issue and PR templates, CODEOWNERS, Dependabot.
- Attribution policy (no AI/tool attribution; human co-authors welcome), enforced by a
  commit-msg hook and a CI check.

### Fixed

- Home-page search returned HTTP 422 whenever the "min score" box was empty.
- Links on the home page used the browser's default dark blue, unreadable on the dark theme.

[Unreleased]: https://github.com/faraj118/personal-network-analyzer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/faraj118/personal-network-analyzer/releases/tag/v0.1.0
