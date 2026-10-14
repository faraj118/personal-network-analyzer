# Security Policy

PNCA stores personal data about real people, so security and privacy bugs are taken
seriously.

## Supported versions

PNCA is pre-1.0. Only the latest `main` receives fixes.

## Reporting a vulnerability

**Please don't open a public issue for security problems.**

Report privately through GitHub:
[**Report a vulnerability**](https://github.com/faraj118/personal-network-analyzer/security/advisories/new).

Include:

- what the problem is and where (file, route, setting);
- steps to reproduce, ideally with synthetic data;
- the impact you think it has.

**Never include real personal data** (contacts, exports, card photos) in a report.

## What to expect

This is a volunteer, single-maintainer project. Realistic targets:

- acknowledgement within **7 days**;
- an assessment and a fix plan within **30 days** for confirmed issues;
- credit in the advisory and changelog, unless you'd rather stay anonymous.

## Scope

PNCA's threat model is a **single user on their own machine**, with the server bound to
`127.0.0.1`.

**In scope**, for example:

- anything that exposes data beyond `127.0.0.1`, or sends contact data off the machine
  without the user turning that on;
- server-side request forgery or unsafe URL handling in the enrichment fetcher;
- path traversal or unsafe file handling in uploads (CSV, card images);
- injection (SQL, template/XSS) in the web UI;
- erasure that leaves personal data behind after a contact is deleted;
- bugs that let enrichment bypass `robots.txt` or keep going after a block.

**Out of scope:**

- an attacker who already has access to your user account or disk (use full-disk encryption;
  database encryption is tracked in #3);
- exposing the server on a public interface yourself, against the documented setup;
- vulnerabilities in third-party dependencies without a demonstrated impact on PNCA (please
  report those upstream).
