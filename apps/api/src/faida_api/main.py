import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .db import Database
from .storage import Storage
from .wa import WhatsAppClient
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

    stop = asyncio.Event()
    worker_task: asyncio.Task | None = None
    if settings.worker_enabled:
        worker_task = asyncio.create_task(
            worker_loop(
                app.state.db,
                app.state.wa,
                app.state.storage,
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
app.include_router(webhook_router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "db": await app.state.db.ping()}
