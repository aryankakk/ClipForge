from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import logging

from app.core.database import get_db
from app.core.redis_client import get_cached, get_stream_live, get_score_events
from app.models.models import Streamer, Stream, Clip
from app.services.stream_manager import get_all_active_broadcaster_ids, start_stream_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/streams", tags=["streams"])


@router.get("/status")
async def stream_status(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    session = await get_cached(f"session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await db.execute(
        select(Streamer).where(Streamer.id == session["streamer_id"])
    )
    streamer = result.scalar_one_or_none()
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")

    live_data = await get_stream_live(streamer.twitch_id)
    is_live = streamer.twitch_id in get_all_active_broadcaster_ids()

    # Get recent score events
    score_events = await get_score_events(streamer.twitch_id)
    current_score = sum(e.get("score", 0) for e in score_events)

    # Get recent stream
    result = await db.execute(
        select(Stream)
        .where(Stream.streamer_id == streamer.id)
        .order_by(desc(Stream.created_at))
        .limit(1)
    )
    stream = result.scalar_one_or_none()

    # Get clip counts
    result = await db.execute(
        select(Clip).where(Clip.streamer_id == streamer.id)
    )
    all_clips = result.scalars().all()

    clip_stats = {
        "total": len(all_clips),
        "pending": sum(1 for c in all_clips if c.status.value == "pending"),
        "ready": sum(1 for c in all_clips if c.status.value == "ready"),
        "approved": sum(1 for c in all_clips if c.status.value == "approved"),
    }

    return {
        "is_live": is_live,
        "live_data": live_data,
        "current_score": current_score,
        "score_threshold": 60.0,
        "score_events": score_events[-10:],
        "stream": {
            "id": stream.id if stream else None,
            "title": stream.title if stream else None,
            "game_name": stream.game_name if stream else None,
            "started_at": stream.started_at.isoformat() if stream and stream.started_at else None,
            "is_live": stream.is_live if stream else False,
        } if stream else None,
        "clip_stats": clip_stats,
        "streamer": {
            "id": streamer.id,
            "login": streamer.login,
            "display_name": streamer.display_name,
            "profile_image_url": streamer.profile_image_url,
        },
    }


@router.post("/start-monitoring")
async def manually_start_monitoring(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Manually start monitoring (for testing without being live)."""
    session = await get_cached(f"session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    await start_stream_session(session["twitch_id"])
    return {"ok": True, "message": "Monitoring started"}
