from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from ..models.user import UserRole


class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    phone: Optional[str] = Field(None, max_length=50)
    role: UserRole = UserRole.FARMER
    centre_id: Optional[int] = None
    preferred_language: str = Field("en", max_length=10)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class PhoneOtpRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15, description="Farmer phone number")


class PhoneOtpVerify(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=4, max_length=10, description="OTP code (dev mock: 123456)")


class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str
    centre_id: Optional[int] = None
    preferred_language: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
