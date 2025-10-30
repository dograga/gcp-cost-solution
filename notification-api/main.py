"""FastAPI Notification API - Teams webhooks and Pub/Sub integration"""

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import HttpUrl
import logging
import base64
import json
from datetime import datetime

import config
from dataclass import (
    TeamsMessageRequest,
    TeamsMessageResponse,
    HealthResponse,
    AddTeamsChannelRequest,
    AddTeamsChannelResponse
)
from helper import (
    create_or_update_secret,
    get_secret,
    save_channel_metadata,
    post_to_teams_with_retry,
    build_teams_message_card
)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Notification API",
    description="API for sending notifications to Microsoft Teams channels",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API Endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0"
    )


@app.post("/add-teams-channel", response_model=AddTeamsChannelResponse, status_code=status.HTTP_201_CREATED)
async def add_teams_channel(request: AddTeamsChannelRequest):
    """
    Register a Teams notification channel.
    - Stores webhook URL in Secret Manager
    - Stores metadata in Firestore
    - Document ID: {app_code}-{alert_type}
    - Secret ID: {app_code}-{alert_type}
    """
    try:
        doc_id = f"{request.app_code}-{request.alert_type}"
        secret_id = doc_id
        
        logger.info(f"Registering Teams channel: {doc_id}")
        
        # Store webhook URL in Secret Manager
        secret_version = create_or_update_secret(secret_id, str(request.url))
        
        # Store metadata in Firestore
        save_channel_metadata(
            collection_name=config.FIRESTORE_COLLECTION,
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type,
            secret_id=secret_id,
            secret_version=secret_version,
            updated_by=request.updated_by,
            timestamp=request.timestamp
        )
        
        logger.info(f"Successfully registered channel: {doc_id}")
        
        return AddTeamsChannelResponse(
            success=True,
            message="Teams channel registered successfully (URL stored in Secret Manager)",
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type
        )
        
    except Exception as e:
        logger.error(f"Error registering Teams channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register Teams channel: {str(e)}"
        )


@app.post("/post-team-channel", response_model=TeamsMessageResponse, status_code=status.HTTP_200_OK)
async def post_to_teams_channel(request: TeamsMessageRequest):
    """
    Post a message to Microsoft Teams channel via webhook with retry logic.
    Automatically retries on transient errors (502, 503, 504, 429) with exponential backoff.
    """
    logger.info(f"Posting message to Teams channel")
    
    try:
        # Build Teams message card
        message_card = build_teams_message_card(
            title=request.title,
            message=request.message,
            color=request.color,
            facts=request.facts
        )
        
        # Send to Teams webhook with retry logic
        response = await post_to_teams_with_retry(
            webhook_url=str(request.webhook_url),
            message_card=message_card,
            max_retries=3
        )
        
        # Check response
        if response.status_code == 200:
            logger.info(f"Successfully posted message to Teams")
            return TeamsMessageResponse(
                success=True,
                message="Message posted successfully to Teams channel",
                timestamp=datetime.utcnow().isoformat(),
                webhook_url=str(request.webhook_url)
            )
        else:
            logger.error(f"Teams webhook returned status {response.status_code}: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Teams webhook failed with status {response.status_code}: {response.text}"
            )
                
    except httpx.TimeoutException:
        logger.error("Timeout while posting to Teams webhook after retries")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timeout while posting to Teams webhook"
        )
    
    except httpx.RequestError as e:
        logger.error(f"Request error while posting to Teams: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error posting to Teams webhook: {str(e)}"
        )
    
    except Exception as e:
        logger.error(f"Unexpected error posting to Teams: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@app.post("/post-simple-message", response_model=TeamsMessageResponse)
async def post_simple_message(webhook_url: HttpUrl, message: str):
    """Post simple text message to Teams"""
    request = TeamsMessageRequest(webhook_url=webhook_url, message=message)
    return await post_to_teams_channel(request)


@app.post("/pubsub-notification")
async def pubsub_notification(request: Request):
    """
    Pub/Sub push subscription endpoint for Teams notifications.
    
    Retrieves webhook URL from Secret Manager using app_code and alert_type.
    
    Expects Pub/Sub message with base64-encoded JSON payload:
    {
        "app_code": "cost-alerts",
        "alert_type": "budget-exceeded",
        "message": "Alert message",
        "title": "Alert Title",
        "color": "FF0000",
        "facts": {"key": "value"}
    }
    """
    try:
        envelope = await request.json()
        
        if "message" not in envelope:
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message format")
        
        pubsub_message = envelope["message"]
        
        if "data" not in pubsub_message:
            raise HTTPException(status_code=400, detail="No data in Pub/Sub message")
        
        # Decode base64 payload
        data = base64.b64decode(pubsub_message["data"]).decode("utf-8")
        payload = json.loads(data)
        
        logger.info(f"Received Pub/Sub notification: {payload.get('title', 'No title')}")
        
        # Validate required fields
        if "app_code" not in payload or "alert_type" not in payload or "message" not in payload:
            raise HTTPException(
                status_code=400,
                detail="Payload must contain app_code, alert_type, and message"
            )
        
        # Get secret ID from app_code and alert_type
        secret_id = f"{payload['app_code']}-{payload['alert_type']}"
        
        logger.info(f"Retrieving webhook URL from Secret Manager: {secret_id}")
        
        # Get webhook URL from Secret Manager
        try:
            webhook_url = get_secret(secret_id)
        except Exception as e:
            logger.error(f"Failed to retrieve webhook URL for {secret_id}: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"Webhook URL not found for {secret_id}. Please register the channel first."
            )
        
        # Create Teams message request
        teams_request = TeamsMessageRequest(
            webhook_url=webhook_url,
            message=payload["message"],
            title=payload.get("title"),
            color=payload.get("color", "0078D4"),
            facts=payload.get("facts")
        )
        
        # Post to Teams
        response = await post_to_teams_channel(teams_request)
        
        return {"status": "processed", "success": response.success, "secret_id": secret_id}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Pub/Sub message: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
