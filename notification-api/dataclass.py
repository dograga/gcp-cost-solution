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
    webhook_url: str
    message: str
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
