import uuid
import base64
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from datetime import datetime, timezone
from bson import ObjectId
from app.core.dependencies import get_current_user
from app.database import get_db
from app.services.ai_service import analyze_image
from app.utils.response import success_response, APIResponse
from app.models.media import MediaUploadResponse

router = APIRouter(prefix="/media", tags=["Media"])


@router.post("/upload", response_model=APIResponse[MediaUploadResponse])
async def upload_media(
    file: UploadFile = File(...),
    purpose: str = Form(...),
    venue_id: str = Form(None),
    user=Depends(get_current_user),
):
    db = get_db()
    user_id = str(user["_id"])

    content_type = file.content_type or ""
    ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'bin'
    safe_filename = f"{uuid.uuid4().hex}.{ext}"

    if "image" in content_type:
        media_type = "image"
    elif "audio" in content_type:
        media_type = "audio"
    elif "video" in content_type:
        media_type = "video"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_url = f"https://your-storage.com/{user_id}/{safe_filename}"

    ai_analysis = None
    if media_type == "image":
        try:
            file_bytes = await file.read()
            b64_data = base64.b64encode(file_bytes).decode('utf-8')
            base64_url = f"data:{content_type};base64,{b64_data}"
            
            ai_analysis = await analyze_image(base64_url, context=purpose)
            ai_analysis["analysedAt"] = datetime.now(timezone.utc)
        except Exception as e:
            ai_analysis = None

    result = await db["mediaassets"].insert_one({
        "user": ObjectId(user_id),
        "mediaType": media_type,
        "purpose": purpose,
        "url": file_url,
        "mimeType": content_type,
        "sizeBytes": file.size,
        "aiAnalysis": ai_analysis,
        "linkedVenue": ObjectId(venue_id) if venue_id else None,
        "isDeleted": False,
        "createdAt": datetime.now(timezone.utc),
    })

    return success_response({
        "assetId": str(result.inserted_id),
        "url": file_url,
        "mediaType": media_type,
        "purpose": purpose,
        "aiAnalysis": ai_analysis,
    }, "Upload successful")