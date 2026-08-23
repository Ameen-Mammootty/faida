import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router as api_router
from .config import get_settings
from .db import Database
from .extraction.pipeline import build_provider
from .storage import Storage
from .wa import WhatsAppClient
from .waitlist import router as waitlist_router
from .webhook import router as webhook_router
from .worker import worker_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    await app.state.db.connect()
    app.state.wa = WhatsAppClient(settings)
    app.state.storage = Storage(settings)
    # None without a key: extract jobs then fail into plan.md §5 layer 6 while
    # ingest and (from M3) upload + manual entry keep working.
    app.state.provider = build_provider(settings.anthropic_api_key)

    stop = asyncio.Event()
    worker_task: asyncio.Task | None = None
    if settings.worker_enabled:
        worker_task = asyncio.create_task(
            worker_loop(
                app.state.db,
                app.state.wa,
                app.state.storage,
                app.state.provider,
                stop,
                settings.worker_poll_seconds,
            )
        )

    try:
        yield
    finally:
        stop.set()
        if worker_task is not None:
            await worker_task
        await app.state.wa.close()
        await app.state.storage.close()
        await app.state.db.close()


app = FastAPI(title="Faida API", lifespan=lifespan)
# CORS for the review screen (C6): exactly one allowed origin, the web app's.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(webhook_router)
app.include_router(api_router)
app.include_router(waitlist_router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "db": await app.state.db.ping()}
