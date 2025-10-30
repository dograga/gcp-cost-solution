"""Helper functions for notification API"""

import logging
import random
import string
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from google.cloud import firestore
from google.cloud import secretmanager
import httpx
import asyncio

import config

logger = logging.getLogger(__name__)

# Initialize GCP clients
db = firestore.Client(project=config.GCP_PROJECT_ID)
secret_client = secretmanager.SecretManagerServiceClient()


# Secret Manager functions
def create_or_update_secret(secret_id: str, secret_value: str) -> str:
    """Create or update a secret in Secret Manager"""
    parent = f"projects/{config.GCP_PROJECT_ID}"
    secret_path = f"{parent}/secrets/{secret_id}"
    
    try:
        secret_client.get_secret(name=secret_path)
        logger.info(f"Secret {secret_id} exists, adding new version")
        
    except Exception:
        logger.info(f"Creating new secret: {secret_id}")
        secret_client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}}
            }
        )
    
    version = secret_client.add_secret_version(
        request={
            "parent": secret_path,
            "payload": {"data": secret_value.encode("UTF-8")}
        }
    )
    
    logger.info(f"Secret version created: {version.name}")
    return version.name


def get_secret(secret_id: str) -> str:
    """Get secret value from Secret Manager"""
    secret_path = f"projects/{config.GCP_PROJECT_ID}/secrets/{secret_id}/versions/latest"
    
    try:
        response = secret_client.access_secret_version(name=secret_path)
        secret_value = response.payload.data.decode("UTF-8")
        return secret_value
    except Exception as e:
        logger.error(f"Error accessing secret {secret_id}: {e}")
        raise


# Firestore functions
def save_channel_metadata(
    collection_name: str,
    doc_id: str,
    app_code: str,
    alert_type: str,
    secret_id: str,
    secret_version: str,
    updated_by: str,
    timestamp: str
) -> None:
    """Save channel metadata to Firestore"""
    channel_data = {
        "app_code": app_code,
        "alert_type": alert_type,
        "secret_id": secret_id,
        "secret_version": secret_version,
        "updated_by": updated_by,
        "timestamp": timestamp,
        "verified": True,
        "created_at": datetime.utcnow().isoformat(),
        "last_modified": datetime.utcnow().isoformat()
    }
    
    doc_ref = db.collection(collection_name).document(doc_id)
    doc_ref.set(channel_data, merge=True)
    logger.info(f"Saved metadata to Firestore: {doc_id}")


def save_pending_verification(
    doc_id: str,
    app_code: str,
    alert_type: str,
    url: str,
    verification_code: str,
    updated_by: str,
    expires_at: str
) -> None:
    """Save pending verification to Firestore"""
    verification_data = {
        "app_code": app_code,
        "alert_type": alert_type,
        "url": url,
        "verification_code": verification_code,
        "updated_by": updated_by,
        "expires_at": expires_at,
        "verified": False,
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending"
    }
    
    collection_name = f"{config.FIRESTORE_COLLECTION}-pending"
    doc_ref = db.collection(collection_name).document(doc_id)
    doc_ref.set(verification_data)
    logger.info(f"Saved pending verification to Firestore: {doc_id}")


def get_pending_verification(doc_id: str) -> Optional[Dict[str, Any]]:
    """Get pending verification from Firestore"""
    collection_name = f"{config.FIRESTORE_COLLECTION}-pending"
    doc_ref = db.collection(collection_name).document(doc_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return doc.to_dict()
    return None


def delete_pending_verification(doc_id: str) -> None:
    """Delete pending verification from Firestore"""
    collection_name = f"{config.FIRESTORE_COLLECTION}-pending"
    doc_ref = db.collection(collection_name).document(doc_id)
    doc_ref.delete()
    logger.info(f"Deleted pending verification: {doc_id}")


# Verification code functions
def generate_verification_code() -> str:
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))


async def send_verification_code_to_teams(webhook_url: str, verification_code: str, app_code: str, alert_type: str) -> bool:
    """Send verification code to Teams channel"""
    message_card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "body": [
                    {
                        "type": "Container",
                        "style": "accent",
                        "items": [{
                            "type": "TextBlock",
                            "text": "🔐 Channel Verification",
                            "weight": "bolder",
                            "size": "large",
                            "wrap": True
                        }],
                        "bleed": True
                    },
                    {
                        "type": "TextBlock",
                        "text": "Please verify this Teams channel to enable notifications.",
                        "wrap": True,
                        "spacing": "medium"
                    },
                    {
                        "type": "FactSet",
                        "facts": [
                            {"title": "App Code", "value": app_code},
                            {"title": "Alert Type", "value": alert_type},
                            {"title": "Verification Code", "value": f"**{verification_code}**"}
                        ],
                        "spacing": "medium"
                    },
                    {
                        "type": "TextBlock",
                        "text": "⚠️ This code expires in 15 minutes. Enter this code in the registration UI to complete setup.",
                        "wrap": True,
                        "spacing": "medium",
                        "color": "warning",
                        "size": "small"
                    }
                ],
                "msteams": {"width": "Full"},
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "version": "1.4"
            }
        }]
    }
    
    try:
        response = await post_to_teams_with_retry(webhook_url, message_card, max_retries=2)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send verification code to Teams: {e}")
        return False


# Teams webhook functions
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


def build_teams_message_card(
    title: str,
    message: str,
    color: str = "0078D4",
    facts: Dict[str, str] = None
) -> Dict[str, Any]:
    """Build Microsoft Teams message using Adaptive Card format"""
    color_map = {
        "0078D4": "accent",
        "00FF00": "good",
        "28A745": "good",
        "FFA500": "warning",
        "FFC107": "warning",
        "FF0000": "attention",
        "DC3545": "attention",
        "8B0000": "attention",
    }
    
    accent_color = color_map.get(color.upper(), "accent")
    
    body = []
    
    body.append({
        "type": "Container",
        "style": accent_color,
        "items": [{
            "type": "TextBlock",
            "text": title or "Notification",
            "weight": "bolder",
            "size": "large",
            "wrap": True
        }],
        "bleed": True
    })
    
    body.append({
        "type": "TextBlock",
        "text": message,
        "wrap": True,
        "spacing": "medium"
    })
    
    if facts:
        body.append({
            "type": "FactSet",
            "facts": [
                {"title": key, "value": value}
                for key, value in facts.items()
            ],
            "spacing": "medium"
        })
    
    adaptive_card = {
        "type": "AdaptiveCard",
        "body": body,
        "msteams": {"width": "Full"},
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4"
    }
    
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": adaptive_card
        }]
    }
