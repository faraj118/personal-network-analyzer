"""OCR (SPEC.md §2, §6). v1 = Tesseract (en + ar); LLM cleans up the text downstream.

pytesseract/Pillow are imported lazily so this module loads without the OCR extra; callers
that inject their own OCR function (e.g. tests) never touch Tesseract.
"""

from __future__ import annotations


def run_ocr(image_bytes: bytes, lang: str = "eng+ara") -> tuple[str, float]:
    """OCR an image -> (text, mean_confidence 0..1). Handles English + Arabic cards."""
    import pytesseract

    from app.pipeline.preprocess import preprocess

    img = preprocess(image_bytes)
    text = pytesseract.image_to_string(img, lang=lang)
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
    confidence = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return text.strip(), round(confidence, 3)
