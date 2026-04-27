from datetime import datetime, timezone
import re
from typing import Optional, Tuple, Any
from bson import ObjectId
from app.database import get_db
from app.mcp.registry import registry
from app.services.ai_service import chat_completion, transcribe_audio, analyze_image


def _now():
    return datetime.now(timezone.utc)


GPS_KEYWORDS = {
    "gps", "coordinate", "coordinates", "latitude", "longitude", "lat", "lng", "map", "pin"
}
LOCATION_KEYWORDS = {
    "where", "location", "locate", "find", "route", "direction", "directions", "address", "near"
}


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(tok) > 2}


def _mentions_gps(text: str) -> bool:
    lower = (text or "").lower()
    return any(k in lower for k in GPS_KEYWORDS)


def _looks_like_location_query(text: str) -> bool:
    lower = (text or "").lower()
    return any(k in lower for k in GPS_KEYWORDS.union(LOCATION_KEYWORDS))


def _safe_object_id(value: str | None):
    if not value:
        return None
    try:
        return ObjectId(value)
    except Exception:
        return None


def _generate_title_from_input(user_text: str, input_type: str = "text") -> str:
    text = (user_text or "").strip()
    if not text:
        return "New Chat"

    if input_type == "photo" and not text.lower().startswith("photo"):
        text = f"Photo: {text}"
    elif input_type == "voice" and not text.lower().startswith("voice"):
        text = f"Voice: {text}"

    text = re.sub(r"\s+", " ", text)
    if len(text) > 60:
        text = text[:57].rstrip() + "..."
    return text


async def _build_gps_runtime_context(user_text: str, venue_id: str | None) -> str | None:
    if not _mentions_gps(user_text):
        return None

    text_tokens = _tokenize(user_text)
    if not text_tokens:
        return None

    regex_pattern = "|".join(re.escape(t) for t in text_tokens)

    db = get_db()
    query = {
        "isDeleted": {"$ne": True},
        "googleMaps.lat": {"$exists": True, "$ne": None},
        "googleMaps.lng": {"$exists": True, "$ne": None},
        "$or":[
            {"label": {"$regex": regex_pattern, "$options": "i"}},
            {"address": {"$regex": regex_pattern, "$options": "i"}},
        ]
    }

    venue_obj_id = _safe_object_id(venue_id)
    if venue_obj_id:
        query["venue"] = venue_obj_id

    top_candidates = await db["locations"].find(
        query,
        {"label": 1, "address": 1, "googleMaps": 1},
    ).limit(5).to_list(length=5)

    if not top_candidates:
        return None

    lines =[]
    for doc in top_candidates:
        gm = doc.get("googleMaps") or {}
        lat = gm.get("lat")
        lng = gm.get("lng")
        if lat is None or lng is None:
            continue
        label = doc.get("label") or doc.get("address") or "Unknown place"
        lines.append(f"- {label}: lat={lat}, lng={lng}")

    if not lines:
        return None

    return (
        "GPS context from saved locations in database:\n"
        + "\n".join(lines)
        + "\nIf the user asks for GPS, provide the most relevant coordinates from this list."
    )


async def _build_mcp_location_runtime_context(user_text: str, user_id: str) -> Tuple[str | None, dict | None]:
    if not _looks_like_location_query(user_text):
        return None, None

    try:
        handler = registry.get_handler("route_to_location")
    except Exception:
        return None, None

    try:
        result = await handler(
            {"query": user_text},
            {"user": {"_id": ObjectId(user_id)}},
        )
    except Exception:
        return None, None

    destination = result.get("destination") or {}
    coordinates = result.get("coordinates") or {}
    route = result.get("route") or {}
    route_mode = result.get("routeMode") or "fallback"
    resolution_level = result.get("resolutionLevel") or "venue"
    fallback_reason = result.get("reason")
    route_meta = (route or {}).get("googleMapsRoute") or {}
    maps_url = result.get("mapsUrl") or route_meta.get("mapsUrl")

    lat = coordinates.get("lat")
    lng = coordinates.get("lng")

    if lat is None or lng is None:
        gm = destination.get("googleMaps") or {}
        lat = gm.get("lat")
        lng = gm.get("lng")

    if lat is None or lng is None:
        return None, None

    label = destination.get("label") or destination.get("formattedAddress") or destination.get("address") or user_text
    dest_id = destination.get("_id") or destination.get("id")

    if route_mode == "indoor" and dest_id:
        action_card = {
            "cardType": "start_navigation",
            "locationId": str(dest_id),
            "label": label,
            "ctaLabel": "Start Indoor Navigation",
        }
    elif route_mode == "outdoor":
        action_card = {
            "cardType": "directions",
            "locationId": str(dest_id) if dest_id else None,
            "label": label,
            "ctaLabel": "Open Route",
        }
    else:
        action_card = {
            "cardType": "location_info",
            "locationId": str(dest_id) if dest_id else None,
            "label": label,
            "ctaLabel": "Open in Maps" if maps_url else "View Location",
        }

    context_lines =[
        "Location resolved successfully via MCP tool route_to_location:",
        f"- label: {label}",
        f"- resolutionLevel: {resolution_level}",
        f"- routeMode: {route_mode}",
        f"- latitude: {lat}",
        f"- longitude: {lng}",
    ]
    if maps_url:
        context_lines.append(f"- mapsUrl: {maps_url}")
    if fallback_reason:
        context_lines.append(f"- fallbackReason: {fallback_reason}")

    if route_mode == "fallback":
        context_lines.append(
            "IMPORTANT: Indoor step-by-step navigation is unavailable for this destination. "
            "Politely explain that the destination is pinned at venue/address level and ask whether the user wants outdoor route guidance."
        )
    else:
        context_lines.append(
            "IMPORTANT: The system has automatically generated a UI action card for this location. "
            "Do not output raw JSON or coordinates. Keep your response brief and user-friendly."
        )
    
    return "\n".join(context_lines), action_card


