# Notification API

FastAPI-based notification service for posting messages to Microsoft Teams channels via webhooks.

## Overview

This API provides endpoints to send formatted messages to Microsoft Teams channels. It handles webhook authentication and message formatting automatically.

## Features

- **FastAPI Framework**: Modern, fast, async API framework
- **Teams Integration**: Post messages to Teams channels via webhooks
- **Adaptive Cards**: Modern card format with rich UI and better Teams support
- **Message Formatting**: Support for titles, colors, and fact tables
- **Retry Logic**: Automatic retry with exponential backoff for transient errors (502, 503, 504, 429)
- **Error Handling**: Comprehensive error handling with proper HTTP status codes
- **Health Checks**: Built-in health check endpoints
- **CORS Support**: Configurable CORS for cross-origin requests
- **Docker Ready**: Containerized for easy deployment

## API Endpoints

### POST /post-team-channel

Post a formatted message to Microsoft Teams channel.

**Request Body:**
```json
{
  "webhook_url": "https://outlook.office.com/webhook/...",
  "message": "Cost alert: Project XYZ exceeded budget by 20%",
  "title": "Cost Alert",
  "color": "FF0000",
  "facts": {
    "Project": "XYZ",
    "Cost": "$1,250",
    "Budget": "$1,000",
    "Overage": "20%"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Message posted successfully to Teams channel",
  "timestamp": "2025-10-29T15:55:00Z",
  "webhook_url": "https://outlook.office.com/webhook/..."
}
```

**Parameters:**
- `webhook_url` (required): Microsoft Teams webhook URL
- `message` (required): Message text (1-10,000 characters)
- `title` (optional): Message title (max 256 characters)
- `color` (optional): Hex color code without # (default: "0078D4" - Microsoft blue)
- `facts` (optional): Key-value pairs to display as a table

### POST /post-simple-message

Post a simple text message (query parameters).

**Query Parameters:**
- `webhook_url`: Teams webhook URL
- `message`: Message text

**Example:**
```bash
curl -X POST "http://localhost:8080/post-simple-message?webhook_url=https://outlook.office.com/webhook/...&message=Hello%20Teams"
```

### POST /initiate-channel-verification

**Step 1:** Initiate channel verification by sending a verification code to Teams.

**Request Body:**
```json
{
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "url": "https://outlook.office.com/webhook/...",
  "updated_by": "john.doe@company.com"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Verification code sent to Teams channel. Please check the channel and enter the code.",
  "doc_id": "cost-alerts-budget-exceeded",
  "verification_code": "123456",
  "expires_at": "2025-10-30T12:15:00Z"
}
```

**What happens:**
1. Generates 6-digit verification code
2. Sends code to Teams channel via webhook
3. Stores pending verification in Firestore
4. Code expires in 15 minutes

**Teams Message:**
```
🔐 Channel Verification

Please verify this Teams channel to enable notifications.

App Code: cost-alerts
Alert Type: budget-exceeded
Verification Code: **123456**

⚠️ This code expires in 15 minutes. Enter this code in the registration UI to complete setup.
```

### POST /verify-channel

**Step 2:** Verify channel by submitting the verification code.

**Request Body:**
```json
{
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "verification_code": "123456",
  "timestamp": "2025-10-30T12:10:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Channel verified and registered successfully",
  "doc_id": "cost-alerts-budget-exceeded",
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "verified": true
}
```

**What happens:**
1. Validates verification code
2. Checks expiration (15 minutes)
3. Stores webhook URL in Secret Manager
4. Stores metadata in Firestore
5. Deletes pending verification

**Error Responses:**

**Code Expired:**
```json
{
  "detail": "Verification code has expired. Please request a new code."
}
```

**Invalid Code:**
```json
{
  "detail": "Invalid verification code. Please try again."
}
```

**No Pending Verification:**
```json
{
  "detail": "No pending verification found for cost-alerts-budget-exceeded. Please initiate verification first."
}
```

### POST /add-teams-channel (Legacy - Direct Registration)

Register a Teams notification channel with secure webhook URL storage (without verification).

**Request Body:**
```json
{
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "url": "https://outlook.office.com/webhook/...",
  "updated_by": "john.doe@company.com",
  "timestamp": "2025-10-30T12:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Teams channel registered successfully (URL stored in Secret Manager)",
  "doc_id": "cost-alerts-budget-exceeded",
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded"
}
```

**Security Architecture:**

1. **Webhook URL** → Stored in **Secret Manager**
   - Secret ID: `{app_code}-{alert_type}`
   - Example: `cost-alerts-budget-exceeded`
   - Encrypted at rest
   - Access controlled via IAM

