from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user
from app.models.navigation import NavigationStart, NavigationSessionOut
from app.services.navigation_service import start_navigation, advance_step, handle_recheck
from app.services.ai_service import analyze_image
from app.utils.object_id import doc_to_dict
from app.utils.response import success_response, APIResponse

router = APIRouter(prefix="/navigation", tags=["Navigation"])


@router.post("/start", response_model=APIResponse[NavigationSessionOut])
async def start_nav(body: NavigationStart, user=Depends(get_current_user)):
    user_id = str(user["_id"])
    try:
        session = await start_navigation(
            user_id=user_id,
            origin_id=body.originId,
            destination_id=body.destinationId,
            venue_id=body.venueId,
            input_source=body.inputSource,
            voice_enabled=body.voiceGuidanceEnabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return success_response(doc_to_dict(session), "Navigation started")


@router.post("/{nav_id}/next-step", response_model=APIResponse[NavigationSessionOut])
async def next_step(nav_id: str, user=Depends(get_current_user)):
    try:
        session = await advance_step(nav_id, user_id=str(user["_id"]))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not session:
        raise HTTPException(status_code=404, detail="Navigation session not found")
    return success_response(doc_to_dict(session))


@router.post("/{nav_id}/recheck")
async def recheck(nav_id: str, image_url: str, user=Depends(get_current_user)):
    analysis = await analyze_image(image_url, context="recheck photo")
    try:
        correction = await handle_recheck(nav_id, analysis, user_id=str(user["_id"]))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return success_response({"correction": correction, "analysis": analysis})