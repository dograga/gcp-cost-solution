"""Pydantic models for notification API"""

from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Optional, Dict, Any
from enum import Enum


class TeamsColor(str, Enum):
    """Predefined Teams color schemes"""
    INFO = "0078D4"      # Microsoft Blue
    SUCCESS = "28A745"   # Green
    WARNING = "FFC107"   # Yellow/Orange
    ERROR = "DC3545"     # Red
    CRITICAL = "8B0000"  # Dark Red
    ACCENT = "0078D4"    # Same as INFO (default)


class TeamsMessageRequest(BaseModel):
    """Request model for posting to Teams channel"""
    webhook_url: HttpUrl
    message: str = Field(..., min_length=1, max_length=10000)
    title: Optional[str] = Field(None, max_length=256)
    color: Optional[str] = Field(default=TeamsColor.INFO, description="Hex color code without #")
    facts: Optional[Dict[str, str]] = None
    
    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> str:
        """Validate and normalize color hex code"""
        if v is None:
            return TeamsColor.INFO
        
        # Remove # if present
        v = v.lstrip('#').upper()
        
        # Validate hex format
        if len(v) != 6:
            raise ValueError("Color must be 6-character hex code")
        
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Color must be valid hex code")
        
        return v


class TeamsMessageResponse(BaseModel):
    """Response model for Teams message posting"""
    success: bool
    message: str
    timestamp: str
    webhook_url: str


class PubSubMessage(BaseModel):
    """Pub/Sub push message envelope"""
    message: Dict[str, Any]
    subscription: str


class PubSubNotification(BaseModel):
    """Notification payload from Pub/Sub (decoded)"""
    app_code: str = Field(..., min_length=1, max_length=100)
    alert_type: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1)
    title: Optional[str] = None
    color: Optional[str] = Field(default=TeamsColor.INFO)
    facts: Optional[Dict[str, str]] = None
    
    @field_validator('color')
    @classmethod
    def validate_color(cls, v: Optional[str]) -> str:
        """Validate and normalize color hex code"""
        if v is None:
            return TeamsColor.INFO
        
        v = v.lstrip('#').upper()
        
        if len(v) != 6:
            raise ValueError("Color must be 6-character hex code")
        
        try:
            int(v, 16)
        except ValueError:
            raise ValueError("Color must be valid hex code")
        
        return v


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str


class AddTeamsChannelRequest(BaseModel):
    """Request to register a Teams notification channel"""
    app_code: str = Field(..., min_length=1, max_length=100, description="Application code")
    alert_type: str = Field(..., min_length=1, max_length=100, description="Alert type")
    url: HttpUrl = Field(..., description="Teams webhook URL")
    updated_by: str = Field(..., min_length=1, max_length=100, description="User who updated")
    timestamp: str = Field(..., description="ISO timestamp")
    
    @field_validator('app_code', 'alert_type')
    @classmethod
    def validate_no_special_chars(cls, v: str) -> str:
        """Ensure no special characters that could break document ID"""
        if '-' in v:
            raise ValueError("app_code and alert_type cannot contain hyphens")
        return v.strip()


class AddTeamsChannelResponse(BaseModel):
    """Response for Teams channel registration"""
    success: bool
    message: str
    doc_id: str
    app_code: str
    alert_type: str


class InitiateChannelVerificationRequest(BaseModel):
    """Request to initiate channel verification"""
    app_code: str = Field(..., min_length=1, max_length=100, description="Application code")
    alert_type: str = Field(..., min_length=1, max_length=100, description="Alert type")
    url: HttpUrl = Field(..., description="Teams webhook URL to verify")
    
    @field_validator('app_code', 'alert_type')
    @classmethod
    def validate_no_special_chars(cls, v: str) -> str:
        """Ensure no special characters that could break document ID"""
        if '-' in v:
            raise ValueError("app_code and alert_type cannot contain hyphens")
        return v.strip()


class InitiateChannelVerificationResponse(BaseModel):
    """Response for channel verification initiation"""
    success: bool
    message: str
    doc_id: str
    verification_code: str
    expires_at: str
    requested_by: str


class VerifyChannelRequest(BaseModel):
    """Request to verify channel with code"""
    app_code: str = Field(..., min_length=1, max_length=100)
    alert_type: str = Field(..., min_length=1, max_length=100)
    verification_code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    timestamp: str = Field(..., description="ISO timestamp")


class VerifyChannelResponse(BaseModel):
    """Response for channel verification"""
    success: bool
    message: str
    doc_id: str
    app_code: str
    alert_type: str
    verified: bool
    requested_by: str


class DeleteChannelRequest(BaseModel):
    """Request to delete a Teams channel"""
    app_code: str = Field(..., min_length=1, max_length=100)
    alert_type: str = Field(..., min_length=1, max_length=100)


class DeleteChannelResponse(BaseModel):
    """Response for channel deletion"""
    success: bool
    message: str
    doc_id: str
    app_code: str
    alert_type: str
    deleted_from_firestore: bool
    deleted_from_secret_manager: bool
    requested_by: str
