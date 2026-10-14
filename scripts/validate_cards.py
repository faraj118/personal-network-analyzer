"""Business-card OCR validation harness (SPEC.md §13).

Runs the real OCR + extraction cascade over every card image in a folder and
reports what was read. If a card has a sibling ``<name>.expected.json`` label,
it also scores field-by-field accuracy and prints an aggregate.

Usage (inside the docker image, where the OCR engines live):
    docker compose run --rm pnca python scripts/validate_cards.py [DIR]

DIR defaults to tests/golden/. Drop real card photos there first; see
tests/golden/README.md for the label format. With no labels, this is still
useful — it shows exactly what the scanner extracts from each card.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.pipeline.ingest_card import _CARD_FIELDS, read_card

_IMG_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _norm(v: object) -> str:
    return str(v or "").strip().casefold()


def _score_card(got: dict, expected: dict) -> tuple[int, int, list[str]]:
    """Return (correct, total_labelled, mismatches) over the labelled fields."""
    correct = 0
    total = 0
    misses: list[str] = []
    for field in _CARD_FIELDS:
        if field not in expected:  # only score fields the label actually pins down
            continue
        total += 1
        if _norm(got.get(field)) == _norm(expected.get(field)):
            correct += 1
        else:
            misses.append(f"{field}: got {got.get(field)!r} != {expected.get(field)!r}")
    return correct, total, misses


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("tests/golden")
    if not root.exists():
        print(f"No such directory: {root}")
        return 2
    images = sorted(p for p in root.iterdir() if p.suffix.lower() in _IMG_SUFFIXES)
    if not images:
        print(f"No card images (.jpg/.jpeg/.png) in {root}/ — drop some real cards there first.")
        print("See tests/golden/README.md for the (optional) label format.")
        return 1

    grand_correct = grand_total = labelled_cards = 0
    for img in images:
        card = read_card(img.read_bytes(), origin_file=img.name)
        print(f"\n=== {img.name} ===")
        if card is None:
            print("  OCR returned nothing (unreadable / blank).")
            continue
        print(f"  confidence: {card['confidence']:.2f}")
        for field in _CARD_FIELDS:
            print(f"  {field:12} {card['fields'].get(field) or '—'}")

        label = img.with_suffix(img.suffix + ".expected.json")
        alt = img.with_name(img.stem + ".expected.json")
        label = label if label.exists() else alt
        if label.exists():
            expected = json.loads(label.read_text())
            correct, total, misses = _score_card(card["fields"], expected)
            labelled_cards += 1
            grand_correct += correct
            grand_total += total
            pct = (100 * correct / total) if total else 0
            print(f"  -> {correct}/{total} fields correct ({pct:.0f}%)")
            for m in misses:
                print(f"     ✗ {m}")

    print("\n" + "=" * 40)
    print(f"Cards scanned: {len(images)} · labelled: {labelled_cards}")
    if grand_total:
        print(
            f"Field-level accuracy on labelled cards: "
            f"{grand_correct}/{grand_total} = {100 * grand_correct / grand_total:.1f}%"
        )
    else:
        print("No labels found — add <card>.expected.json files to get an accuracy number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
