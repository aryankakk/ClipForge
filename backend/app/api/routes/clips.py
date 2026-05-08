from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from app.core.database import get_db
from app.core.config import get_settings
from app.core.redis_client import get_cached
from app.models.models import Clip, ClipStatus, Streamer

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/clips", tags=["clips"])


async def get_streamer_from_token(token: str, db: AsyncSession) -> Streamer:
    session = await get_cached(f"session:{token}")
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    result = await db.execute(
        select(Streamer).where(Streamer.id == session["streamer_id"])
    )
    streamer = result.scalar_one_or_none()
    if not streamer:
        raise HTTPException(status_code=404, detail="Streamer not found")
    return streamer


@router.get("/")
async def list_clips(
    token: str = Query(...),
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)

    q = select(Clip).where(Clip.streamer_id == streamer.id)

    if status:
        try:
            clip_status = ClipStatus(status)
            q = q.where(Clip.status == clip_status)
        except ValueError:
            pass

    q = q.order_by(desc(Clip.detected_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    clips = result.scalars().all()

    return {
        "clips": [_serialize_clip(c) for c in clips],
        "total": len(clips),
    }


@router.get("/{clip_id}")
async def get_clip(
    clip_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.streamer_id == streamer.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return _serialize_clip(clip)


@router.post("/{clip_id}/approve")
async def approve_clip(
    clip_id: str,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.streamer_id == streamer.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.status = ClipStatus.APPROVED
    clip.approved_at = datetime.utcnow()
    await db.commit()

    # Trigger video processing task
    from app.workers.video_worker import enqueue_video_processing
    await enqueue_video_processing(clip.id)

    return {"ok": True, "status": ClipStatus.APPROVED.value}


@router.post("/{clip_id}/reject")
async def reject_clip(
    clip_id: str,
    token: str = Query(...),
    reason: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.streamer_id == streamer.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.status = ClipStatus.REJECTED
    clip.rejected_at = datetime.utcnow()
    clip.rejection_reason = reason
    await db.commit()
    return {"ok": True}


@router.get("/{clip_id}/download")
async def download_clip(
    clip_id: str,
    token: str = Query(...),
    processed: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.streamer_id == streamer.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    path = clip.processed_clip_path if processed else clip.raw_clip_path
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="File not available yet")

    return FileResponse(
        path=path,
        media_type="video/mp4",
        filename=f"clip_{clip_id[:8]}.mp4",
    )


@router.patch("/{clip_id}/title")
async def update_clip_title(
    clip_id: str,
    token: str = Query(...),
    title: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    streamer = await get_streamer_from_token(token, db)
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.streamer_id == streamer.id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.ai_title = title
    await db.commit()
    return {"ok": True}


def _serialize_clip(clip: Clip) -> dict:
    return {
        "id": clip.id,
        "twitch_clip_id": clip.twitch_clip_id,
        "twitch_clip_url": clip.twitch_clip_url,
        "twitch_thumbnail_url": clip.twitch_thumbnail_url,
        "highlight_score": clip.highlight_score,
        "score_breakdown": clip.score_breakdown or {},
        "status": clip.status.value if clip.status else "pending",
        "transcript": clip.transcript,
        "chat_context": clip.chat_context or [],
        "ai_title": clip.ai_title,
        "ai_description": clip.ai_description,
        "ai_hashtags": clip.ai_hashtags or [],
        "duration_seconds": clip.duration_seconds,
        "detected_at": clip.detected_at.isoformat() if clip.detected_at else None,
        "approved_at": clip.approved_at.isoformat() if clip.approved_at else None,
        "rejected_at": clip.rejected_at.isoformat() if clip.rejected_at else None,
        "has_processed_video": bool(clip.processed_clip_path),
    }
