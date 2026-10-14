# PNCA dev/runtime image (Python 3.14; every dependency ships a prebuilt 3.14 wheel).
# Local-only tool; kept localhost-only via the compose port mapping.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PNCA_HOST=0.0.0.0

# Tesseract (English + Arabic) for the business-card OCR path (Phase 1b, §6).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy metadata first so the dependency layer caches independently of source churn.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install -e ".[dev,ocr]"

# Remaining project files (config, migrations, tests).
COPY . .

# Run as a non-root user whose UID/GID match the host owner (1000) so files written
# to the mounted ./data volume are owned by the host user, not root.
RUN useradd --uid 1000 --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8199
CMD ["python", "-m", "app.main"]
