"""
Video processing worker - picks up approved clips and runs the FFmpeg pipeline.
"""
import asyncio
import logging
from pathlib import Path
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.models import Clip, ClipStatus, Streamer
from app.services.video_processor import VideoProcessor
from app.services.ai_service import transcribe_clip, generate_clip_metadata
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

VIDEO_QUEUE_KEY = "queue:video_processing"
processor = VideoProcessor()


async def enqueue_video_processing(clip_id: str):
    """Push clip_id to the Redis processing queue."""
    r = await get_redis()
    await r.rpush(VIDEO_QUEUE_KEY, clip_id)
    logger.info(f"Enqueued video processing for clip: {clip_id}")


async def run_video_worker():
    """Long-running worker that processes clips from the queue."""
    logger.info("Video processing worker started")
    r = await get_redis()

    while True:
        try:
            # Block until a clip is available (timeout 5s)
            item = await r.blpop(VIDEO_QUEUE_KEY, timeout=5)
            if item is None:
                continue

            _, clip_id = item
            logger.info(f"Processing clip: {clip_id}")
            await process_clip(clip_id)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Video worker error: {e}", exc_info=True)
            await asyncio.sleep(2)


async def process_clip(clip_id: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Clip).where(Clip.id == clip_id)
        )
        clip = result.scalar_one_or_none()
        if not clip:
            logger.error(f"Clip not found: {clip_id}")
            return

        # Fetch streamer info for AI context
        result = await db.execute(
            select(Streamer).where(Streamer.id == clip.streamer_id)
        )
        streamer = result.scalar_one_or_none()

        clip.status = ClipStatus.PROCESSING
        await db.commit()

        # 1. Download raw clip
        raw_path = None
        if clip.twitch_thumbnail_url:
            raw_path = await processor.download_clip(
                clip.twitch_thumbnail_url, clip.id
            )

        if not raw_path:
            logger.error(f"Failed to download clip {clip_id}")
            clip.status = ClipStatus.READY  # Keep ready, just no processed video
            await db.commit()
            return

        clip.raw_clip_path = str(raw_path)
        await db.commit()

        # 2. Transcribe with Whisper
        transcript = await transcribe_clip(raw_path)
        if transcript:
            clip.transcript = transcript
            await db.commit()

        # 3. Generate AI metadata
        game_name = None
        if clip.stream:
            game_name = clip.stream.game_name

        metadata = await generate_clip_metadata(
            transcript=clip.transcript,
            chat_context=clip.chat_context or [],
            score_breakdown=clip.score_breakdown or {},
            game_name=game_name,
            streamer_name=streamer.display_name if streamer else None,
        )

        clip.ai_title = metadata.get("title")
        clip.ai_description = metadata.get("description")
        clip.ai_hashtags = metadata.get("hashtags", [])
        await db.commit()

        # 4. Process video to vertical format
        processed_path = await processor.process_for_short(
            input_path=raw_path,
            clip_id=clip.id,
            transcript=clip.transcript,
            title=clip.ai_title,
        )

        if processed_path:
            clip.processed_clip_path = str(processed_path)
            processor.cleanup_raw(clip.id)

        clip.status = ClipStatus.APPROVED
        await db.commit()

        logger.info(f"✅ Clip processed successfully: {clip_id}")
