"""
Stream Manager - lifecycle manager for monitoring services.
One StreamSession per active broadcaster. Starts/stops chat monitor and scorer.
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Streamer, Stream
from app.services.chat_monitor import ChatMonitor
from app.services.highlight_scorer import HighlightScorer
from app.services.clip_creator import create_clip_for_moment
from app.core.redis_client import set_stream_live, clear_stream_live
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Global registry of active stream sessions
_active_sessions: Dict[str, "StreamSession"] = {}


class StreamSession:
    def __init__(self, streamer: Streamer, stream: Stream):
        self.streamer = streamer
        self.stream = stream
        self.broadcaster_id = streamer.twitch_id

        self.chat_monitor = ChatMonitor(
            broadcaster_login=streamer.login,
            broadcaster_id=streamer.twitch_id,
            access_token=streamer.access_token,
        )
        self.scorer = HighlightScorer(
            broadcaster_id=streamer.twitch_id,
            on_clip_triggered=self._on_clip_triggered,
        )
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        logger.info(f"🟢 Starting stream session for {self.streamer.login}")
        await set_stream_live(self.broadcaster_id, {
            "streamer_id": self.streamer.id,
            "login": self.streamer.login,
            "stream_id": self.stream.id,
            "started_at": self.stream.started_at.isoformat() if self.stream.started_at else None,
        })

        self._tasks = [
            asyncio.create_task(self.chat_monitor.start(), name=f"chat:{self.broadcaster_id}"),
            asyncio.create_task(self.scorer.start(), name=f"scorer:{self.broadcaster_id}"),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def stop(self):
        logger.info(f"🔴 Stopping stream session for {self.streamer.login}")
        await self.chat_monitor.stop()
        await self.scorer.stop()
        for task in self._tasks:
            task.cancel()
        await clear_stream_live(self.broadcaster_id)

    async def inject_viewer_event(self, event_type: str, score: float, metadata: dict):
        await self.scorer.inject_score(score, event_type)
        logger.info(f"Viewer event: {event_type} +{score} for {self.streamer.login}")

    async def _on_clip_triggered(
        self, broadcaster_id: str, score: float, breakdown: dict
    ):
        """Called by HighlightScorer when threshold is exceeded."""
        async with AsyncSessionLocal() as db:
            chat_ctx = self.chat_monitor.get_recent_messages(20)
            await create_clip_for_moment(
                db=db,
                broadcaster_id=broadcaster_id,
                highlight_score=score,
                score_breakdown=breakdown,
                chat_context=chat_ctx,
            )


# ─── Session lifecycle ────────────────────────────────────────────────────────

async def start_stream_session(broadcaster_id: str) -> bool:
    if broadcaster_id in _active_sessions:
        logger.info(f"Session already active for {broadcaster_id}")
        return True

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Streamer).where(Streamer.twitch_id == broadcaster_id)
        )
        streamer = result.scalar_one_or_none()
        if not streamer:
            logger.error(f"Cannot start session: streamer {broadcaster_id} not found")
            return False

        # Create/update stream record
        stream = Stream(
            streamer_id=streamer.id,
            is_live=True,
            started_at=datetime.utcnow(),
        )
        db.add(stream)
        await db.commit()
        await db.refresh(stream)

        session = StreamSession(streamer=streamer, stream=stream)
        _active_sessions[broadcaster_id] = session
        asyncio.create_task(session.start(), name=f"session:{broadcaster_id}")
        return True


async def stop_stream_session(broadcaster_id: str) -> bool:
    session = _active_sessions.pop(broadcaster_id, None)
    if not session:
        return False

    await session.stop()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Stream)
            .where(Stream.streamer_id == session.streamer.id, Stream.is_live == True)
            .order_by(Stream.created_at.desc())
        )
        stream = result.scalar_one_or_none()
        if stream:
            stream.is_live = False
            stream.ended_at = datetime.utcnow()
            await db.commit()

    return True


async def get_active_session(broadcaster_id: str) -> Optional[StreamSession]:
    return _active_sessions.get(broadcaster_id)


def get_all_active_broadcaster_ids() -> list[str]:
    return list(_active_sessions.keys())


async def inject_viewer_event(broadcaster_id: str, event_type: str, score: float, metadata: dict):
    session = _active_sessions.get(broadcaster_id)
    if session:
        await session.inject_viewer_event(event_type, score, metadata)
