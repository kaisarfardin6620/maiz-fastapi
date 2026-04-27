from datetime import datetime, timezone
import heapq
from math import hypot
from bson import json_util
from app.database import get_db
from app.redis_client import redis_client
from app.services.ai_service import chat_completion
from app.services.maps_service import get_google_directions
from app.utils.object_id import str_to_objectid

def _now():
    return datetime.now(timezone.utc)

def _normalize_navigation_session(session: dict | None) -> dict | None:
    if not session:
        return None

    out = dict(session)
    if out.get("originId") is None and out.get("origin") is not None:
        out["originId"] = out.get("origin")
    if out.get("destinationId") is None and out.get("destination") is not None:
        out["destinationId"] = out.get("destination")
    if out.get("routeMode") is None:
        out["routeMode"] = "outdoor" if out.get("steps") else "fallback"
    return out

def _get_coordinates(doc: dict | None):
    gm = (doc or {}).get("googleMaps") or {}
    return gm.get("lat"), gm.get("lng")

def _get_indoor_xy(doc: dict | None):
    pos = (doc or {}).get("indoorPosition") or {}
    x = pos.get("x")
    y = pos.get("y")
    if x is None or y is None:
        return None
    return float(x), float(y)

async def _load_venue_graph(venue_obj_id):
    if not venue_obj_id:
        return None
        
    cache_key = f"venue_graph:{str(venue_obj_id)}"
    cached_graph = await redis_client.get(cache_key)
    
    if cached_graph:
        return json_util.loads(cached_graph)
        
    db = get_db()
    graph = await db["venuegraphs"].find_one({"venue": venue_obj_id, "isDeleted": {"$ne": True}})
    
    if graph:
        await redis_client.setex(cache_key, 86400, json_util.dumps(graph))
        
    return graph

def _pick_nearest_graph_node(nodes: list[dict], floor: int | None, point: tuple[float, float] | None):
    if not nodes or point is None:
        return None

    filtered =[n for n in nodes if floor is None or n.get("floor") == floor]
    if not filtered:
        filtered = nodes

    best = None
    best_dist = float("inf")
    px, py = point
    for node in filtered:
        nx, ny = node.get("x"), node.get("y")
        if nx is None or ny is None:
            continue
        d = hypot(float(nx) - px, float(ny) - py)
        if d < best_dist:
            best_dist = d
            best = node
    return best

def _build_indoor_route(graph: dict, origin: dict, destination: dict) -> dict | None:
    nodes = graph.get("nodes") or[]
    edges = graph.get("edges") or[]
    if not nodes or not edges:
        return None

    node_by_id = {str(n.get("id")): n for n in nodes if n.get("id") is not None}
    if not node_by_id:
        return None

    origin_node = _pick_nearest_graph_node(
        list(node_by_id.values()),
        origin.get("floor"),
        _get_indoor_xy(origin),
    )
    destination_node = _pick_nearest_graph_node(
        list(node_by_id.values()),
        destination.get("floor"),
        _get_indoor_xy(destination),
    )
    if not origin_node or not destination_node:
        return None

    origin_id = str(origin_node.get("id"))
    destination_id = str(destination_node.get("id"))
    adjacency: dict[str, list[tuple[str, float, dict]]] = {}
    for edge in edges:
        src = str(edge.get("from")) if edge.get("from") is not None else None
        dst = str(edge.get("to")) if edge.get("to") is not None else None
        if not src or not dst:
            continue
        weight = float(edge.get("weight") or edge.get("distance") or 1.0)
        adjacency.setdefault(src,[]).append((dst, weight, edge))
        if edge.get("bidirectional", True):
            adjacency.setdefault(dst, []).append((src, weight, edge))

    queue =[(0.0, origin_id)]
    dist = {origin_id: 0.0}
    prev: dict[str, tuple[str, dict]] = {}

    while queue:
        current_dist, current = heapq.heappop(queue)
        if current == destination_id:
            break
        if current_dist > dist.get(current, float("inf")):
            continue
        for nxt, weight, edge in adjacency.get(current,[]):
            candidate = current_dist + weight
            if candidate < dist.get(nxt, float("inf")):
                dist[nxt] = candidate
                prev[nxt] = (current, edge)
                heapq.heappush(queue, (candidate, nxt))

    if destination_id not in dist:
        return None

    path_nodes =[destination_id]
    path_edges =[]
    cursor = destination_id
    while cursor != origin_id:
        parent, edge = prev[cursor]
        path_edges.append((parent, cursor, edge))
        path_nodes.append(parent)
        cursor = parent
    path_nodes.reverse()
    path_edges.reverse()

    steps =[]
    for idx, (_, to_node_id, edge) in enumerate(path_edges):
        node = node_by_id.get(to_node_id) or {}
        instruction = edge.get("instruction") or f"Proceed to {node.get('label') or 'next waypoint'}."
        steps.append(
            {
                "stepIndex": idx,
                "instructionText": instruction,
                "maneuver": edge.get("maneuver") or "straight",
                "landmarkName": node.get("label"),
                "floor": node.get("floor"),
                "estimatedSteps": int(edge.get("estimatedSteps")) if edge.get("estimatedSteps") is not None else None,
            }
        )

    return {
        "steps": steps,
        "destinationLabel": destination.get("label") or destination.get("address") or "destination",
    }

