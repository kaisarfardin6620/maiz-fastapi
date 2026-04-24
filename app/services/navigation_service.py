from datetime import datetime, timezone
from app.database import get_db
from app.services.ai_service import chat_completion
from app.services.maps_service import get_google_directions
from app.utils.object_id import str_to_objectid


def _now():
    return datetime.now(timezone.utc)


async def start_navigation(user_id: str, origin_id: str, destination_id: str,
                            venue_id: str = None, input_source: str = "text",
                            voice_enabled: bool = True) -> dict:
    db = get_db()

    user_obj_id = str_to_objectid(user_id)
    origin_obj_id = str_to_objectid(origin_id)
    destination_obj_id = str_to_objectid(destination_id)
    venue_obj_id = str_to_objectid(venue_id) if venue_id else None

    origin = await db["locations"].find_one({"_id": origin_obj_id})
    destination = await db["locations"].find_one({"_id": destination_obj_id})

    origin_label = origin.get("label", "your location") if origin else "your location"
    dest_label = destination.get("label", "destination") if destination else "destination"

    route_data = None

    origin_maps = (origin or {}).get("googleMaps") or {}
    dest_maps = (destination or {}).get("googleMaps") or {}
    origin_lat, origin_lng = origin_maps.get("lat"), origin_maps.get("lng")
    dest_lat, dest_lng = dest_maps.get("lat"), dest_maps.get("lng")

    if all(v is not None for v in [origin_lat, origin_lng, dest_lat, dest_lng]):
        try:
            route_data = await get_google_directions(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                destination_lat=dest_lat,
                destination_lng=dest_lng,
                mode="walking",
            )
        except Exception:
            route_data = None

    if not route_data:
        prompt = f"""
Generate indoor navigation steps from "{origin_label}" to "{dest_label}".
Return JSON only:
{{
  "steps": [
    {{
      "stepIndex": 0,
      "instructionText": "Walk straight past the main entrance",
      "maneuver": "straight",
      "landmarkName": "Main Entrance Sign",
      "floor": 1,
      "estimatedSteps": 20
    }}
  ],
  "destinationLabel": "{dest_label}"
}}
"""
        import json

        response = await chat_completion(
            [{"role": "user", "content": prompt}], stream=False
        )
        raw = response.choices[0].message.content
        try:
            route_data = json.loads(raw)
        except Exception:
            route_data = {"steps": [], "destinationLabel": dest_label, "googleMapsRoute": None}

    steps = route_data.get("steps", [])

    result = await db["navigationsessions"].insert_one({
        "user": user_obj_id,
        "venue": venue_obj_id,
        "inputSource": input_source,
        "origin": origin_obj_id,
        "destination": destination_obj_id,
        "destinationLabel": route_data.get("destinationLabel", dest_label),
        "steps": steps,
        "googleMapsRoute": route_data.get("googleMapsRoute"),
        "currentStepIndex": 0,
        "totalSteps": len(steps),
        "status": "active",
        "voiceGuidanceEnabled": voice_enabled,
        "indoorContext": {
            "currentFloor": steps[0].get("floor") if steps else None,
            "needsRecheckPhoto": False,
        },
        "correctionCount": 0,
        "recheckPhotoCount": 0,
        "startedAt": _now(),
        "isDeleted": False,
        "createdAt": _now(),
        "updatedAt": _now(),
    })

    session = await db["navigationsessions"].find_one({"_id": result.inserted_id})
    return session


async def advance_step(nav_session_id: str) -> dict:
    db = get_db()
    nav_obj_id = str_to_objectid(nav_session_id)
    session = await db["navigationsessions"].find_one({"_id": nav_obj_id})
    if not session:
        return None

    current = session.get("currentStepIndex", 0)
    total = session.get("totalSteps", 0)
    new_index = current + 1
    status = "completed" if new_index >= total else "active"

    await db["navigationsessions"].update_one(
        {"_id": nav_obj_id},
        {"$set": {
            "currentStepIndex": new_index,
            "status": status,
            "completedAt": _now() if status == "completed" else None,
            "updatedAt": _now(),
        }},
    )
    return await db["navigationsessions"].find_one({"_id": nav_obj_id})


async def handle_recheck(nav_session_id: str, image_analysis: dict) -> str:
    db = get_db()
    nav_obj_id = str_to_objectid(nav_session_id)
    session = await db["navigationsessions"].find_one({"_id": nav_obj_id})
    if not session:
        return "Session not found"

    steps = session.get("steps", [])
    current_step = steps[session.get("currentStepIndex", 0)] if steps else {}

    prompt = f"""
The user is lost during indoor navigation.
Current step instruction: "{current_step.get('instructionText', 'unknown')}"
Photo analysis: {image_analysis}
Give a short correction instruction to get them back on track.
"""
    response = await chat_completion(
        [{"role": "user", "content": prompt}], stream=False
    )
    correction = response.choices[0].message.content

    await db["navigationsessions"].update_one(
        {"_id": nav_obj_id},
        {"$inc": {"recheckPhotoCount": 1, "correctionCount": 1},
         "$set": {"updatedAt": _now()}},
    )
    return correction