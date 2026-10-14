# Golden card set (OCR validation — SPEC.md §13)

Drop **5–15 real business-card photos** here to measure the scanner's accuracy.
Aim for a realistic mix: Arabic, English, bilingual, some messy / low-contrast /
double-sided. Filenames can be anything (`card01.jpg`, `ahmed.png`, …).

Accepted image types: `.jpg`, `.jpeg`, `.png`.

> These images may contain personal data — this folder is for **your own** cards
> or ones you're authorized to test with. It is a local test fixture.

## Optional: label a card so accuracy can be scored

Next to any image `card01.jpg`, add `card01.expected.json` with the fields you
can verify by eye. Only include fields you actually want scored — omit the rest.

```json
{
  "first_name": "Ahmed",
  "last_name": "Dughri",
  "job_title": "Managing Director",
  "company": "Delta Payments",
  "email": "ahmed@delta.ly",
  "phone": "+218 91 234 5678",
  "location": "Tripoli"
}
```

Scoring is case-insensitive and whitespace-trimmed.

## Run it

```bash
# unlabelled — just see what the scanner extracts from each card:
docker compose run --rm pnca python scripts/validate_cards.py

# labelled cards additionally print a field-by-field accuracy number.
```

Run inside the docker image (that's where PaddleOCR / EasyOCR / Tesseract live).
