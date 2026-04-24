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

class ChatMessageOut(BaseModel):
    id: str
    role: MessageRole
    text: Optional[str] = None
    attachments: List[MessageAttachment] = Field(default_factory=list)
    actionCard: Optional[ActionCard] = None
    navigationInstruction: Optional[NavigationInstruction] = None
    voiceTranscript: Optional[str] = None
    createdAt: datetime

class WSIncoming(BaseModel):
    text: Optional[str] = None
    audio: Optional[str] = None
    imageUrl: Optional[str] = None
    venueId: Optional[str] = None

class WSOutgoing(BaseModel):
    role: MessageRole = MessageRole.ASSISTANT
    text: Optional[str] = None
    actionCard: Optional[ActionCard] = None
    navigationInstruction: Optional[NavigationInstruction] = None
    isStreaming: bool = False
    isDone: bool = False

class ChatSessionOut(BaseModel):
    id: str
    title: str = "New Chat"
    status: str = "active"
    venueId: Optional[str] = None
    messages: List[ChatMessageOut] = Field(default_factory=list)
    createdAt: Optional[datetime] = None