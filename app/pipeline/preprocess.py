"""Image preprocessing for OCR (SPEC.md §2). Pillow-based (lean); OpenCV is a later upgrade.

Grayscale + autocontrast + upscale small images — cheap wins for card OCR. Pillow is
imported lazily so this module imports even when the OCR extra isn't installed.
"""

from __future__ import annotations

import io


def preprocess(image_bytes: bytes):
    """Return a cleaned PIL image ready for OCR."""
    from PIL import Image, ImageOps

    img = Image.open(io.BytesIO(image_bytes)).convert("L")  # grayscale
    img = ImageOps.autocontrast(img)
    if img.width and img.width < 1200:  # upscale small captures for better OCR
        scale = 1200 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return img
