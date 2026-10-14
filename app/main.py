"""FastAPI entrypoint. Host/port come from config/app.yaml — never hardcoded."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import (
    contacts,
    discovery,
    enrich,
    graph,
    ingest,
    planning,
    review,
    score,
    signals,
)
from app.config import get_config
from app.db import init_db
from app.web import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure schema exists on boot (idempotent).
    init_db()
    yield


app = FastAPI(title="PNCA", version=__version__, lifespan=lifespan)

app.include_router(ingest.router)
app.include_router(contacts.router)
app.include_router(review.router)
app.include_router(score.router)
app.include_router(graph.router)
app.include_router(discovery.router)
app.include_router(enrich.router)
app.include_router(signals.router)
app.include_router(planning.router)
app.include_router(web_router)


@app.get("/health")
def health() -> dict:
    cfg = get_config()
    return {"status": "ok", "version": __version__, "bind": f"{cfg.server.host}:{cfg.server.port}"}


def main() -> None:
    """Console entrypoint: bind strictly to the configured host/port."""
    import uvicorn

    cfg = get_config()
    uvicorn.run(app, host=cfg.server.host, port=cfg.server.port)


if __name__ == "__main__":
    main()
