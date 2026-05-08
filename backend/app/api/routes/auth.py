import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import Streamer
from app.services.twitch_api import (
    build_oauth_url,
    exchange_code,
    TwitchAPIClient,
    register_eventsub,
)
from app.core.redis_client import set_cached, get_cached

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
async def twitch_login():
    """Redirect user to Twitch OAuth."""
    state = secrets.token_urlsafe(16)
    await set_cached(f"oauth:state:{state}", {"valid": True}, ttl=300)
    url = build_oauth_url(state)
    return {"url": url}


@router.get("/callback")
async def twitch_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Twitch OAuth callback."""
    # Verify state
    cached = await get_cached(f"oauth:state:{state}")
    if not cached:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Exchange code for tokens
    try:
        token_data = await exchange_code(code)
    except Exception as e:
        logger.error(f"Token exchange failed: {e}")
        raise HTTPException(status_code=400, detail="Token exchange failed")

    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    # Fetch user info
    client = TwitchAPIClient(access_token=access_token)
    try:
        user = await client.get_user()
    except Exception as e:
        logger.error(f"Failed to fetch Twitch user: {e}")
        raise HTTPException(status_code=400, detail="Failed to fetch user info")

    # Upsert streamer
    result = await db.execute(
        select(Streamer).where(Streamer.twitch_id == user["id"])
    )
    streamer = result.scalar_one_or_none()

    if streamer:
        streamer.access_token = access_token
        streamer.refresh_token = refresh_token
        streamer.display_name = user["display_name"]
        streamer.login = user["login"]
        streamer.profile_image_url = user.get("profile_image_url")
        streamer.updated_at = datetime.utcnow()
    else:
        streamer = Streamer(
            twitch_id=user["id"],
            login=user["login"],
            display_name=user["display_name"],
            profile_image_url=user.get("profile_image_url"),
            access_token=access_token,
            refresh_token=refresh_token,
            broadcaster_type=user.get("broadcaster_type", ""),
        )
        db.add(streamer)

    await db.commit()
    await db.refresh(streamer)

    # Register EventSub subscriptions
    try:
        await register_eventsub(user["id"])
    except Exception as e:
        logger.warning(f"EventSub registration failed (non-fatal): {e}")

    # Store session token in cache
    session_token = secrets.token_urlsafe(32)
    await set_cached(f"session:{session_token}", {
        "streamer_id": streamer.id,
        "twitch_id": streamer.twitch_id,
        "login": streamer.login,
        "display_name": streamer.display_name,
        "profile_image_url": streamer.profile_image_url,
    }, ttl=86400 * 7)

    # Redirect to frontend with session token
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/auth/callback?token={session_token}&login={streamer.login}"
    )


@router.get("/me")
async def get_me(token: str = Query(...)):
    """Get current user info from session token."""
    data = await get_cached(f"session:{token}")
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return data


@router.post("/logout")
async def logout(token: str = Query(...)):
    from app.core.redis_client import delete_cached
    await delete_cached(f"session:{token}")
    return {"ok": True}