2. **Metadata** → Stored in **Firestore**
   - Collection: Configurable via `FIRESTORE_COLLECTION` env var
   - Document ID: `{app_code}-{alert_type}`
   - Does NOT contain webhook URL

**Document ID & Secret ID Format:**
- Format: `{app_code}-{alert_type}`
- Example: `cost-alerts-budget-exceeded`
- Ensures atomicity (upsert behavior)

**Firestore Document Structure:**
```json
{
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "secret_id": "cost-alerts-budget-exceeded",
  "secret_version": "projects/123/secrets/cost-alerts-budget-exceeded/versions/1",
  "updated_by": "john.doe@company.com",
  "timestamp": "2025-10-30T12:00:00Z",
  "created_at": "2025-10-30T12:00:00.123Z",
  "last_modified": "2025-10-30T12:00:00.123Z"
}
```

**Secret Manager:**
- Secret ID: `cost-alerts-budget-exceeded`
- Secret Value: `https://outlook.office.com/webhook/...`
- Automatic replication
- Versioned (supports updates)

**Validation:**
- `app_code` and `alert_type` cannot contain hyphens
- All fields are required
- URL must be valid Teams webhook URL

**Configuration:**
- Collection name: Set via `FIRESTORE_COLLECTION` in `.env.{env}`
- Example: `teams-notification-channels-dev`

### POST /pubsub-notification

Pub/Sub push subscription endpoint for event-driven notifications.

**How it works:**
1. Receives `app_code` and `alert_type` in payload
2. Retrieves webhook URL from Secret Manager using `{app_code}-{alert_type}`
3. Posts message to Teams webhook

**Pub/Sub Message Format:**
```json
{
  "message": {
    "data": "base64-encoded-payload",
    "messageId": "123456",
    "publishTime": "2025-10-29T12:00:00Z"
  },
  "subscription": "projects/my-project/subscriptions/teams-notifications"
}
```

**Decoded Payload (base64):**
```json
{
  "app_code": "cost-alerts",
  "alert_type": "budget-exceeded",
  "message": "Cost alert: Budget exceeded by 25%",
  "title": "⚠️ Cost Alert",
  "color": "FF0000",
  "facts": {
    "Project": "my-project",
    "Cost": "$1,250",
    "Budget": "$1,000"
  }
}
```

**Response:**
```json
{
  "status": "processed",
  "success": true,
  "secret_id": "cost-alerts-budget-exceeded"
}
```

**Error Response (Channel not registered):**
```json
{
  "detail": "Webhook URL not found for cost-alerts-budget-exceeded. Please register the channel first."
}
```

**Prerequisites:**
- Channel must be registered first using `/add-teams-channel`
- Secret Manager must contain webhook URL with ID `{app_code}-{alert_type}`

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-29T15:55:00Z",
  "version": "1.0.0"
}
```

## Pub/Sub Integration

### Setup Pub/Sub Push Subscription

1. **Create Pub/Sub Topic**
```bash
gcloud pubsub topics create teams-notifications
```

2. **Deploy Notification API to Cloud Run**
```bash
gcloud run deploy notification-api \
  --source . \
  --region asia-southeast1 \
  --allow-unauthenticated
```

3. **Create Push Subscription**
```bash
gcloud pubsub subscriptions create teams-notifications-sub \
  --topic=teams-notifications \
  --push-endpoint=https://notification-api-xxx.run.app/pubsub-notification \
  --ack-deadline=60
```

4. **Publish Test Message**
```bash
# Encode payload as base64
echo -n '{"webhook_url":"https://outlook.office.com/webhook/...","message":"Test from Pub/Sub","title":"Test Alert","color":"0078D4"}' | base64

# Publish to topic
gcloud pubsub topics publish teams-notifications \
  --message='<base64-encoded-payload>'
```

### Python Example - Publish to Pub/Sub

```python
from google.cloud import pubsub_v1
import json

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path('my-project', 'teams-notifications')

# Create notification payload (no webhook URL needed)
payload = {
    "app_code": "cost-alerts",
    "alert_type": "budget-exceeded",
    "message": "Cost alert: Budget exceeded by 25%",
    "title": "⚠️ Cost Alert",
    "color": "FF0000",
    "facts": {
        "Project": "my-gcp-project",
        "Current Cost": "$1,250",
        "Budget": "$1,000",
        "Overage": "25%"
    }
}

# Publish (Pub/Sub will base64 encode automatically)
data = json.dumps(payload).encode('utf-8')
future = publisher.publish(topic_path, data)
print(f"Published message ID: {future.result()}")

