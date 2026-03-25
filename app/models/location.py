from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class LocationType(str, Enum):
    INDOOR = "indoor"
    OUTDOOR = "outdoor"

class GoogleMapsCoords(BaseModel):
    lat: float
    lng: float
    placeId: Optional[str] = None
    formattedAddress: Optional[str] = None

class IndoorPosition(BaseModel):
    x: Optional[float] = None
    y: Optional[float] = None

class LocationOut(BaseModel):
    id: str
    label: Optional[str] = None
    address: Optional[str] = None
    locationType: LocationType = LocationType.INDOOR
    floor: Optional[int] = None
    isFavorite: bool = False
    venueId: Optional[str] = None
    zoneId: Optional[str] = None
    indoorPosition: Optional[IndoorPosition] = None
    googleMaps: Optional[GoogleMapsCoords] = None
    visitedAt: Optional[datetime] = None

class LocationCreate(BaseModel):
    label: Optional[str] = None
    address: Optional[str] = None
    locationType: LocationType = LocationType.INDOOR
    floor: Optional[int] = None
    venueId: Optional[str] = None
    zoneId: Optional[str] = None
    indoorPosition: Optional[IndoorPosition] = None
    googleMaps: Optional[GoogleMapsCoords] = None
    isFavorite: bool = False