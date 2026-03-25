from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class InputSource(str, Enum):
    VOICE = "voice"
    PHOTO = "photo"
    TEXT = "text"
    CHAT = "chat"
    HISTORY = "history"

class NavStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Maneuver(str, Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"
    U_TURN = "u_turn"
    TAKE_ESCALATOR = "take_escalator"
    TAKE_ELEVATOR = "take_elevator"
    ARRIVE = "arrive"
    DEPART = "depart"

class GoogleMapsRoute(BaseModel):
    polyline: Optional[str] = None
    distanceMeters: Optional[int] = None
    durationSeconds: Optional[int] = None
    mapsUrl: Optional[str] = None

class RouteStepOut(BaseModel):
    stepIndex: int
    instructionText: str
    maneuver: Optional[Maneuver] = None
    landmarkRef: Optional[str] = None
    landmarkName: Optional[str] = None
    floor: Optional[int] = None
    estimatedSteps: Optional[int] = None
    isCorrection: bool = False
    completedAt: Optional[datetime] = None

class IndoorContext(BaseModel):
    currentZone: Optional[str] = None
    currentFloor: Optional[int] = None
    lastSeenLandmark: Optional[str] = None
    confidenceScore: Optional[float] = None
    needsRecheckPhoto: bool = False

class NavigationSessionOut(BaseModel):
    id: str
    inputSource: InputSource
    originId: str
    destinationId: str
    destinationLabel: Optional[str] = None
    status: NavStatus = NavStatus.PENDING
    steps: List[RouteStepOut] = []
    currentStepIndex: int = 0
    totalSteps: int = 0
    indoorContext: Optional[IndoorContext] = None
    googleMapsRoute: Optional[GoogleMapsRoute] = None
    correctionCount: int = 0
    voiceGuidanceEnabled: bool = True
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None

class NavigationStart(BaseModel):
    originId: str
    destinationId: str
    inputSource: InputSource = InputSource.TEXT
    venueId: Optional[str] = None
    voiceGuidanceEnabled: bool = True