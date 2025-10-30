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
    AddTeamsChannelResponse,
    InitiateChannelVerificationRequest,
    InitiateChannelVerificationResponse,
    VerifyChannelRequest,
    VerifyChannelResponse,
    DeleteChannelRequest,
    DeleteChannelResponse
)
from helper import (
    create_or_update_secret,
    get_secret,
    delete_secret,
    save_channel_metadata,
    delete_channel_metadata,
    post_to_teams_with_retry,
    build_teams_message_card,
    generate_verification_code,
    send_verification_code_to_teams,
    save_pending_verification,
    get_pending_verification,
    delete_pending_verification
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


@app.post("/initiate-channel-verification", response_model=InitiateChannelVerificationResponse, status_code=status.HTTP_200_OK)
async def initiate_channel_verification(request: InitiateChannelVerificationRequest):
    """
    Step 1: Initiate channel verification.
    - Generates 6-digit verification code
    - Sends code to Teams channel
    - Stores pending verification in Firestore
    - Code expires in 15 minutes
    """
    try:
        doc_id = f"{request.app_code}-{request.alert_type}"
        
        logger.info(f"Initiating channel verification: {doc_id}")
        
        # Generate verification code
        verification_code = generate_verification_code()
        
        # Calculate expiration (configurable)
        from datetime import timedelta
        expires_at = (datetime.utcnow() + timedelta(minutes=config.VERIFICATION_CODE_EXPIRY_MINUTES)).isoformat()
        
        # Send verification code to Teams
        logger.info(f"Sending verification code to Teams: {doc_id}")
        sent = await send_verification_code_to_teams(
            webhook_url=str(request.url),
            verification_code=verification_code,
            app_code=request.app_code,
            alert_type=request.alert_type
        )
        
        if not sent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to send verification code to Teams. Please check the webhook URL."
            )
        
        # Save pending verification
        save_pending_verification(
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type,
            url=str(request.url),
            verification_code=verification_code,
            updated_by=request.updated_by,
            expires_at=expires_at
        )
        
        logger.info(f"Verification code sent successfully: {doc_id}")
        
        return InitiateChannelVerificationResponse(
            success=True,
            message="Verification code sent to Teams channel. Please check the channel and enter the code.",
            doc_id=doc_id,
            verification_code=verification_code,
            expires_at=expires_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating channel verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate verification: {str(e)}"
        )


@app.post("/verify-channel", response_model=VerifyChannelResponse, status_code=status.HTTP_201_CREATED)
async def verify_channel(request: VerifyChannelRequest):
    """
    Step 2: Verify channel with code.
    - Validates verification code
    - Checks expiration
    - Stores webhook URL in Secret Manager
    - Stores metadata in Firestore
    - Deletes pending verification
    """
    try:
        doc_id = f"{request.app_code}-{request.alert_type}"
        
        logger.info(f"Verifying channel: {doc_id}")
        
        # Get pending verification
        pending = get_pending_verification(doc_id)
        
        if not pending:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pending verification found for {doc_id}. Please initiate verification first."
            )
        
        # Check expiration
        expires_at = datetime.fromisoformat(pending["expires_at"])
        if datetime.utcnow() > expires_at:
            delete_pending_verification(doc_id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please request a new code."
            )
        
        # Validate verification code
        if pending["verification_code"] != request.verification_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please try again."
            )
        
        logger.info(f"Verification code validated: {doc_id}")
        
        # Store webhook URL in Secret Manager
        secret_id = doc_id
        secret_version = create_or_update_secret(secret_id, pending["url"])
        
        # Store metadata in Firestore
        save_channel_metadata(
            collection_name=config.FIRESTORE_COLLECTION,
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type,
            secret_id=secret_id,
            secret_version=secret_version,
            updated_by=pending["updated_by"],
            timestamp=request.timestamp
        )
        
        # Delete pending verification
        delete_pending_verification(doc_id)
        
        logger.info(f"Channel verified and registered successfully: {doc_id}")
        
        return VerifyChannelResponse(
            success=True,
            message="Channel verified and registered successfully",
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type,
            verified=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify channel: {str(e)}"
        )


@app.post("/add-teams-channel", response_model=InitiateChannelVerificationResponse, status_code=status.HTTP_200_OK)
async def add_teams_channel(request: AddTeamsChannelRequest):
    """
    Register a Teams notification channel (with verification).
    
    This endpoint now initiates the verification process.
    Use /verify-channel to complete registration after receiving the code.
    
    Steps:
    1. Calls this endpoint with webhook URL
    2. Verification code sent to Teams channel
    3. User enters code via /verify-channel
    4. Channel registered after successful verification
    """
    try:
        # Convert to verification request
        verification_request = InitiateChannelVerificationRequest(
            app_code=request.app_code,
            alert_type=request.alert_type,
            url=request.url,
            updated_by=request.updated_by
        )
        
        # Delegate to verification flow
        return await initiate_channel_verification(verification_request)
        
    except Exception as e:
        logger.error(f"Error initiating channel registration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate channel registration: {str(e)}"
        )


@app.delete("/delete-teams-channel", response_model=DeleteChannelResponse, status_code=status.HTTP_200_OK)
async def delete_teams_channel(request: DeleteChannelRequest):
    """
    Delete a Teams notification channel.
    - Deletes webhook URL from Secret Manager
    - Deletes metadata from Firestore
    - Document ID: {app_code}-{alert_type}
    - Secret ID: {app_code}-{alert_type}
    """
    try:
        doc_id = f"{request.app_code}-{request.alert_type}"
        secret_id = doc_id
        
        logger.info(f"Deleting Teams channel: {doc_id}")
        
        # Delete from Firestore
        deleted_firestore = delete_channel_metadata(doc_id)
        
        # Delete from Secret Manager
        deleted_secret = delete_secret(secret_id)
        
        if not deleted_firestore and not deleted_secret:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel not found: {doc_id}"
            )
        
        logger.info(f"Successfully deleted channel: {doc_id} (Firestore: {deleted_firestore}, Secret: {deleted_secret})")
        
        return DeleteChannelResponse(
            success=True,
            message=f"Channel deleted successfully",
            doc_id=doc_id,
            app_code=request.app_code,
            alert_type=request.alert_type,
            deleted_from_firestore=deleted_firestore,
            deleted_from_secret_manager=deleted_secret
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting Teams channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete Teams channel: {str(e)}"
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
