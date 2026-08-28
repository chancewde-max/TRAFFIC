import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routers import cameras, congestion, history, incidents, live
from .worker import run_worker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(run_worker(stop_event))
    app.state.stop_event = stop_event
    app.state.worker_task = worker_task
    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(worker_task, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            worker_task.cancel()


app = FastAPI(title="City Traffic Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(congestion.router)
app.include_router(history.router)
app.include_router(incidents.router)
app.include_router(live.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "camera_mode": settings.camera_mode}
