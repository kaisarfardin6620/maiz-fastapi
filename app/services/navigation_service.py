from datetime import datetime, timezone
from bson import ObjectId
from app.database import get_db
from app.services.ai_service import chat_completion


def _now():
    return datetime.now(timezone.utc)


async def start_navigation(user_id: str, origin_id: str, destination_id: str,
                            venue_id: str = None, input_source: str = "text",
                            voice_enabled: bool = True) -> dict:
    db = get_db()

    origin = await db["locations"].find_one({"_id": ObjectId(origin_id)})
    destination = await db["locations"].find_one({"_id": ObjectId(destination_id)})

    origin_label = origin.get("label", "your location") if origin else "your location"
    dest_label = destination.get("label", "destination") if destination else "destination"

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
        route_data = {"steps": [], "destinationLabel": dest_label}

    steps = route_data.get("steps", [])

    result = await db["navigationsessions"].insert_one({
        "user": ObjectId(user_id),
        "venue": ObjectId(venue_id) if venue_id else None,
        "inputSource": input_source,
        "origin": ObjectId(origin_id),
        "destination": ObjectId(destination_id),
        "destinationLabel": route_data.get("destinationLabel", dest_label),
        "steps": steps,
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
    session = await db["navigationsessions"].find_one({"_id": ObjectId(nav_session_id)})
    if not session:
        return None

    current = session.get("currentStepIndex", 0)
    total = session.get("totalSteps", 0)
    new_index = current + 1
    status = "completed" if new_index >= total else "active"

    await db["navigationsessions"].update_one(
        {"_id": ObjectId(nav_session_id)},
        {"$set": {
            "currentStepIndex": new_index,
            "status": status,
            "completedAt": _now() if status == "completed" else None,
            "updatedAt": _now(),
        }},
    )
    return await db["navigationsessions"].find_one({"_id": ObjectId(nav_session_id)})


async def handle_recheck(nav_session_id: str, image_analysis: dict) -> str:
    db = get_db()
    session = await db["navigationsessions"].find_one({"_id": ObjectId(nav_session_id)})
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
        {"_id": ObjectId(nav_session_id)},
        {"$inc": {"recheckPhotoCount": 1, "correctionCount": 1},
         "$set": {"updatedAt": _now()}},
    )
    return correction