# Note: The channel must be registered first:
# POST /add-teams-channel with app_code="cost-alerts" and alert_type="budget-exceeded"
```

## Configuration

### Environment Variables

Create environment-specific configuration files:

**.env.dev:**
```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8080
LOG_LEVEL=INFO
ALLOWED_ORIGINS=*

# GCP Configuration
GCP_PROJECT_ID=my-project-dev

# Firestore Configuration
FIRESTORE_COLLECTION=teams-notification-channels-dev
```

**.env.uat:**
```bash
GCP_PROJECT_ID=my-project-uat
FIRESTORE_COLLECTION=teams-notification-channels-uat
LOG_LEVEL=INFO
```

**.env.prod:**
```bash
GCP_PROJECT_ID=my-project-prod
FIRESTORE_COLLECTION=teams-notification-channels
LOG_LEVEL=WARNING
```

### Running with Environment

```bash
# Development
ENVIRONMENT=dev python main.py

# UAT
ENVIRONMENT=uat python main.py

# Production
ENVIRONMENT=prod python main.py
```

### GCP Permissions Required

**Service Account needs:**
- `roles/secretmanager.admin` - Create/update secrets
- `roles/secretmanager.secretAccessor` - Read secrets
- `roles/datastore.user` - Firestore read/write

**Grant permissions:**
```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.admin"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:SERVICE_ACCOUNT@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## Setup Microsoft Teams Webhook

### Create Incoming Webhook in Teams

1. **Open Teams Channel**
   - Navigate to the Teams channel where you want to post messages

2. **Add Connector**
   - Click the `...` (More options) next to the channel name
   - Select `Connectors` or `Manage channel`
   - Click `Edit` → `Connectors`

3. **Configure Incoming Webhook**
   - Search for "Incoming Webhook"
   - Click `Configure`
   - Provide a name (e.g., "Cost Alerts")
   - Optionally upload an image
   - Click `Create`

4. **Copy Webhook URL**
   - Copy the webhook URL provided
   - Format: `https://outlook.office.com/webhook/{guid}@{guid}/IncomingWebhook/{guid}/{guid}`
   - Store securely - treat it like a password

5. **Test Webhook**
   ```bash
   curl -X POST "http://localhost:8080/post-team-channel" \
     -H "Content-Type: application/json" \
     -d '{
       "webhook_url": "YOUR_WEBHOOK_URL",
       "message": "Test message from Notification API"
     }'
   ```

## Installation

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API
python main.py

# Or with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Docker

```bash
# Build image
docker build -t notification-api .

# Run container
docker run -p 8080:8080 notification-api
```

### Deploy to Cloud Run

```bash
gcloud run deploy notification-api \
  --source . \
  --region asia-southeast1 \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi
```

## Usage Examples

### Register Teams Channel (Recommended - With Verification)

```python
import requests
from datetime import datetime
import time

# Step 1: Initiate verification
url = "http://localhost:8080/initiate-channel-verification"
payload = {
    "app_code": "cost-alerts",
    "alert_type": "budget-exceeded",
    "url": "https://outlook.office.com/webhook/...",
    "updated_by": "admin@company.com"
}

response = requests.post(url, json=payload)
result = response.json()
print(f"Verification code sent: {result['verification_code']}")
print(f"Expires at: {result['expires_at']}")

# User checks Teams channel and gets the code
# In production, this would come from UI input
verification_code = input("Enter verification code from Teams: ")

# Step 2: Verify channel with code
verify_url = "http://localhost:8080/verify-channel"
verify_payload = {
    "app_code": "cost-alerts",
    "alert_type": "budget-exceeded",
    "verification_code": verification_code,
    "timestamp": datetime.utcnow().isoformat() + "Z"
}

verify_response = requests.post(verify_url, json=verify_payload)
print(verify_response.json())
# Output: {
#   "success": true,
#   "message": "Channel verified and registered successfully",
#   "doc_id": "cost-alerts-budget-exceeded",
#   "verified": true
# }
```

### Register Teams Channel (Legacy - Without Verification)

```python
import requests
from datetime import datetime

# Direct registration (no verification)
url = "http://localhost:8080/add-teams-channel"
payload = {
    "app_code": "cost-alerts",
    "alert_type": "budget-exceeded",
    "url": "https://outlook.office.com/webhook/...",
    "updated_by": "admin@company.com",
    "timestamp": datetime.utcnow().isoformat() + "Z"
}

response = requests.post(url, json=payload)
print(response.json())
```

### Post Message to Teams

