from datetime import datetime, timezone
from bson import ObjectId
from app.database import get_db
from app.services.ai_service import chat_completion, transcribe_audio, analyze_image


def _now():
    return datetime.now(timezone.utc)


async def get_or_create_session(user_id: str, venue_id: str = None) -> dict:
    db = get_db()
    session = await db["chatsessions"].find_one(
        {"user": ObjectId(user_id), "status": "active", "isDeleted": {"$ne": True}},
        sort=[("createdAt", -1)],
    )
    if not session:
        result = await db["chatsessions"].insert_one({
            "user": ObjectId(user_id),
            "venue": ObjectId(venue_id) if venue_id else None,
            "title": "New Chat",
            "messages": [],
            "status": "active",
            "isDeleted": False,
            "createdAt": _now(),
            "updatedAt": _now(),
        })
        session = await db["chatsessions"].find_one({"_id": result.inserted_id})
    return session


async def get_session_messages(session: dict) -> list:
    formatted = []
    for msg in session.get("messages", [])[-20:]:
        formatted.append({"role": msg["role"], "content": msg.get("text", "")})
    return formatted


async def save_message(session_id: ObjectId, role: str, text: str,
                       voice_transcript: str = None, attachments: list = None):
    db = get_db()
    message = {
        "_id": ObjectId(),
        "role": role,
        "text": text,
        "attachments": attachments or [],
        "voiceTranscript": voice_transcript,
        "createdAt": _now(),
    }
    await db["chatsessions"].update_one(
        {"_id": session_id},
        {"$push": {"messages": message}, "$set": {"updatedAt": _now()}},
    )
    return message


async def save_search_history(user_id: str, query: str, input_type: str,
                               venue_id: str = None, resolved_address: str = None):
    db = get_db()
    await db["searchhistories"].insert_one({
        "user": ObjectId(user_id),
        "venue": ObjectId(venue_id) if venue_id else None,
        "query": query,
        "resolvedAddress": resolved_address,
        "inputType": input_type,
        "searchedAt": _now(),
        "isDeleted": False,
    })


async def process_text_message(session: dict, text: str, user_id: str,
                                venue_id: str = None) -> tuple[str, any]:
    history = await get_session_messages(session)
    history.append({"role": "user", "content": text})
    stream = await chat_completion(history, stream=True)
    return stream


async def process_voice_message(audio_bytes: bytes) -> str:
    return await transcribe_audio(audio_bytes)


async def process_image_message(image_url: str, context: str = "") -> dict:
    return await analyze_image(image_url, context)