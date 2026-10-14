# Contributing

The authoritative build spec is [`SPEC.md`](SPEC.md) — read it before writing code.

## Attribution policy

The commit author is the only attribution. Commit messages, PR titles and PR bodies must not
contain:

- `Co-authored-by:` trailers
- "Generated with/by [tool]" footers or 🤖 markers from any code-generation or AI tool
- `*-Session: <url>` trailers linking to a tool's session

Configure your tools so they don't add these. Two layers enforce the rule:

1. **Local hook** (once per clone): `git config core.hooksPath .githooks`. It rejects an
   offending commit message before the commit is made.
2. **CI** (`.github/workflows/attribution.yml`) checks every PR's commits, title and body, and
   every push to `main`/`develop`. A failing check blocks the merge.

Tool- or editor-specific config files (assistant instruction files, local settings) stay out of
the repo. Put them in `.git/info/exclude` on your machine.