```python
import requests

url = "http://localhost:8080/post-team-channel"
payload = {
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Deployment completed successfully!",
    "title": "Deployment Status",
    "color": "00FF00",
    "facts": {
        "Environment": "Production",
        "Version": "v1.2.3",
        "Deployed By": "CI/CD Pipeline"
    }
}

response = requests.post(url, json=payload)
print(response.json())
```

### cURL

```bash
# Simple message
curl -X POST "http://localhost:8080/post-team-channel" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Hello from Notification API!"
  }'

# Formatted message with facts
curl -X POST "http://localhost:8080/post-team-channel" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Cost alert: Budget exceeded",
    "title": "⚠️ Cost Alert",
    "color": "FF0000",
    "facts": {
      "Project": "my-gcp-project",
      "Current Cost": "$1,250",
      "Budget": "$1,000",
      "Overage": "25%"
    }
  }'
```

### JavaScript/TypeScript

```typescript
const response = await fetch('http://localhost:8080/post-team-channel', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    webhook_url: 'https://outlook.office.com/webhook/...',
    message: 'New user registered!',
    title: 'User Registration',
    color: '0078D4',
    facts: {
      'Username': 'john.doe',
      'Email': 'john@example.com',
      'Timestamp': new Date().toISOString()
    }
  })
});

const data = await response.json();
console.log(data);
```

## Adaptive Cards

The API uses **Adaptive Cards v1.4** format for rich, modern Teams messages.

### Card Structure

```json
{
  "type": "message",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "content": {
        "type": "AdaptiveCard",
        "body": [
          {
            "type": "Container",
            "style": "attention",
            "items": [
              {
                "type": "TextBlock",
                "text": "Cost Alert",
                "weight": "bolder",
                "size": "large"
              }
            ]
          },
          {
            "type": "TextBlock",
            "text": "Project XYZ exceeded budget by 20%"
          },
          {
            "type": "FactSet",
            "facts": [
              {"title": "Project", "value": "XYZ"},
              {"title": "Cost", "value": "$1,250"}
            ]
          }
        ],
        "version": "1.4"
      }
    }
  ]
}
```

### Benefits of Adaptive Cards

- ✅ **Modern UI**: Richer visual elements and better styling
- ✅ **Better Support**: Microsoft's recommended format for Teams
- ✅ **Responsive**: Adapts to different screen sizes
- ✅ **Future-Proof**: Long-term support and new features
- ✅ **Consistent**: Same look across Teams desktop, mobile, and web

## Message Colors

The API uses predefined Teams color schemes with automatic validation.

### Predefined Colors (TeamsColor Enum)

| Color Name | Hex Code | Style | Use Case |
|------------|----------|-------|----------|
| `INFO` (default) | `0078D4` | `accent` | Informational messages |
| `SUCCESS` | `28A745` | `good` | Success notifications |
| `WARNING` | `FFC107` | `warning` | Warning alerts |
| `ERROR` | `DC3545` | `attention` | Error messages |
| `CRITICAL` | `8B0000` | `attention` | Critical alerts |

### Usage

**Option 1: Use predefined colors (recommended)**
```python
from dataclass import TeamsColor

payload = {
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Budget exceeded",
    "title": "Cost Alert",
    "color": TeamsColor.ERROR,  # or "DC3545"
    "facts": {"Project": "XYZ"}
}
```

**Option 2: Use custom hex codes**
```python
payload = {
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Custom alert",
    "color": "FF5733"  # Custom orange
}
```

**Option 3: Omit color (uses default INFO blue)**
```python
payload = {
    "webhook_url": "https://outlook.office.com/webhook/...",
    "message": "Default blue message"
    # color is optional, defaults to INFO (0078D4)
}
```

### Color Validation

- Automatically removes `#` prefix if present
- Validates 6-character hex format
- Converts to uppercase
- Defaults to INFO blue if not specified

**Adaptive Card Styles:**
- **accent**: Blue background (info)
- **good**: Green background (success)
- **warning**: Yellow background (warning)
- **attention**: Red background (error/critical)

## Integration Examples

### Cost Alert Integration

