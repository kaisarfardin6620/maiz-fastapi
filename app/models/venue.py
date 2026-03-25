from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class VenueType(str, Enum):
    MALL = "mall"
    AIRPORT = "airport"
    SUPERMARKET = "supermarket"
    HOSPITAL = "hospital"
    OFFICE = "office"
    UNIVERSITY = "university"
    OTHER = "other"


class MappingStatus(str, Enum):
    UNMAPPED = "unmapped"
    PARTIAL = "partial"
    COMPLETE = "complete"


class ZoneType(str, Enum):
    STORE = "store"
    FOOD_COURT = "food_court"
    RESTROOM = "restroom"
    ENTRANCE = "entrance"
    EXIT = "exit"
    CORRIDOR = "corridor"
    ELEVATOR = "elevator"
    ESCALATOR = "escalator"
    PARKING = "parking"
    INFORMATION = "information"
    OTHER = "other"

class GoogleMapsInfo(BaseModel):
    placeId: Optional[str] = None
    mapsUrl: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class VenueOut(BaseModel):
    id: str
    name: str
    venueType: VenueType
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    totalFloors: int = 1
    mappingStatus: MappingStatus = MappingStatus.UNMAPPED
    coverImage: Optional[str] = None
    isVerified: bool = False
    googleMaps: Optional[GoogleMapsInfo] = None
    createdAt: Optional[datetime] = None

class VenueZoneOut(BaseModel):
    id: str
    venueId: str
    name: str
    floor: int = 0
    zoneType: ZoneType = ZoneType.OTHER
    description: Optional[str] = None


class VenueSearchResult(BaseModel):
    venues: List[VenueOut]
    total: int