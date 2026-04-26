from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.venue import VenueOut, VenueZoneOut
from app.utils.object_id import doc_to_dict, docs_to_list, str_to_objectid
from app.utils.response import success_response, APIResponse

router = APIRouter(prefix="/venue", tags=["Venue"])


@router.get("/search", response_model=APIResponse[List[VenueOut]])
async def search_venues(
    q: str = Query(..., min_length=1),
    city: str = Query(None),
    venue_type: str = Query(None),
    user=Depends(get_current_user),
):
    db = get_db()
    query = {"isDeleted": {"$ne": True}}
    if q:
        query["$or"] =[
            {"name": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}},
        ]
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if venue_type:
        query["venueType"] = venue_type

    cursor = db["venues"].find(query).limit(20)
    venues = await cursor.to_list(length=20)
    return success_response(docs_to_list(venues))


@router.get("/{venue_id}", response_model=APIResponse[VenueOut])
async def get_venue(venue_id: str, user=Depends(get_current_user)):
    db = get_db()

    try:
        venue_obj_id = str_to_objectid(venue_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    venue = await db["venues"].find_one(
        {"_id": venue_obj_id, "isDeleted": {"$ne": True}}
    )
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")
    return success_response(doc_to_dict(venue))


@router.get("/{venue_id}/zones", response_model=APIResponse[List[VenueZoneOut]])
async def get_venue_zones(
    venue_id: str, 
    floor: int = Query(None),
    user=Depends(get_current_user)
):
    db = get_db()

    try:
        venue_obj_id = str_to_objectid(venue_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    query = {"venue": venue_obj_id, "isDeleted": {"$ne": True}}
    if floor is not None:
        query["floor"] = floor
    cursor = db["venuezones"].find(query)
    zones = await cursor.to_list(length=100)
    return success_response(docs_to_list(zones))