```python
from dataclass import TeamsColor
import requests
import os
from datetime import datetime

def send_cost_alert(project_id: str, current_cost: float, budget: float):
    """Send cost alert to Teams with color based on severity"""
    overage_pct = ((current_cost - budget) / budget) * 100
    
    # Choose color based on severity
    if overage_pct > 50:
        color = TeamsColor.CRITICAL
    elif overage_pct > 25:
        color = TeamsColor.ERROR
    else:
        color = TeamsColor.WARNING
    
    payload = {
        "webhook_url": os.getenv("TEAMS_WEBHOOK_URL"),
        "message": f"Project {project_id} has exceeded its budget by {overage_pct:.1f}%",
        "title": "⚠️ Cost Budget Alert",
        "color": color,
        "facts": {
            "Project": project_id,
            "Current Cost": f"${current_cost:,.2f}",
            "Budget": f"${budget:,.2f}",
            "Overage": f"{overage_pct:.1f}%",
            "Alert Time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        }
    }
    
    response = requests.post(
        "http://notification-api:8080/post-team-channel",
        json=payload
    )
    return response.json()
```

### Deployment Notification

```python
from dataclass import TeamsColor

def send_deployment_notification(service: str, version: str, status: str):
    """Send deployment notification to Teams"""
    color = TeamsColor.SUCCESS if status == "success" else TeamsColor.ERROR
    
    payload = {
        "webhook_url": os.getenv("TEAMS_WEBHOOK_URL"),
        "message": f"Deployment of {service} version {version} {status}",
        "title": f"🚀 Deployment {status.title()}",
        "color": color,
        "facts": {
            "Service": service,
            "Version": version,
            "Status": status.upper(),
            "Timestamp": datetime.utcnow().isoformat()
        }
    }
    
    requests.post("http://notification-api:8080/post-team-channel", json=payload)
```

## API Documentation

Once the API is running, visit:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **OpenAPI JSON**: http://localhost:8080/openapi.json

## Retry Logic

The API automatically retries failed requests to Teams webhooks with exponential backoff.

### Retryable Errors

- `502 Bad Gateway` - Teams service temporarily unavailable
- `503 Service Unavailable` - Teams service down
- `504 Gateway Timeout` - Teams webhook timeout
- `429 Too Many Requests` - Rate limit exceeded
- Network errors (`TimeoutException`, `ConnectError`)

### Retry Strategy

- **Maximum retries**: 3 attempts
- **Exponential backoff**: 1s, 2s, 4s (with jitter)
- **Jitter**: Random 0-1s added to prevent thundering herd

### Retry Flow Example

```
Attempt 1: 502 Bad Gateway → Wait 1.2s
Attempt 2: 502 Bad Gateway → Wait 2.5s
Attempt 3: 200 OK → Success ✓
```

### Non-Retryable Errors

- `400 Bad Request` - Invalid webhook URL or message format
- `401 Unauthorized` - Webhook authentication failed
- `404 Not Found` - Webhook deleted or invalid
- Other 4xx errors - Client errors

## Error Handling

The API returns appropriate HTTP status codes:

- `200 OK` - Message posted successfully
- `400 Bad Request` - Invalid request payload
- `502 Bad Gateway` - Teams webhook returned error (after retries)
- `504 Gateway Timeout` - Teams webhook timeout (after retries)
- `500 Internal Server Error` - Unexpected error

**Error Response:**
```json
{
  "detail": "Teams webhook failed with status 400: Invalid webhook URL"
}
```

## Security Considerations

1. **Webhook URL Security**
   - Treat webhook URLs as secrets
   - Don't commit webhook URLs to version control
   - Use environment variables or secret management

2. **API Authentication**
   - For production, add API key authentication
   - Use Cloud Run IAM for GCP deployments
   - Implement rate limiting

3. **Input Validation**
   - All inputs are validated using Pydantic models
   - Message length limits enforced
   - URL validation for webhook URLs

4. **CORS Configuration**
   - Configure `allow_origins` appropriately for production
   - Don't use `*` in production environments

## Monitoring

### Health Checks

```bash
# Check API health
curl http://localhost:8080/health
```

### Logs

```bash
# View Cloud Run logs
gcloud run logs read notification-api \
  --region asia-southeast1 \
  --limit 50
```

## Troubleshooting

### Webhook Returns 400

- Verify webhook URL is correct and active
- Check message format is valid
- Ensure webhook hasn't been deleted in Teams

### Timeout Errors

- Teams webhook may be slow or unavailable
- API has 30-second timeout
- Check network connectivity

### Message Not Appearing in Teams

- Verify webhook is configured for correct channel
- Check Teams connector is enabled
- Test webhook directly with curl

## Future Enhancements

- [ ] Support for Adaptive Cards (modern Teams format)
- [ ] Slack integration
- [ ] Email notifications
- [ ] SMS notifications via Twilio
- [ ] Message templates
- [ ] Retry logic with exponential backoff
- [ ] Message queue for reliability
- [ ] API key authentication
- [ ] Rate limiting
- [ ] Message history/audit log

## License

MIT
