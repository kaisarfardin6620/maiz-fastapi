from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

from fastapi import HTTPException
from starlette.status import HTTP_401_UNAUTHORIZED

from app.database import get_db
from app.mcp.schemas import ToolDefinition, ToolSchema
from app.services.ai_service import analyze_image
from app.services.navigation_service import advance_step, handle_recheck, start_navigation
from app.utils.object_id import doc_to_dict, docs_to_list, str_to_objectid
from app.services.maps_service import geocode_address, get_google_directions


McpHandler = Callable[[dict, dict], Awaitable[dict]]


class McpToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, McpHandler] = {}

    def register(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: McpHandler,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            inputSchema=ToolSchema(**input_schema),
        )
        self._handlers[name] = handler

    def list_tools(self) -> list[dict]:
        return [tool.model_dump() for tool in self._tools.values()]

    def get_handler(self, name: str) -> McpHandler:
        handler = self._handlers.get(name)
        if handler is None:
            raise LookupError(f"Unknown tool: {name}")
        return handler


registry = McpToolRegistry()


async def _require_user(context: dict) -> dict:
    user = context.get("user")
    if not user:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


async def _search_venues(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    query = arguments["query"]
    city = arguments.get("city")
    venue_type = arguments.get("venueType")

    db = get_db()
    filters: dict[str, Any] = {"isDeleted": {"$ne": True}}
    if query:
        filters["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"address": {"$regex": query, "$options": "i"}},
        ]
    if city:
        filters["city"] = {"$regex": city, "$options": "i"}
    if venue_type:
        filters["venueType"] = venue_type

    venues = await db["venues"].find(filters).sort("createdAt", -1).to_list(length=20)
    return {"venues": docs_to_list(venues), "count": len(venues)}


async def _get_venue(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    venue_id = str_to_objectid(arguments["venueId"])

    db = get_db()
    venue = await db["venues"].find_one({"_id": venue_id, "isDeleted": {"$ne": True}})
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {"venue": doc_to_dict(venue)}


async def _get_venue_zones(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    venue_id = str_to_objectid(arguments["venueId"])
    floor = arguments.get("floor")

    db = get_db()
    query: dict[str, Any] = {"venue": venue_id, "isDeleted": {"$ne": True}}
    if floor is not None:
        query["floor"] = floor

    zones = await db["venuezones"].find(query).sort("floor", 1).to_list(length=100)
    return {"zones": docs_to_list(zones), "count": len(zones)}


async def _get_search_history(arguments: dict, context: dict) -> dict:
    user = await _require_user(context)
    db = get_db()
    user_id = str_to_objectid(str(user["_id"]))
    limit = int(arguments.get("limit", 20))
    limit = max(1, min(limit, 100))

    cursor = db["searchhistories"].find({"user": user_id, "isDeleted": {"$ne": True}})
    items = await cursor.sort("searchedAt", -1).limit(limit).to_list(length=limit)
    return {"items": docs_to_list(items), "count": len(items)}


async def _start_navigation(arguments: dict, context: dict) -> dict:
    user = await _require_user(context)
    session = await start_navigation(
        user_id=str(user["_id"]),
        origin_id=arguments["originId"],
        destination_id=arguments["destinationId"],
        venue_id=arguments.get("venueId"),
        input_source=arguments.get("inputSource", "chat"),
        voice_enabled=arguments.get("voiceGuidanceEnabled", True),
    )
    return {"session": doc_to_dict(session)}


async def _advance_navigation_step(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    session = await advance_step(arguments["navigationId"])
    if not session:
        raise HTTPException(status_code=404, detail="Navigation session not found")
    return {"session": doc_to_dict(session)}


async def _get_navigation_session(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    navigation_id = str_to_objectid(arguments["navigationId"])

    db = get_db()
    session = await db["navigationsessions"].find_one(
        {"_id": navigation_id, "isDeleted": {"$ne": True}}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Navigation session not found")

    return {"session": doc_to_dict(session)}


async def _recheck_navigation(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    analysis = await analyze_image(arguments["imageUrl"], context=arguments.get("context", "recheck photo"))
    correction = await handle_recheck(arguments["navigationId"], analysis)
    return {"analysis": analysis, "correction": correction}


async def _route_to_location(arguments: dict, context: dict) -> dict:
    await _require_user(context)
    origin_id = arguments["originId"]
    query = arguments["query"]

    db = get_db()
    origin = await db["locations"].find_one({"_id": str_to_objectid(origin_id), "isDeleted": {"$ne": True}})
    if not origin:
        raise HTTPException(status_code=404, detail="Origin location not found")

    origin_maps = (origin or {}).get("googleMaps") or {}
    origin_lat = origin_maps.get("lat")
    origin_lng = origin_maps.get("lng")

    exact_location = await db["locations"].find_one(
        {
            "isDeleted": {"$ne": True},
            "$or": [
                {"label": {"$regex": f"^{query}$", "$options": "i"}},
                {"address": {"$regex": query, "$options": "i"}},
            ],
        }
    )

    if exact_location:
        dest_maps = (exact_location or {}).get("googleMaps") or {}
        dest_lat = dest_maps.get("lat")
        dest_lng = dest_maps.get("lng")
        route = None
        if all(v is not None for v in [origin_lat, origin_lng, dest_lat, dest_lng]):
            route = await get_google_directions(origin_lat, origin_lng, dest_lat, dest_lng, mode="walking")

        return {
            "matchType": "location",
            "destination": doc_to_dict(exact_location),
            "route": route,
            "mapsUrl": route["googleMapsRoute"]["mapsUrl"] if route else None,
        }

    geocoded = await geocode_address(query)
    if not geocoded:
        raise HTTPException(status_code=404, detail="Unable to resolve destination")

    route = None
    if all(v is not None for v in [origin_lat, origin_lng, geocoded.get("lat"), geocoded.get("lng")]):
        route = await get_google_directions(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=geocoded["lat"],
            destination_lng=geocoded["lng"],
            mode="walking",
        )

    return {
        "matchType": "geocoded",
        "destination": geocoded,
        "route": route,
        "mapsUrl": route["googleMapsRoute"]["mapsUrl"] if route else geocoded.get("mapsUrl"),
    }


registry.register(
    name="search_venues",
    description="Search venues by name, address, or city.",
    input_schema={
        "properties": {
            "query": {"type": "string", "minLength": 1},
            "city": {"type": "string"},
            "venueType": {"type": "string"},
        },
        "required": ["query"],
    },
    handler=_search_venues,
)

registry.register(
    name="get_venue",
    description="Fetch a single venue by its MongoDB id.",
    input_schema={
        "properties": {"venueId": {"type": "string"}},
        "required": ["venueId"],
    },
    handler=_get_venue,
)

registry.register(
    name="get_venue_zones",
    description="List zones for a venue, optionally filtered by floor.",
    input_schema={
        "properties": {
            "venueId": {"type": "string"},
            "floor": {"type": "integer"},
        },
        "required": ["venueId"],
    },
    handler=_get_venue_zones,
)

registry.register(
    name="get_search_history",
    description="Return the authenticated user's recent search history.",
    input_schema={
        "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
    },
    handler=_get_search_history,
)

registry.register(
    name="start_navigation",
    description="Start an indoor navigation session between two saved locations.",
    input_schema={
        "properties": {
            "originId": {"type": "string"},
            "destinationId": {"type": "string"},
            "venueId": {"type": "string"},
            "inputSource": {"type": "string", "enum": ["voice", "photo", "text", "chat", "history"]},
            "voiceGuidanceEnabled": {"type": "boolean"},
        },
        "required": ["originId", "destinationId"],
    },
    handler=_start_navigation,
)

registry.register(
    name="advance_navigation_step",
    description="Advance an active navigation session to the next step.",
    input_schema={
        "properties": {"navigationId": {"type": "string"}},
        "required": ["navigationId"],
    },
    handler=_advance_navigation_step,
)

registry.register(
    name="get_navigation_session",
    description="Fetch a navigation session by id.",
    input_schema={
        "properties": {"navigationId": {"type": "string"}},
        "required": ["navigationId"],
    },
    handler=_get_navigation_session,
)

registry.register(
    name="recheck_navigation",
    description="Use a photo to re-check and correct the current navigation step.",
    input_schema={
        "properties": {
            "navigationId": {"type": "string"},
            "imageUrl": {"type": "string"},
            "context": {"type": "string"},
        },
        "required": ["navigationId", "imageUrl"],
    },
    handler=_recheck_navigation,
)

registry.register(
    name="route_to_location",
    description="Resolve a free-form destination query into an indoor location or Google Maps route.",
    input_schema={
        "properties": {
            "originId": {"type": "string"},
            "query": {"type": "string", "minLength": 1},
        },
        "required": ["originId", "query"],
    },
    handler=_route_to_location,
)
