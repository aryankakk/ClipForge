"""
Clip creator - called when a highlight score threshold is met.
Creates the Twitch clip via API, stores it in the DB, and enqueues video processing.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Clip, Streamer, Stream, ClipStatus
from app.services.twitch_api import TwitchAPIClient
from app.core.redis_client import publish

logger = logging.getLogger(__name__)


async def create_clip_for_moment(
    db: AsyncSession,
    broadcaster_id: str,
    highlight_score: float,
    score_breakdown: dict,
    chat_context: list,
    transcript: Optional[str] = None,
) -> Optional[Clip]:
    """
    Full clip creation flow:
    1. Look up streamer tokens
    2. Call Twitch Create Clip API
    3. Wait for clip to be ready (Twitch takes a few seconds)
    4. Store in DB
    5. Publish event for video pipeline
    """
    # Fetch streamer
    result = await db.execute(
        select(Streamer).where(Streamer.twitch_id == broadcaster_id)
    )
    streamer = result.scalar_one_or_none()
    if not streamer:
        logger.error(f"Streamer not found: {broadcaster_id}")
        return None

    # Fetch current stream
    result = await db.execute(
        select(Stream)
        .where(Stream.streamer_id == streamer.id, Stream.is_live == True)
        .order_by(Stream.created_at.desc())
    )
    stream = result.scalar_one_or_none()

    # Create Twitch clip
    twitch = TwitchAPIClient(
        access_token=streamer.access_token,
        refresh_token=streamer.refresh_token,
    )

    try:
        clip_response = await twitch.create_clip(broadcaster_id)
    except Exception as e:
        logger.error(f"Failed to create Twitch clip for {broadcaster_id}: {e}")
        clip_response = None

    # Build DB record
    clip = Clip(
        streamer_id=streamer.id,
        stream_id=stream.id if stream else None,
        highlight_score=highlight_score,
        score_breakdown=score_breakdown,
        chat_context=chat_context,
        transcript=transcript,
        status=ClipStatus.PENDING,
        detected_at=datetime.utcnow(),
    )

    if clip_response:
        clip.twitch_clip_id = clip_response.get("id")
        clip.twitch_clip_url = clip_response.get("edit_url")
        clip.status = ClipStatus.PROCESSING

        # Wait and fetch full clip metadata
        asyncio.create_task(_fetch_clip_metadata_later(clip.twitch_clip_id, streamer, clip.id, db))

    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    # Notify frontend
    await publish(f"stream:{broadcaster_id}:clip", {
        "clip_id": clip.id,
        "twitch_clip_id": clip.twitch_clip_id,
        "score": highlight_score,
        "breakdown": score_breakdown,
        "status": clip.status.value,
    })

    logger.info(
        f"✅ Clip created: {clip.id} | Twitch: {clip.twitch_clip_id} | Score: {highlight_score}"
    )
    return clip


async def _fetch_clip_metadata_later(
    twitch_clip_id: str,
    streamer: Streamer,
    clip_db_id: str,
    db: AsyncSession,
):
    """Twitch clips take ~15s to become available after creation."""
    await asyncio.sleep(20)
    try:
        twitch = TwitchAPIClient(
            access_token=streamer.access_token,
            refresh_token=streamer.refresh_token,
        )
        clip_meta = await twitch.get_clip(twitch_clip_id)
        if clip_meta:
            result = await db.execute(select(Clip).where(Clip.id == clip_db_id))
            clip = result.scalar_one_or_none()
            if clip:
                clip.twitch_thumbnail_url = clip_meta.get("thumbnail_url")
                clip.duration_seconds = clip_meta.get("duration")
                clip.status = ClipStatus.READY
                await db.commit()
                logger.info(f"Clip metadata updated: {clip_db_id}")
    except Exception as e:
        logger.error(f"Failed to fetch clip metadata: {e}")
