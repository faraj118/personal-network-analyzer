# Contributing to PNCA

Thanks for your interest. PNCA is a small project with a clear purpose, and every kind of
help counts: code, design, Arabic translation, testing, documentation, research.

The authoritative engineering spec is [`SPEC.md`](SPEC.md). Skim it before writing code,
especially §14 (conventions) and §15 (hard boundaries).

## Ways to contribute

| You are… | You can help with |
|---|---|
| New to open source | Issues labelled [`good first issue`](https://github.com/faraj118/personal-network-analyzer/issues?q=is%3Aopen+label%3A%22good+first+issue%22) |
| A Python developer | Issues labelled [`help wanted`](https://github.com/faraj118/personal-network-analyzer/issues?q=is%3Aopen+label%3A%22help+wanted%22) |
| A designer | Synthetic business cards (#1), right-to-left layout (#7), UI polish |
| An Arabic speaker | Arabic UI and right-to-left layout (#7), checking Arabic card extraction |
| A user | Bug reports, feature ideas in [Discussions](https://github.com/faraj118/personal-network-analyzer/discussions), docs fixes |

**Claiming work:** comment on the issue before you start so two people don't build the same
thing. If you've had no reply in a week, go ahead anyway.

## Development setup

**Docker (recommended):**

```bash
docker compose up -d --build                 # app at http://127.0.0.1:8199

# tests: mount your working tree, because the image holds the code from its last build
docker compose run --rm -v "$PWD/app:/app/app" -v "$PWD/tests:/app/tests" pnca pytest -q
```

**Local Python 3.11+:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check . && black --check .
```

Then turn on the commit-message check once per clone:

```bash
git config core.hooksPath .githooks
```

## Workflow

1. Fork the repo and create a branch from `main`: `feature/<short-name>`, `fix/<short-name>`
   or `docs/<short-name>`.
2. Keep pull requests small and focused, one concern per PR.
3. Write a commit message that says what changed and why, in the imperative
   ("Add vCard export", not "Added stuff").
4. Open a PR against `main`, fill in the template, and link the issue (`Closes #4`).
5. CI must pass: `ruff`, `black --check`, `pytest`, and the attribution check. Changes reach
   `main` only through pull requests.
6. The maintainer reviews, usually within a week. Expect questions; they're about the code,
   not you.

## Code standards

- Type hints everywhere; Pydantic models at boundaries.
- Pipeline, LLM and enrichment stages are pure `input -> typed object` functions. Database
  side effects live only in `app/db.py`.
- No hardcoded settings: add them to `config/app.yaml` or `config/rubric.yaml`.
- Fail loud. Never coerce bad data into `contacts`.
- `ruff` + `black`, line length 100.
- **Tests are required** for new behaviour. Network access is never allowed in tests: use
  recorded fixtures.
- Update docs in the **same** PR when behaviour or structure changes (`README.md`,
  `docs/`, and `SPEC.md` if a decision shifts).

## Hard boundaries

PRs that cross these will be declined, however good the code (`SPEC.md §15`):

- **Local only.** No cloud LLMs, no paid APIs or data brokers, no telemetry.
- **Deterministic scoring.** No model ever assigns or adjusts a score.
- **Nothing invented.** The LLM extracts only from text it is given; enriched facts are
  sourced and review-gated, never silently written.
- **No evasion.** No proxy rotation, CAPTCHA solving, User-Agent spoofing or scraping of
  login-walled sites. Blocked means stop.
- **Own network only.** No features for mass-collecting data on people outside the user's
  contacts. No special-category data (health, religion, ethnicity, politics, sexuality).
- **Single user.** No multi-user or authentication features.

If you think a boundary should change, open a Discussion first (see [`GOVERNANCE.md`](GOVERNANCE.md)).

## Privacy in contributions

- **Never commit real personal data**: no real contacts, CSV exports, card photos or
  databases, not even in tests or screenshots.
- Use clearly fictional names and synthetic data. Real business cards need the card owner's
  explicit consent.
- If you spot personal data in the repo, report it privately (see [`SECURITY.md`](SECURITY.md)).

## Attribution policy

Credit goes to people. If you paired with someone, credit them with a normal
`Co-authored-by: Name <email>` trailer; that's welcome.

What's not allowed is attribution to code-generation or AI tools. Commit messages, PR titles
and PR bodies must not contain:

- `Co-authored-by:` trailers for a tool or bot (a `[bot]` account or a generic `noreply@`
  vendor address)
- "Generated with/by [tool]" footers or 🤖 markers
- `*-Session: <url>` trailers linking to a tool's session

You're responsible for every line you submit, however you wrote it. Configure your tools so
they don't add these markers. Two layers enforce the rule:

1. **Local hook** (`git config core.hooksPath .githooks`) rejects an offending commit
   message before the commit is made.
2. **CI** (`.github/workflows/attribution.yml`) checks every PR's commits, title and body,
   and every push to `main`. A failing check blocks the merge.

Tool- or editor-specific config files (assistant instruction files, local settings) stay out
of the repo. Put them in `.git/info/exclude` on your machine.

## License of contributions

PNCA is licensed under the [Apache License 2.0](LICENSE). By submitting a contribution you
agree that it is licensed under the same terms (Apache-2.0 §5), and that you have the right to
submit it.

## Code of conduct

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
