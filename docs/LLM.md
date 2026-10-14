# Local LLM (Ollama) — model choice & rationale

Per `SPEC.md §7, §17`. Local-only, bounded, degrade-if-down. This file records **why** the
default model was chosen and the measured benchmark on this machine.

## Hardware (measured 2026-09-21)

| Resource | Value | Implication |
|---|---|---|
| CPU | Intel Core 7 150U, 12 threads, ~15 W ultrabook | CPU-only inference; small models only |
| RAM | 14 GiB total, **~3.9 GiB available** | **Binding constraint.** 7B (~4.5 GB) would OOM/swap |
| Disk | 78 GB, **~11 GB free** | Frugal: prefer ~1 GB models + the Ollama image |
| GPU | none | No acceleration |

## Decision

**Default: `qwen2.5:1.5b`** (set in `config/app.yaml → llm.model`; instruct-tuned by default in Ollama).

Why:
- **Fits RAM** — ~1 GB on disk, ~2 GB resident; comfortable under ~3.9 GB available.
- **Multilingual / Arabic** — Qwen2.5 handles Arabic markedly better than Llama-3.2-1B, which
  matters for the Arabic-card extraction pain (`SPEC.md §16`).
- **CPU-fast** — 1.5B is responsive on 12 threads for short extraction prompts.
- **Selective use** — invoked only on Arabic/low-confidence text (`llm.invoke_on`), never the
  bulk CSV path, so latency stays off the hot path.

Upgrade path: `qwen2.5:3b-instruct` if RAM headroom improves (close other apps) — better
quality, ~2 GB disk / ~3.5 GB RAM. Re-benchmark before switching the default.

## Benchmark (measured 2026-09-21, Ollama 0.34.2, CPU)

Reproduce:
```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:1.5b
# POST a constrained extract-from-text prompt to /api/generate (English + Arabic card)
```

| Metric | Value |
|---|---|
| Model pull size | 986 MB |
| Cold load time | ~4.1 s (first call only) |
| Generation | ~8.5 tok/s (94 tok in ~11 s) |
| Total (this card) | ~20 s incl. load + prompt eval |
| Arabic extract sanity | ✅ correctly extracted Arabic job title (المدير التنفيذي) + mixed AR/EN company, plus name/email/phone/location |

**Verdict:** validated. Arabic extraction — the §16 pain point — works well. CPU latency
(~11–20 s/card) is fine for **selective** use (`llm.invoke_on: [arabic, low_confidence]`),
never the bulk CSV path. The app also runs fully without it (`llm.enabled: false` default).

## Guardrails (enforced in `app/llm/`)

- `client.available()` gates every call; unreachable ⇒ deterministic fallback (no crash).
- Prompts (`app/llm/prompts/`) are **extract-from-provided-text only** — no fact invention.
- Outputs cached by hash(model, prompt) ⇒ reproducible re-runs.
- Never in the scoring path (`SPEC.md §4`).
