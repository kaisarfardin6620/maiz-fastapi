import uuid
import base64
import os
import tempfile
import cv2
import boto3
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.concurrency import run_in_threadpool
from datetime import datetime, timezone
from bson import ObjectId
from app.core.dependencies import get_current_user
from app.database import get_db
from app.services.ai_service import analyze_image
from app.utils.response import success_response, APIResponse
from app.models.media import MediaUploadResponse
from app.config import settings

router = APIRouter(prefix="/media", tags=["Media"])

# Module-level singleton — created once at startup, reused across all requests
_s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
)


def _extract_frame_sync(file_bytes: bytes, ext: str) -> str | None:
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        cap = cv2.VideoCapture(tmp_path)
        success, frame = cap.read()
        cap.release()

        if success:
            _, buffer = cv2.imencode('.jpg', frame)
            return base64.b64encode(buffer.tobytes()).decode('utf-8')

    except Exception:
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    return None


def _upload_to_s3(file_data: bytes, filename: str, mime_type: str, user_id: str):
    _s3_client.put_object(
        Bucket=settings.AWS_BUCKET_NAME,
        Key=f"{user_id}/{filename}",
        Body=file_data,
        ContentType=mime_type,
    )


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    conversation_id: str = Form(None),
    user=Depends(get_current_user),
):
    db = get_db()
    user_id = str(user["_id"])

    content_type = file.content_type or ""
    ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'bin'
    safe_filename = f"{uuid.uuid4().hex}.{ext}"

    if "image" in content_type:
        media_type = "image"
    elif "video" in content_type:
        media_type = "video"
    elif "audio" in content_type:
        media_type = "audio"
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_bytes = await file.read()

    try:
        await run_in_threadpool(_upload_to_s3, file_bytes, safe_filename, content_type, user_id)
        file_url = f"https://{settings.AWS_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{user_id}/{safe_filename}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload media to S3: {str(e)}")

    ai_analysis = None
    user_text = ""
    input_type = "photo"

    if media_type == "image":
        try:
            b64_data = base64.b64encode(file_bytes).decode('utf-8')
            base64_url = f"data:{content_type};base64,{b64_data}"
            ai_analysis = await analyze_image(base64_url, context="")
            ai_analysis["analysedAt"] = datetime.now(timezone.utc)
            user_text = f"[Photo analyzed: {ai_analysis.get('detectedZone', 'unknown zone')}]"
        except Exception:
            ai_analysis = None

    elif media_type == "video":
        b64_data = await run_in_threadpool(_extract_frame_sync, file_bytes, ext)
        if b64_data:
            try:
                base64_url = f"data:image/jpeg;base64,{b64_data}"
                ai_analysis = await analyze_image(base64_url, context="")
                ai_analysis["analysedAt"] = datetime.now(timezone.utc)
                user_text = f"[Video frame analyzed: {ai_analysis.get('detectedZone', 'unknown zone')}]"
            except Exception:
                ai_analysis = None

    elif media_type == "audio":
        from app.services.chat_service import process_voice_message
        input_type = "voice"
        user_text = await process_voice_message(file_bytes)

    result = await db["mediaassets"].insert_one({
        "user": ObjectId(user_id),
        "mediaType": media_type,
        "url": file_url,
        "mimeType": content_type,
        "sizeBytes": file.size,
        "aiAnalysis": ai_analysis,
        "isDeleted": False,
        "createdAt": datetime.now(timezone.utc),
    })

    ai_response_text = None

    if conversation_id and user_text:
        from app.services.chat_service import get_session_by_id, save_message, process_text_message
        session = await get_session_by_id(user_id, conversation_id)
        if session:
            attachment_items = [{
                "mediaType": media_type,
                "url": file_url,
                "purpose": "chat",
            }]
            await save_message(
                session["_id"],
                "user",
                user_text,
                voice_transcript=user_text if input_type == "voice" else None,
                attachments=attachment_items,
            )

            stream, action_card = await process_text_message(session, user_text, user_id, venue_id=None)

            full_reply = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                full_reply += delta

            if full_reply:
                await save_message(
                    session["_id"],
                    "assistant",
                    full_reply,
                    action_card=action_card,
                )
                ai_response_text = full_reply

    return success_response({
        "assetId": str(result.inserted_id),
        "url": file_url,
        "mediaType": media_type,
        "aiAnalysis": ai_analysis,
        "aiResponse": ai_response_text,
    }, "Upload and analysis successful")