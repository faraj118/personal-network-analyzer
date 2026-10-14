# Governance

PNCA is a young project with one maintainer. This document says how decisions are made today
and how that will open up as the community grows.

## Roles

| Role | Who | What they do |
|---|---|---|
| **Maintainer** | [@faraj118](https://github.com/faraj118) (Faraj Elburkie) | Sets direction, reviews and merges PRs, cuts releases, enforces the Code of Conduct |
| **Triager** | Invited contributors | Label, reproduce and close issues; review PRs (no merge rights) |
| **Contributor** | Anyone | Opens issues, discussions and pull requests |

## How decisions are made

1. **Day-to-day changes** (bug fixes, features within scope) are decided in the pull request.
   If no one objects after review, it merges.
2. **Larger changes** (new modules, new dependencies, schema changes, UX overhauls) start as an
   issue or Discussion so the approach is agreed before code is written.
3. **Where there is disagreement**, the maintainer makes the final call and writes down the
   reasoning in the issue or PR.

## Changing the hard boundaries

The boundaries in `SPEC.md §15` (local-only, deterministic scoring, nothing invented, no
evasion, own network only, single user) define what PNCA is. Changing one requires:

1. A Discussion explaining the problem, the proposed change, and its privacy and legal
   implications. It stays open for at least **14 days** for comment.
2. A pull request that amends `SPEC.md`, with a dated amendment note, **before** any code
   that depends on it.
3. Maintainer approval.

## Becoming a triager or maintainer

Sustained, high-quality contributions and good conduct in reviews and discussions lead to an
invitation to triage. Triagers who show sound judgement over time may be offered merge
rights. When there are two or more maintainers, decisions move to lazy consensus among them.

## Repository rules

- `main` is protected: changes land only through pull requests with passing CI.
- Every PR passes lint, format, tests and the attribution check
  ([`CONTRIBUTING.md`](CONTRIBUTING.md#attribution-policy)).
- Security reports follow [`SECURITY.md`](SECURITY.md); conduct reports follow
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Releases

Releases follow [Semantic Versioning](https://semver.org/). Before 1.0, minor versions may
include breaking changes, which are always called out in [`CHANGELOG.md`](CHANGELOG.md).
