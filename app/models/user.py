from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"


class SubscriptionPlan(str, Enum):
    FREE = "free"
    PREMIUM = "premium"


class Subscription(BaseModel):
    plan: SubscriptionPlan = SubscriptionPlan.FREE
    startedAt: Optional[datetime] = None
    expiresAt: Optional[datetime] = None
    isActive: bool = False


class Wallet(BaseModel):
    balance: float = 0
    totalEarned: float = 0
    totalWithdrawn: float = 0


class UserOut(BaseModel):
    id: str
    email: Optional[str] = None
    fullName: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    image: Optional[str] = None
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE
    verified: bool = False
    phoneNumber: Optional[str] = None
    region: Optional[str] = None
    subscription: Optional[Subscription] = None
    wallet: Optional[Wallet] = None
    usageCount: int = 0
    createdAt: Optional[datetime] = None