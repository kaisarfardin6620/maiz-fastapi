import re
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


_HTML_TAG_RE = re.compile(r"<[^>]+>")
logger = logging.getLogger(__name__)


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
