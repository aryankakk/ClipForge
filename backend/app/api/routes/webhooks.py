"""
Handles Twitch EventSub webhook callbacks.
Verifies signatures, routes events to appropriate handlers.
"""
import hashlib
import hmac
import logging
import time
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional

from app.core.config import get_settings
from app.services.stream_manager import (
    start_stream_session,
    stop_stream_session,
    inject_viewer_event,
)
from app.services.highlight_scorer import score_for_event

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Track processed message IDs to prevent duplicates
_processed_ids: set = set()
MAX_PROCESSED_IDS = 10000


def _verify_signature(
    body: bytes,
    message_id: str,
    timestamp: str,
    signature: str,
) -> bool:
    """Verify Twitch EventSub HMAC signature."""
    hmac_message = message_id + timestamp + body.decode("utf-8")
    expected = "sha256=" + hmac.new(
        settings.TWITCH_WEBHOOK_SECRET.encode("utf-8"),
        hmac_message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/twitch")
async def twitch_webhook(
    request: Request,
    twitch_eventsub_message_id: Optional[str] = Header(None),
    twitch_eventsub_message_timestamp: Optional[str] = Header(None),
    twitch_eventsub_message_signature: Optional[str] = Header(None),
    twitch_eventsub_message_type: Optional[str] = Header(None),
    twitch_eventsub_subscription_type: Optional[str] = Header(None),
):
    body = await request.body()

    # Verify signature
    if not all([
        twitch_eventsub_message_id,
        twitch_eventsub_message_timestamp,
        twitch_eventsub_message_signature,
    ]):
        raise HTTPException(status_code=400, detail="Missing signature headers")

    if not _verify_signature(
        body,
        twitch_eventsub_message_id,
        twitch_eventsub_message_timestamp,
        twitch_eventsub_message_signature,
    ):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Deduplicate
    if twitch_eventsub_message_id in _processed_ids:
        return {"ok": True}
    _processed_ids.add(twitch_eventsub_message_id)
    if len(_processed_ids) > MAX_PROCESSED_IDS:
        _processed_ids.clear()

    data = await request.json()

    # Handle webhook verification challenge
    if twitch_eventsub_message_type == "webhook_callback_verification":
        challenge = data.get("challenge")
        if not challenge:
            raise HTTPException(status_code=400, detail="No challenge")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content=challenge)

    # Route the event
    if twitch_eventsub_message_type == "notification":
        event_type = twitch_eventsub_subscription_type
        event = data.get("event", {})
        await _handle_event(event_type, event)

    return {"ok": True}


async def _handle_event(event_type: str, event: dict):
    logger.info(f"EventSub event: {event_type} | {event}")

    if event_type == "stream.online":
        broadcaster_id = event.get("broadcaster_user_id")
        if broadcaster_id:
            await start_stream_session(broadcaster_id)

    elif event_type == "stream.offline":
        broadcaster_id = event.get("broadcaster_user_id")
        if broadcaster_id:
            await stop_stream_session(broadcaster_id)

    elif event_type in (
        "channel.subscribe",
        "channel.subscription.message",
        "channel.subscription.gift",
        "channel.cheer",
        "channel.raid",
        "channel.channel_points_custom_reward_redemption.add",
    ):
        # Determine broadcaster_id
        broadcaster_id = (
            event.get("broadcaster_user_id")
            or event.get("to_broadcaster_user_id")
        )
        if broadcaster_id:
            score = score_for_event(event_type, event)
            if score > 0:
                await inject_viewer_event(broadcaster_id, event_type, score, event)
