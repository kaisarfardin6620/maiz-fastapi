import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bson import ObjectId

from app.config import settings
from app.database import get_db


_HTML_TAG_RE = re.compile(r"<[^>]+>")
logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _extract_coordinates_from_doc(doc: dict | None) -> dict | None:
    if not doc:
        return None
    gm = (doc.get("googleMaps") or {}) if isinstance(doc, dict) else {}
    lat = gm.get("lat")
    lng = gm.get("lng")
    if lat is None or lng is None:
        return None
    return {"lat": lat, "lng": lng}


async def _find_location_by_query(query: str) -> dict | None:
    db = get_db()
    q = query.strip()
    if not q:
        return None

    exact = await db["locations"].find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"label": {"$regex": f"^{re.escape(q)}$", "$options": "i"}},
                {"address": {"$regex": f"^{re.escape(q)}$", "$options": "i"}},
            ],
        }
    )
    if exact:
        return exact

    return await db["locations"].find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"label": {"$regex": re.escape(q), "$options": "i"}},
                {"address": {"$regex": re.escape(q), "$options": "i"}},
            ],
        }
    )


async def _find_venue_by_query(query: str) -> dict | None:
    db = get_db()
    q = query.strip()
    if not q:
        return None

    exact = await db["venues"].find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"name": {"$regex": f"^{re.escape(q)}$", "$options": "i"}},
                {"address": {"$regex": f"^{re.escape(q)}$", "$options": "i"}},
            ],
        }
    )
    if exact:
        return exact

    return await db["venues"].find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"name": {"$regex": re.escape(q), "$options": "i"}},
                {"address": {"$regex": re.escape(q), "$options": "i"}},
            ],
        }
    )


async def _cache_geocoded_location(query: str, geocoded: dict) -> dict:
    db = get_db()
    place_id = geocoded.get("placeId")
    formatted = geocoded.get("formattedAddress") or geocoded.get("label")

    existing = None
    if place_id:
        existing = await db["locations"].find_one(
            {"isDeleted": {"$ne": True}, "googleMaps.placeId": place_id}
        )

    if not existing and formatted:
        existing = await db["locations"].find_one(
            {
                "isDeleted": {"$ne": True},
                "address": {"$regex": f"^{re.escape(formatted)}$", "$options": "i"},
            }
        )

    if existing:
        return existing

    result = await db["locations"].insert_one(
        {
            "label": geocoded.get("label") or query,
            "address": formatted or query,
            "locationType": "outdoor",
            "floor": None,
            "venue": None,
            "zone": None,
            "indoorPosition": None,
            "googleMaps": {
                "lat": geocoded.get("lat"),
                "lng": geocoded.get("lng"),
                "placeId": place_id,
                "formattedAddress": formatted,
            },
            "isFavorite": False,
            "visitedAt": None,
            "isDeleted": False,
            "createdAt": _now(),
            "updatedAt": _now(),
        }
    )
    return await db["locations"].find_one({"_id": result.inserted_id})


async def resolve_destination(query: str) -> Dict[str, Any] | None:
    q = (query or "").strip()
    if not q:
        return None

    location = await _find_location_by_query(q)
    if location:
        return {
            "matchType": "location",
            "resolutionLevel": "indoor" if (location.get("floor") is not None or location.get("zone") or location.get("venue")) else "venue",
            "routeMode": "indoor" if (location.get("floor") is not None or location.get("zone") or location.get("venue")) else "outdoor",
            "destination": location,
            "coordinates": _extract_coordinates_from_doc(location),
            "mapsUrl": None,
            "reason": None,
        }

    venue = await _find_venue_by_query(q)
    if venue:
        coords = _extract_coordinates_from_doc(venue)
        return {
            "matchType": "venue",
            "resolutionLevel": "venue",
            "routeMode": "outdoor",
            "destination": venue,
            "coordinates": coords,
            "mapsUrl": (venue.get("googleMaps") or {}).get("mapsUrl"),
            "reason": "No indoor unit/floor mapping was found for this destination.",
        }

    geocoded = await geocode_address(q)
    if not geocoded:
        return None

    cached_location = await _cache_geocoded_location(q, geocoded)
    coords = {
        "lat": geocoded.get("lat"),
        "lng": geocoded.get("lng"),
    }
    return {
        "matchType": "geocoded",
        "resolutionLevel": "venue",
        "routeMode": "outdoor",
        "destination": cached_location,
        "coordinates": coords,
        "mapsUrl": geocoded.get("mapsUrl"),
        "reason": "Pinned destination at venue/address level. Indoor map is unavailable.",
    }


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


async def get_google_directions(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    mode: str = "walking",
) -> Optional[Dict[str, Any]]:
    params = {
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{destination_lat},{destination_lng}",
        "mode": mode,
        "key": settings.GOOGLE_MAPS_API_KEY,
    }

    async with httpx.AsyncClient(timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            logger.exception("Google Directions request failed")
            return None

    if data.get("status") != "OK":
        return None

    routes: List[Dict[str, Any]] = data.get("routes", [])
    if not routes:
        return None

    route = routes[0]
    legs = route.get("legs", [])
    if not legs:
        return None

    leg = legs[0]
    steps_out = []
    for idx, step in enumerate(leg.get("steps", [])):
        steps_out.append(
            {
                "stepIndex": idx,
                "instructionText": _strip_html(step.get("html_instructions", "")),
                "maneuver": _to_maneuver(step.get("maneuver")),
                "estimatedSteps": None,
                "floor": None,
            }
        )

    return {
        "steps": steps_out,
        "googleMapsRoute": {
            "polyline": route.get("overview_polyline", {}).get("points"),
            "distanceMeters": leg.get("distance", {}).get("value"),
            "durationSeconds": leg.get("duration", {}).get("value"),
            "mapsUrl": (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={origin_lat},{origin_lng}"
                f"&destination={destination_lat},{destination_lng}"
                f"&travelmode={mode}"
            ),
        },
        "destinationLabel": leg.get("end_address"),
    }


async def geocode_address(query: str) -> Optional[Dict[str, Any]]:
    params = {
        "address": query,
        "key": settings.GOOGLE_MAPS_API_KEY,
    }

    async with httpx.AsyncClient(timeout=settings.GOOGLE_MAPS_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError:
            logger.exception("Google Geocoding request failed")
            return None

    if data.get("status") != "OK":
        return None

    results = data.get("results", [])
    if not results:
        return None

    result = results[0]
    location = result.get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        return None

    return {
        "label": result.get("formatted_address") or query,
        "formattedAddress": result.get("formatted_address"),
        "lat": lat,
        "lng": lng,
        "placeId": result.get("place_id"),
        "mapsUrl": (
            "https://www.google.com/maps/search/?api=1"
            f"&query={lat},{lng}"
        ),
    }


def _to_maneuver(google_maneuver: Optional[str]) -> str:
    if not google_maneuver:
        return "straight"

    maneuver = google_maneuver.lower()
    if "left" in maneuver:
        return "left"
    if "right" in maneuver:
        return "right"
    if "uturn" in maneuver or "u-turn" in maneuver:
        return "u_turn"
    if "arrive" in maneuver:
        return "arrive"
    if "depart" in maneuver:
        return "depart"
    return "straight"
