"""FastAPI Notification API - Teams webhooks and Pub/Sub integration"""

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import HttpUrl
import httpx
import logging
import asyncio
import base64
import json
from typing import Dict, Any
from datetime import datetime

from dataclass import (
    TeamsMessageRequest,
    TeamsMessageResponse,
    PubSubMessage,
    PubSubNotification,
    HealthResponse,
    TeamsColor
)

logging.basicConfig(
    level=logging.INFO,
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
    allow_origins=["*"],
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


async def post_to_teams_with_retry(
    webhook_url: str,
    message_card: Dict[str, Any],
    max_retries: int = 3
) -> httpx.Response:
    """Post to Teams with retry on transient errors (502, 503, 504, 429)"""
    retryable_status_codes = {502, 503, 504, 429}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    webhook_url,
                    json=message_card,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    if attempt > 0:
                        logger.info(f"Posted to Teams after {attempt + 1} attempts")
                    return response
                
                if response.status_code in retryable_status_codes and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(f"Retry {attempt + 1}/{max_retries} after {response.status_code}")
                    await asyncio.sleep(wait_time)
                    continue
                
                logger.error(f"Teams webhook failed: {response.status_code}")
                return response
                
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(f"Network error, retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(wait_time)
                    continue
                raise
            
            except httpx.RequestError as e:
                logger.error(f"Request error: {e}")
                raise
    
    raise httpx.HTTPStatusError("Max retries exceeded", request=None, response=None)


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


def build_teams_message_card(
    title: Optional[str],
    message: str,
    color: str = "0078D4",
    facts: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Build Microsoft Teams message using Adaptive Card format.
    
    Adaptive Cards provide richer UI and better long-term Teams support.
    """
    # Map hex color to Adaptive Card accent color
    # Adaptive Cards support: default, dark, light, accent, good, warning, attention
    color_map = {
        "0078D4": "accent",      # Microsoft Blue (default)
        "00FF00": "good",        # Green (success)
        "28A745": "good",        # Green (success)
        "FFA500": "warning",     # Orange (warning)
        "FFC107": "warning",     # Yellow (warning)
        "FF0000": "attention",   # Red (error)
        "DC3545": "attention",   # Red (error)
        "8B0000": "attention",   # Dark Red (critical)
    }
    
    accent_color = color_map.get(color.upper(), "accent")
    
    # Build body elements
    body = []
    
    # Add colored accent bar using Container
    body.append({
        "type": "Container",
        "style": accent_color,
        "items": [
            {
                "type": "TextBlock",
                "text": title if title else "Notification",
                "weight": "bolder",
                "size": "large",
                "wrap": True
            }
        ],
        "bleed": True
    })
    
    # Add message text
    body.append({
        "type": "TextBlock",
        "text": message,
        "wrap": True,
        "spacing": "medium"
    })
    
    # Add facts as FactSet if provided
    if facts:
        fact_set = {
            "type": "FactSet",
            "facts": [
                {"title": key, "value": value}
                for key, value in facts.items()
            ],
            "spacing": "medium"
        }
        body.append(fact_set)
    
    # Build Adaptive Card
    adaptive_card = {
        "type": "AdaptiveCard",
        "body": body,
        "msteams": {
            "width": "Full"
        },
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4"
    }
    
    # Wrap in message attachment format
    message_payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": adaptive_card
            }
        ]
    }
    
    return message_payload


@app.post("/post-simple-message", response_model=TeamsMessageResponse)
async def post_simple_message(webhook_url: HttpUrl, message: str):
    """Post simple text message to Teams"""
    request = TeamsMessageRequest(webhook_url=webhook_url, message=message)
    return await post_to_teams_channel(request)


@app.post("/pubsub-notification")
async def pubsub_notification(request: Request):
    """
    Pub/Sub push subscription endpoint for Teams notifications.
    
    Expects Pub/Sub message with base64-encoded JSON payload:
    {
        "webhook_url": "https://outlook.office.com/webhook/...",
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
        if "webhook_url" not in payload or "message" not in payload:
            raise HTTPException(
                status_code=400,
                detail="Payload must contain webhook_url and message"
            )
        
        # Create Teams message request
        teams_request = TeamsMessageRequest(
            webhook_url=payload["webhook_url"],
            message=payload["message"],
            title=payload.get("title"),
            color=payload.get("color", "0078D4"),
            facts=payload.get("facts")
        )
        
        # Post to Teams
        response = await post_to_teams_channel(teams_request)
        
        # Return 204 No Content for Pub/Sub acknowledgment
        return {"status": "processed", "success": response.success}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in Pub/Sub message: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    except Exception as e:
        logger.error(f"Error processing Pub/Sub message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
