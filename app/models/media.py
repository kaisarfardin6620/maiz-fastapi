from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"

class MediaPurpose(str, Enum):
    GROUNDING_PHOTO = "grounding_photo"
    RECHECK_PHOTO = "recheck_photo"
    DESTINATION_PHOTO = "destination_photo"
    VENUE_CONTRIBUTION = "venue_contribution"
    VOICE_COMMAND = "voice_command"
    CHAT_ATTACHMENT = "chat_attachment"

class DetectedLandmark(BaseModel):
    landmarkId: Optional[str] = None
    name: Optional[str] = None
    confidence: Optional[float] = None

class AIAnalysis(BaseModel):
    detectedVenueType: Optional[str] = None
    detectedZone: Optional[str] = None
    detectedLandmarks: List[DetectedLandmark] = []
    detectedText: Optional[str] = None
    detectedLocation: Optional[str] = None
    overallConfidence: Optional[float] = None
    tags: List[str] = []
    analysedAt: Optional[datetime] = None

class MediaAssetOut(BaseModel):
    id: str
    mediaType: MediaType
    purpose: MediaPurpose
    url: str
    mimeType: Optional[str] = None
    sizeBytes: Optional[int] = None
    durationSec: Optional[float] = None
    thumbnail: Optional[str] = None
    aiAnalysis: Optional[AIAnalysis] = None
    linkedVenue: Optional[str] = None
    createdAt: Optional[datetime] = None

class MediaUploadResponse(BaseModel):
    assetId: str
    url: str
    mediaType: MediaType
    purpose: MediaPurpose
    aiAnalysis: Optional[AIAnalysis] = None