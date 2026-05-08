import random
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis_client import (
    get_cached,
    add_score_event,
    get_score_events,
    publish,
    set_stream_live,
)
from app.models.models import Clip, ClipStatus, Stream, Streamer
from app.services import stream_manager

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/debug", tags=["debug"])

_FAKE_CHAT_MESSAGES = ["clip that", "OMG", "no way", "LOL", "CLIP IT", "PogChamp", "monkaS", "KEKW"]


async def _get_streamer(token: str, db: AsyncSession) -> Streamer:
    session = await get_cached(f"session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    result = await db.execute(select(Streamer).where(Streamer.id == session["streamer_id"]))
    streamer = result.scalar_one_or_none()
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")
    return streamer


@router.post("/fake-chat-spike")
async def fake_chat_spike(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await _get_streamer(token, db)
    broadcaster_id = streamer.twitch_id

    # Push a burst of chat score events (simulates spike)
    messages_used = random.choices(_FAKE_CHAT_MESSAGES, k=12)
    for msg in messages_used:
        await add_score_event(broadcaster_id, score=5.0, source="chat")

    # Publish each fake chat message to the chat WebSocket channel
    for msg in messages_used:
        await publish(f"stream:{broadcaster_id}:chat", {
            "type": "chat",
            "username": f"debug_user_{random.randint(100, 999)}",
            "message": msg,
            "timestamp": datetime.utcnow().isoformat(),
        })

    # Publish an aggregated score update so the dashboard reflects the spike
    events = await get_score_events(broadcaster_id)
    total_score = sum(e["score"] for e in events)
    await publish(f"stream:{broadcaster_id}:score", {
        "type": "score_update",
        "score": total_score,
        "breakdown": {"chat": total_score},
        "event_count": len(events),
    })

    return {
        "ok": True,
        "broadcaster_id": broadcaster_id,
        "messages_injected": messages_used,
        "total_score": total_score,
        "score_event_count": len(events),
    }


@router.post("/force-clip")
async def force_clip(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await _get_streamer(token, db)

    # Find the most recent live stream for this streamer (may be None)
    result = await db.execute(
        select(Stream)
        .where(Stream.streamer_id == streamer.id)
        .order_by(Stream.created_at.desc())
        .limit(1)
    )
    stream = result.scalar_one_or_none()

    fake_chat = [
        {"username": "viewer1", "message": "clip that", "timestamp": datetime.utcnow().isoformat()},
        {"username": "viewer2", "message": "OMG no way", "timestamp": datetime.utcnow().isoformat()},
        {"username": "viewer3", "message": "LOL", "timestamp": datetime.utcnow().isoformat()},
    ]

    clip = Clip(
        streamer_id=streamer.id,
        stream_id=stream.id if stream else None,
        highlight_score=99.0,
        score_breakdown={"chat": 60.0, "audio": 25.0, "debug": 14.0},
        status=ClipStatus.READY,
        transcript="And then he hit the most insane shot — chat absolutely exploded.",
        chat_context=fake_chat,
        ai_title=f"INSANE Highlight – {streamer.display_name} Goes Off",
        ai_description="Debug-forced clip with a perfect highlight score for local testing.",
        ai_hashtags=["clip", "highlight", "debug"],
        detected_at=datetime.utcnow(),
        duration_seconds=30.0,
    )
    db.add(clip)
    await db.commit()
    await db.refresh(clip)

    # Notify WebSocket subscribers
    await publish(f"stream:{streamer.twitch_id}:clip", {
        "type": "clip_created",
        "clip_id": clip.id,
        "score": clip.highlight_score,
        "ai_title": clip.ai_title,
    })

    return {
        "ok": True,
        "clip": {
            "id": clip.id,
            "status": clip.status.value,
            "highlight_score": clip.highlight_score,
            "ai_title": clip.ai_title,
            "transcript": clip.transcript,
            "chat_context": clip.chat_context,
            "detected_at": clip.detected_at.isoformat(),
        },
    }


@router.post("/fake-stream-online")
async def fake_stream_online(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await _get_streamer(token, db)
    broadcaster_id = streamer.twitch_id

    # Mark any existing live stream offline first to avoid duplicate live rows
    existing = await db.execute(
        select(Stream)
        .where(Stream.streamer_id == streamer.id, Stream.is_live == True)
    )
    for stale in existing.scalars().all():
        stale.is_live = False
        stale.ended_at = datetime.utcnow()

    stream = Stream(
        streamer_id=streamer.id,
        is_live=True,
        title="[Debug] Fake Stream",
        game_name="Debug Game",
        started_at=datetime.utcnow(),
    )
    db.add(stream)
    await db.commit()
    await db.refresh(stream)

    # Update Redis live-stream cache
    await set_stream_live(broadcaster_id, {
        "streamer_id": streamer.id,
        "login": streamer.login,
        "stream_id": stream.id,
        "started_at": stream.started_at.isoformat(),
    })

    # Start StreamManager session (no-op if already active)
    session_started = False
    try:
        active = await stream_manager.get_active_session(broadcaster_id)
        if not active:
            session_started = await stream_manager.start_stream_session(broadcaster_id)
        else:
            session_started = True
    except Exception as exc:
        logger.warning(f"StreamManager could not start for {broadcaster_id}: {exc}")

    active_ids = stream_manager.get_all_active_broadcaster_ids()

    return {
        "ok": True,
        "stream": {
            "id": stream.id,
            "is_live": stream.is_live,
            "title": stream.title,
            "started_at": stream.started_at.isoformat(),
        },
        "session_started": session_started,
        "active_sessions": active_ids,
    }
