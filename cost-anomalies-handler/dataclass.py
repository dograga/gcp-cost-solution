from typing import Dict, Any, Optional
from pydantic import BaseModel

class PubSubMessage(BaseModel):
    """Pub/Sub message format"""
    message: Dict[str, Any]
    subscription: str

class AnomalyData(BaseModel):
    """
    Model representing the anomaly data structure.
    This can be expanded based on the actual GCP anomaly payload.
    """
    anomaly_id: Optional[str] = None
    id: Optional[str] = None
    project_id: Optional[str] = None
    projectId: Optional[str] = None
    # Add other known fields as optional to allow flexibility
    description: Optional[str] = None
    cost: Optional[float] = None
    currency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    class Config:
        extra = "allow" # Allow extra fields from the raw payload
