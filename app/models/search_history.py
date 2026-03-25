from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class InputType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
    PHOTO = "photo"


class SearchHistoryItem(BaseModel):
    id: str
    query: Optional[str] = None
    resolvedAddress: Optional[str] = None
    inputType: InputType = InputType.TEXT
    venueId: Optional[str] = None
    locationId: Optional[str] = None
    searchedAt: datetime


class SearchHistoryGrouped(BaseModel):
    today: List[SearchHistoryItem] = []
    lastWeek: List[SearchHistoryItem] = []
    lastMonth: List[SearchHistoryItem] = []