async def start_navigation(user_id: str, origin_id: str, destination_id: str,
                            input_source: str = "text",
                            voice_enabled: bool = True) -> dict:
    db = get_db()

    user_obj_id = str_to_objectid(user_id)
    origin_obj_id = str_to_objectid(origin_id)
    destination_obj_id = str_to_objectid(destination_id)

    origin = await db["locations"].find_one({"_id": origin_obj_id, "isDeleted": {"$ne": True}})
    destination = await db["locations"].find_one({"_id": destination_obj_id, "isDeleted": {"$ne": True}})

    if not origin:
        raise ValueError("Origin location not found")
    if not destination:
        raise ValueError("Destination location not found")

    origin_label = origin.get("label", "your location") if origin else "your location"
    dest_label = destination.get("label", "destination") if destination else "destination"

    route_data = None
    route_mode = "fallback"
    fallback_reason = None

    origin_lat, origin_lng = _get_coordinates(origin)
    dest_lat, dest_lng = _get_coordinates(destination)

    shared_venue = (origin or {}).get("venue") and (origin or {}).get("venue") == (destination or {}).get("venue")
    venue_obj_id = (origin or {}).get("venue") if shared_venue else None
    
    indoor_graph = await _load_venue_graph(venue_obj_id)
    indoor_route = None
    if indoor_graph and _get_indoor_xy(origin) and _get_indoor_xy(destination):
        indoor_route = _build_indoor_route(indoor_graph, origin, destination)

    if indoor_route and indoor_route.get("steps"):
        route_data = {
            "steps": indoor_route.get("steps") or[],
            "googleMapsRoute": None,
            "destinationLabel": indoor_route.get("destinationLabel", dest_label),
        }
        route_mode = "indoor"

    if not route_data and all(v is not None for v in[origin_lat, origin_lng, dest_lat, dest_lng]):
        try:
            route_data = await get_google_directions(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                destination_lat=dest_lat,
                destination_lng=dest_lng,
                mode="walking",
            )
            if route_data:
                route_mode = "outdoor"
        except Exception:
            route_data = None

    if not route_data:
        fallback_reason = (
            f"Indoor route unavailable between '{origin_label}' and '{dest_label}'. "
            "Pinned destination at venue level."
        )
        route_data = {
            "steps":[],
            "googleMapsRoute": {
                "mapsUrl": (
                    f"https://www.google.com/maps/search/?api=1&query={dest_lat},{dest_lng}"
                    if dest_lat is not None and dest_lng is not None
                    else None
                )
            },
            "destinationLabel": dest_label,
        }

    steps = route_data.get("steps",[])
    status = "active" if steps else "pending"

    result = await db["navigationsessions"].insert_one({
        "user": user_obj_id,
        "venue": venue_obj_id,
        "inputSource": input_source,
        "origin": origin_obj_id,
        "originId": origin_obj_id,
        "destination": destination_obj_id,
        "destinationId": destination_obj_id,
        "destinationLabel": route_data.get("destinationLabel", dest_label),
        "routeMode": route_mode,
        "fallbackReason": fallback_reason,
        "steps": steps,
        "googleMapsRoute": route_data.get("googleMapsRoute"),
        "currentStepIndex": 0,
        "totalSteps": len(steps),
        "status": status,
        "voiceGuidanceEnabled": voice_enabled,
        "indoorContext": {
            "currentFloor": origin.get("floor"),
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
    return _normalize_navigation_session(session)

async def advance_step(nav_session_id: str, user_id: str | None = None) -> dict:
    db = get_db()
    nav_obj_id = str_to_objectid(nav_session_id)
    query = {"_id": nav_obj_id, "isDeleted": {"$ne": True}}
    if user_id:
        query["user"] = str_to_objectid(user_id)

    session = await db["navigationsessions"].find_one(query)
    if not session:
        return None

    current = session.get("currentStepIndex", 0)
    total = session.get("totalSteps", 0)
    if total <= 0:
        return _normalize_navigation_session(session)

    new_index = min(current + 1, total)
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
    updated = await db["navigationsessions"].find_one({"_id": nav_obj_id})
    return _normalize_navigation_session(updated)

async def handle_recheck(nav_session_id: str, image_analysis: dict, user_id: str | None = None) -> str:
    db = get_db()
    nav_obj_id = str_to_objectid(nav_session_id)
    query = {"_id": nav_obj_id, "isDeleted": {"$ne": True}}
    if user_id:
        query["user"] = str_to_objectid(user_id)

    session = await db["navigationsessions"].find_one(query)
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