import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import get_settings
from app.core.database import init_db
from app.core.redis_client import get_redis, close_redis
from app.api.routes import auth, clips, streams, webhooks, debug
from app.workers.video_worker import run_video_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 TwitchClipper starting up...")
    await init_db()
    await get_redis()  # Initialize Redis connection

    # Start video processing worker in background
    video_worker_task = asyncio.create_task(run_video_worker())

    # Ensure output directories exist
    Path(settings.CLIPS_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.PROCESSED_DIR).mkdir(parents=True, exist_ok=True)

    logger.info("✅ All services started")
    yield

    # Shutdown
    logger.info("👋 Shutting down...")
    video_worker_task.cancel()
    await close_redis()


app = FastAPI(
    title="TwitchClipper API",
    description="AI-powered Twitch highlight detection and clipping",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(clips.router)
app.include_router(streams.router)
app.include_router(webhooks.router)
if settings.DEBUG:
    app.include_router(debug.router)

# Serve processed clips as static files
processed_path = Path(settings.PROCESSED_DIR)
processed_path.mkdir(parents=True, exist_ok=True)
app.mount("/processed", StaticFiles(directory=settings.PROCESSED_DIR), name="processed")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# WebSocket for real-time score updates
from fastapi import WebSocket, WebSocketDisconnect
import json
import redis.asyncio as redis_async

@app.websocket("/ws/{broadcaster_id}")
async def websocket_endpoint(websocket: WebSocket, broadcaster_id: str):
    await websocket.accept()
    r = await get_redis()
    pubsub = r.pubsub()

    channels = [
        f"stream:{broadcaster_id}:score",
        f"stream:{broadcaster_id}:clip",
        f"stream:{broadcaster_id}:chat",
    ]
    await pubsub.subscribe(*channels)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(json.dumps({
                    "channel": message["channel"],
                    "data": json.loads(message["data"]),
                }))
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()
