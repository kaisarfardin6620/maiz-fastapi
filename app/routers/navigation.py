from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user
from app.models.navigation import NavigationStart, NavigationSessionOut
from app.services.navigation_service import start_navigation, advance_step, handle_recheck
from app.services.ai_service import analyze_image
from app.utils.object_id import doc_to_dict
from app.utils.response import success_response

router = APIRouter(prefix="/navigation", tags=["Navigation"])


@router.post("/start")
async def start_nav(body: NavigationStart, user=Depends(get_current_user)):
    user_id = str(user["_id"])
    session = await start_navigation(
        user_id=user_id,
        origin_id=body.originId,
        destination_id=body.destinationId,
        venue_id=body.venueId,
        input_source=body.inputSource,
        voice_enabled=body.voiceGuidanceEnabled,
    )
    return success_response(doc_to_dict(session), "Navigation started")


@router.post("/{nav_id}/next-step")
async def next_step(nav_id: str, user=Depends(get_current_user)):
    session = await advance_step(nav_id)
    if not session:
        raise HTTPException(status_code=404, detail="Navigation session not found")
    return success_response(doc_to_dict(session))


@router.post("/{nav_id}/recheck")
async def recheck(nav_id: str, image_url: str, user=Depends(get_current_user)):
    analysis = await analyze_image(image_url, context="recheck photo")
    correction = await handle_recheck(nav_id, analysis)
    return success_response({"correction": correction, "analysis": analysis})