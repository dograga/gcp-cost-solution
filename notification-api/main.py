"""
FastAPI Notification API
Sends messages to Microsoft Teams channels via webhooks.
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
import httpx
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Notification API",
    description="API for sending notifications to Microsoft Teams channels",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class TeamsMessageRequest(BaseModel):
    """Request model for posting to Teams channel."""
    webhook_url: HttpUrl = Field(
        ...,
        description="Microsoft Teams webhook URL",
        example="https://outlook.office.com/webhook/..."
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Message to post to Teams channel",
        example="Cost alert: Project XYZ exceeded budget by 20%"
    )
    title: Optional[str] = Field(
        None,
        max_length=256,
        description="Optional message title",
        example="Cost Alert"
    )
    color: Optional[str] = Field(
        "0078D4",
        description="Hex color code for message theme (without #)",
        example="FF0000"
    )
    facts: Optional[Dict[str, str]] = Field(
        None,
        description="Optional key-value pairs to display as facts",
        example={"Project": "XYZ", "Cost": "$1,250", "Budget": "$1,000"}
    )


class TeamsMessageResponse(BaseModel):
    """Response model for Teams message posting."""
    success: bool
    message: str
    timestamp: str
    webhook_url: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


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
    """
    Post message to Teams webhook with retry logic for transient errors.
    
    Args:
        webhook_url: Teams webhook URL
        message_card: Formatted message card
        max_retries: Maximum number of retry attempts
        
    Returns:
        httpx.Response object
        
    Raises:
        httpx.HTTPStatusError: If all retries fail
    """
    retryable_status_codes = {502, 503, 504, 429}  # Bad Gateway, Service Unavailable, Gateway Timeout, Too Many Requests
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    webhook_url,
                    json=message_card,
                    headers={"Content-Type": "application/json"}
                )
                
                # Success
                if response.status_code == 200:
                    if attempt > 0:
                        logger.info(f"Successfully posted to Teams after {attempt + 1} attempts")
                    return response
                
                # Retryable error
                if response.status_code in retryable_status_codes and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)  # Exponential backoff with jitter
                    logger.warning(
                        f"Teams webhook returned {response.status_code}, "
                        f"retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                
                # Non-retryable error or final attempt
                logger.error(f"Teams webhook returned status {response.status_code}: {response.text}")
                return response
                
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                # Network errors - retry
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                    logger.warning(
                        f"Network error ({type(e).__name__}), "
                        f"retrying in {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    # Final attempt - raise
                    raise
            
            except httpx.RequestError as e:
                # Other request errors - don't retry
                logger.error(f"Request error (non-retryable): {e}")
                raise
    
    # Should not reach here
    raise httpx.HTTPStatusError(
        "Max retries exceeded",
        request=None,
        response=None
    )


@app.post("/post-team-channel", response_model=TeamsMessageResponse, status_code=status.HTTP_200_OK)
async def post_to_teams_channel(request: TeamsMessageRequest):
    """
    Post a message to Microsoft Teams channel via webhook with retry logic.
    
    Automatically retries on transient errors (502, 503, 504, 429) with exponential backoff.
    
    Args:
        request: TeamsMessageRequest containing webhook URL and message
        
    Returns:
        TeamsMessageResponse with success status
        
    Raises:
        HTTPException: If posting to Teams fails after retries
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
    Build Microsoft Teams message card in Adaptive Card format.
    
    Args:
        title: Optional message title
        message: Message text
        color: Hex color code (without #)
        facts: Optional key-value pairs
        
    Returns:
        Teams message card dictionary
    """
    # Build message card using MessageCard format (legacy but widely supported)
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": color,
        "summary": title or message[:100],
    }
    
    # Add title if provided
    if title:
        card["title"] = title
    
    # Add message text
    card["text"] = message
    
    # Add facts if provided
    if facts:
        card["sections"] = [
            {
                "facts": [
                    {"name": key, "value": value}
                    for key, value in facts.items()
                ]
            }
        ]
    
    return card


# Alternative endpoint with simple text message
@app.post("/post-simple-message", response_model=TeamsMessageResponse)
async def post_simple_message(
    webhook_url: HttpUrl,
    message: str
):
    """
    Post a simple text message to Teams channel.
    
    Simplified endpoint that only requires webhook URL and message text.
    
    Args:
        webhook_url: Microsoft Teams webhook URL
        message: Message text to post
        
    Returns:
        TeamsMessageResponse with success status
    """
    request = TeamsMessageRequest(
        webhook_url=webhook_url,
        message=message
    )
    return await post_to_teams_channel(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
