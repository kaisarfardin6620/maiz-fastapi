from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class CardType(str, Enum):
    START_NAVIGATION = "start_navigation"
    DIRECTIONS = "directions"
    LOCATION_INFO = "location_info"
    PRODUCT_LOCATION = "product_location"
    RECHECK_REQUEST = "recheck_request"
    REQUEST_LOCATION = "request_location"


class Maneuver(str, Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    U_TURN = "u_turn"
    ARRIVE = "arrive"


class ActionCard(BaseModel):
    cardType: Optional[CardType] = None
    locationId: Optional[str] = None
    venueZoneId: Optional[str] = None
    address: Optional[str] = None
    label: Optional[str] = None
    ctaLabel: Optional[str] = None


class NavigationInstruction(BaseModel):
    instructionText: Optional[str] = None
    landmarkRef: Optional[str] = None
    maneuver: Optional[Maneuver] = None
    isCorrection: bool = False


class MessageAttachment(BaseModel):
    assetId: Optional[str] = None
    mediaType: Optional[str] = None
    url: Optional[str] = None
    purpose: Optional[str] = None


class ChatSessionOut(BaseModel):
    id: str
    title: str = "New Chat"
    status: str = "active"
    venueId: Optional[str] = None
    messages: List[dict] = Field(default_factory=list)
    createdAt: Optional[datetime] = None