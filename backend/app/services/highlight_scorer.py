"""
Highlight Scorer - aggregates all signal sources and computes a rolling highlight score.
Triggers clip creation when the score exceeds the configured threshold.
"""
import asyncio
import logging
import time
from typing import Optional, Callable, Awaitable
from app.core.config import get_settings
from app.core.redis_client import (
    get_score_events,
    clear_score_events,
    is_on_cooldown,
    set_clip_cooldown,
    add_score_event,
    publish,
    get_redis,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class HighlightScorer:
    """
    Runs a continuous scoring loop while a stream is live.
    Every SCORE_WINDOW_SECONDS, it aggregates all events from Redis,
    computes a score, and calls on_clip_triggered if the threshold is met.
    """

    def __init__(
        self,
        broadcaster_id: str,
        on_clip_triggered: Callable[[str, float, dict], Awaitable[None]],
    ):
        self.broadcaster_id = broadcaster_id
        self.on_clip_triggered = on_clip_triggered
        self._running = False
        self._last_scores: list[float] = []

    async def start(self):
        self._running = True
        logger.info(f"Highlight scorer started for {self.broadcaster_id}")
        while self._running:
            await asyncio.sleep(settings.SCORE_WINDOW_SECONDS)
            if self._running:
                await self._evaluate()

    async def stop(self):
        self._running = False

    async def inject_score(self, score: float, source: str):
        """Manually inject a score event (e.g. from EventSub: sub, donation, raid)."""
        await add_score_event(self.broadcaster_id, score, source)

    async def _evaluate(self):
        events = await get_score_events(self.broadcaster_id)
        if not events:
            return

        # Aggregate scores by source
        breakdown = {}
        total = 0.0
        for event in events:
            src = event.get("source", "unknown")
            val = event.get("score", 0.0)
            breakdown[src] = breakdown.get(src, 0.0) + val
            total += val

        # Publish current score to frontend via pub/sub
        await publish(f"stream:{self.broadcaster_id}:score", {
            "total": total,
            "breakdown": breakdown,
            "threshold": settings.CLIP_SCORE_THRESHOLD,
            "timestamp": time.time(),
        })

        logger.debug(f"Score for {self.broadcaster_id}: {total:.1f} (breakdown: {breakdown})")

        # Check if we should clip
        if total >= settings.CLIP_SCORE_THRESHOLD:
            on_cooldown = await is_on_cooldown(self.broadcaster_id)
            if not on_cooldown:
                logger.info(
                    f"🎬 Clip triggered for {self.broadcaster_id}! "
                    f"Score: {total:.1f} | Breakdown: {breakdown}"
                )
                await set_clip_cooldown(self.broadcaster_id, settings.COOLDOWN_SECONDS)
                await clear_score_events(self.broadcaster_id)
                await self.on_clip_triggered(self.broadcaster_id, total, breakdown)
            else:
                logger.info(f"Score threshold met but on cooldown for {self.broadcaster_id}")
        else:
            # Decay: clear events older than 2 windows to prevent stale accumulation
            await clear_score_events(self.broadcaster_id)


# ─── Viewer event score values ────────────────────────────────────────────────

EVENT_SCORES = {
    "sub": 25.0,
    "resub": 15.0,
    "gift_sub": 20.0,
    "gift_bomb": 40.0,
    "cheer_small": 10.0,   # < 100 bits
    "cheer_medium": 20.0,  # 100-999 bits
    "cheer_large": 35.0,   # 1000+ bits
    "raid": 30.0,
    "channel_points": 10.0,
}


def score_for_event(event_type: str, metadata: dict = None) -> float:
    """Return score contribution for a Twitch EventSub event."""
    if event_type == "channel.subscribe":
        return EVENT_SCORES["sub"]
    elif event_type == "channel.subscription.message":
        return EVENT_SCORES["resub"]
    elif event_type == "channel.subscription.gift":
        total = metadata.get("total", 1) if metadata else 1
        return EVENT_SCORES["gift_bomb"] if total >= 5 else EVENT_SCORES["gift_sub"]
    elif event_type == "channel.cheer":
        bits = metadata.get("bits", 0) if metadata else 0
        if bits >= 1000:
            return EVENT_SCORES["cheer_large"]
        elif bits >= 100:
            return EVENT_SCORES["cheer_medium"]
        return EVENT_SCORES["cheer_small"]
    elif event_type == "channel.raid":
        viewers = metadata.get("viewers", 0) if metadata else 0
        return min(50.0, EVENT_SCORES["raid"] + viewers * 0.01)
    elif event_type == "channel.channel_points_custom_reward_redemption.add":
        return EVENT_SCORES["channel_points"]
    return 0.0
