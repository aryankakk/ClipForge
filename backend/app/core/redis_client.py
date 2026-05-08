import redis.asyncio as redis
from app.core.config import get_settings
import json
from typing import Any, Optional

settings = get_settings()

_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = await redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ─── Pub/Sub helpers ─────────────────────────────────────────────────────────

async def publish(channel: str, data: dict):
    r = await get_redis()
    await r.publish(channel, json.dumps(data))


async def get_cached(key: str) -> Optional[Any]:
    r = await get_redis()
    val = await r.get(key)
    return json.loads(val) if val else None


async def set_cached(key: str, value: Any, ttl: int = 300):
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value))


async def delete_cached(key: str):
    r = await get_redis()
    await r.delete(key)


# ─── Stream-state helpers ─────────────────────────────────────────────────────

async def set_stream_live(broadcaster_id: str, stream_data: dict):
    await set_cached(f"stream:live:{broadcaster_id}", stream_data, ttl=86400)


async def get_stream_live(broadcaster_id: str) -> Optional[dict]:
    return await get_cached(f"stream:live:{broadcaster_id}")


async def clear_stream_live(broadcaster_id: str):
    await delete_cached(f"stream:live:{broadcaster_id}")


# ─── Score accumulator ────────────────────────────────────────────────────────

async def add_score_event(broadcaster_id: str, score: float, source: str):
    r = await get_redis()
    key = f"score:{broadcaster_id}"
    await r.lpush(key, json.dumps({"score": score, "source": source}))
    await r.ltrim(key, 0, 99)  # Keep last 100 events
    await r.expire(key, 300)


async def get_score_events(broadcaster_id: str) -> list:
    r = await get_redis()
    events = await r.lrange(f"score:{broadcaster_id}", 0, -1)
    return [json.loads(e) for e in events]


async def clear_score_events(broadcaster_id: str):
    r = await get_redis()
    await r.delete(f"score:{broadcaster_id}")


# ─── Cooldown tracker ─────────────────────────────────────────────────────────

async def set_clip_cooldown(broadcaster_id: str, seconds: int):
    r = await get_redis()
    await r.setex(f"cooldown:{broadcaster_id}", seconds, "1")


async def is_on_cooldown(broadcaster_id: str) -> bool:
    r = await get_redis()
    return await r.exists(f"cooldown:{broadcaster_id}") == 1
