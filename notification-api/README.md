# Notification API

FastAPI-based notification service for posting messages to Microsoft Teams channels via webhooks.

## Overview

This API provides endpoints to send formatted messages to Microsoft Teams channels. It handles webhook authentication and message formatting automatically.

## Features

- **FastAPI Framework**: Modern, fast, async API framework
- **Teams Integration**: Post messages to Teams channels via webhooks
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

### Python

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

## Message Colors

Common color codes for different message types:

- **Info**: `0078D4` (Microsoft Blue)
- **Success**: `00FF00` or `28A745` (Green)
- **Warning**: `FFA500` or `FFC107` (Orange/Yellow)
- **Error**: `FF0000` or `DC3545` (Red)
- **Critical**: `8B0000` (Dark Red)

## Integration Examples

### Cost Alert Integration

```python
# From cost-anomalies-handler
import requests

def send_cost_alert(project_id: str, current_cost: float, budget: float):
    """Send cost alert to Teams."""
    overage_pct = ((current_cost - budget) / budget) * 100
    
    payload = {
        "webhook_url": os.getenv("TEAMS_WEBHOOK_URL"),
        "message": f"Project {project_id} has exceeded its budget by {overage_pct:.1f}%",
        "title": "⚠️ Cost Budget Alert",
        "color": "FF0000" if overage_pct > 50 else "FFA500",
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
def send_deployment_notification(service: str, version: str, status: str):
    """Send deployment notification to Teams."""
    color = "00FF00" if status == "success" else "FF0000"
    
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