async def create_session(user_id: str, venue_id: str = None, title: str = "New Chat") -> dict:
    db = get_db()
    result = await db["chatsessions"].insert_one({
        "user": ObjectId(user_id),
        "venue": ObjectId(venue_id) if venue_id else None,
        "title": title or "New Chat",
        "messages":[],
        "status": "active",
        "isDeleted": False,
        "createdAt": _now(),
        "updatedAt": _now(),
    })
    return await db["chatsessions"].find_one({"_id": result.inserted_id})


async def get_session_by_id(user_id: str, conversation_id: str) -> Optional[dict]:
    db = get_db()
    session_obj_id = _safe_object_id(conversation_id)
    if not session_obj_id:
        return None
    return await db["chatsessions"].find_one({
        "_id": session_obj_id,
        "user": ObjectId(user_id),
        "isDeleted": {"$ne": True},
    })


async def get_or_create_session(
    user_id: str,
    venue_id: str = None,
    conversation_id: str = None,
    force_new: bool = False,
) -> dict:
    if force_new:
        return await create_session(user_id, venue_id)

    if conversation_id:
        existing = await get_session_by_id(user_id, conversation_id)
        if existing:
            return existing

    db = get_db()
    session = await db["chatsessions"].find_one(
        {"user": ObjectId(user_id), "status": "active", "isDeleted": {"$ne": True}},
        sort=[("createdAt", -1)],
    )
    if not session:
        session = await create_session(user_id, venue_id)
    return session


async def list_sessions(user_id: str, venue_id: str = None, limit: int = 50) -> list[dict]:
    db = get_db()
    query = {
        "user": ObjectId(user_id),
        "isDeleted": {"$ne": True},
    }
    if venue_id:
        venue_obj_id = _safe_object_id(venue_id)
        if venue_obj_id:
            query["venue"] = venue_obj_id

    docs = await db["chatsessions"].find(query).sort("updatedAt", -1).limit(max(1, min(limit, 200))).to_list(length=limit)
    return docs


async def update_session_title(user_id: str, conversation_id: str, title: str) -> Optional[dict]:
    session_obj_id = _safe_object_id(conversation_id)
    if not session_obj_id:
        return None

    db = get_db()
    clean_title = re.sub(r"\s+", " ", (title or "").strip())[:80] or "New Chat"
    await db["chatsessions"].update_one(
        {
            "_id": session_obj_id,
            "user": ObjectId(user_id),
            "isDeleted": {"$ne": True},
        },
        {"$set": {"title": clean_title, "updatedAt": _now()}},
    )
    return await db["chatsessions"].find_one({"_id": session_obj_id})


async def auto_title_session_if_needed(session: dict, user_text: str, input_type: str = "text") -> dict:
    current_title = (session or {}).get("title") or "New Chat"
    if current_title != "New Chat":
        return session

    if (session or {}).get("messages"):
        return session

    generated_title = _generate_title_from_input(user_text, input_type)
    return await update_session_title(str(session["user"]), str(session["_id"]), generated_title) or session


async def delete_session(user_id: str, conversation_id: str) -> bool:
    session_obj_id = _safe_object_id(conversation_id)
    if not session_obj_id:
        return False

    db = get_db()
    result = await db["chatsessions"].update_one(
        {
            "_id": session_obj_id,
            "user": ObjectId(user_id),
            "isDeleted": {"$ne": True},
        },
        {
            "$set": {
                "isDeleted": True,
                "status": "deleted",
                "updatedAt": _now(),
            }
        },
    )
    return result.modified_count > 0


async def get_session_messages(session: dict) -> list:
    formatted =[]
    for msg in session.get("messages", [])[-50:]:
        formatted.append({"role": msg["role"], "content": msg.get("text", "")})
    return formatted


async def save_message(session_id: ObjectId, role: str, text: str,
                       voice_transcript: str = None, attachments: list = None,
                       action_card: dict = None):
    db = get_db()
    message = {
        "_id": ObjectId(),
        "role": role,
        "text": text,
        "attachments": attachments or[],
        "actionCard": action_card,
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
                                venue_id: str = None) -> Tuple[Any, dict | None]:
    db = get_db()
    user = await db["users"].find_one(
        {"_id": ObjectId(user_id), "isDeleted": {"$ne": True}},
        {"fullName": 1, "firstName": 1, "lastName": 1, "email": 1},
    )

    history = await get_session_messages(session)
    history.append({"role": "user", "content": text})

    context_parts =[]
    action_card = None
    
    mcp_context, mcp_action_card = await _build_mcp_location_runtime_context(text, user_id)
    if mcp_context:
        context_parts.append(mcp_context)
        action_card = mcp_action_card

    db_context = await _build_gps_runtime_context(text, venue_id)
    if db_context:
        context_parts.append(db_context)

    runtime_context = "\n\n".join(context_parts) if context_parts else None
    stream = await chat_completion(
        history,
        stream=True,
        user_context=user,
        runtime_context=runtime_context,
    )
    return stream, action_card


async def process_voice_message(audio_bytes: bytes) -> str:
    return await transcribe_audio(audio_bytes)


async def process_image_message(image_url: str, context: str = "") -> dict:
    return await analyze_image(image_url, context)