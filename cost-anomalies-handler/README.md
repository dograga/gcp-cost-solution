# Cost Anomalies Handler

FastAPI service that receives GCP cost anomaly notifications via Pub/Sub, enriches them with project metadata (appcode, lob), and stores them in Firestore.

## Overview

This service acts as a Pub/Sub push endpoint that:
1. Receives cost anomaly messages from GCP Cost Anomaly Detection
2. Enriches anomalies with project metadata from Firestore
3. Stores enriched anomalies in a Firestore collection

## Architecture

```
GCP Cost Anomaly Detection
          ↓
    Pub/Sub Topic
          ↓
   Push Subscription
          ↓
   FastAPI Handler (this service)
          ↓
    Firestore (enriched anomalies)
```

## Features

- **Pub/Sub Push Endpoint**: Receives anomaly notifications via HTTP POST
- **Project Enrichment**: Enriches anomalies with appcode and lob from project metadata
- **Caching**: Caches enrichment data for performance
- **Health Checks**: `/health` endpoint for monitoring
- **Direct API**: `/anomaly` endpoint for testing
- **Error Handling**: Proper HTTP status codes for Pub/Sub retry logic

## Configuration

### Environment Variables (.env.dev)

```bash
# GCP Project
GCP_PROJECT_ID=evol-dev-456410

# Firestore Configuration
FIRESTORE_DATABASE=cost-db
FIRESTORE_COLLECTION=cost_anomalies_dev

# Project Enrichment Configuration
ENRICHMENT_DATABASE=dashboard
ENRICHMENT_COLLECTION=projects
ENRICHMENT_PROJECT_ID_FIELD=project_id
ENRICHMENT_FIELDS=appcode,lob

# Logging
LOG_LEVEL=INFO
```

## API Endpoints

### `GET /`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "cost-anomaly-handler",
  "version": "1.0.0"
}
```

### `GET /health`
Detailed health check with cache status.

**Response:**
```json
{
  "status": "healthy",
  "firestore_database": "cost-db",
  "enrichment_database": "dashboard",
  "enrichment_cache_loaded": true,
  "enrichment_projects_count": 150
}
```

### `POST /pubsub/push`
Receives Pub/Sub push notifications.

**Request Body:**
```json
{
  "message": {
    "data": "<base64-encoded-anomaly-json>",
    "messageId": "123456",
    "publishTime": "2025-10-28T12:00:00Z"
  },
  "subscription": "projects/PROJECT/subscriptions/SUBSCRIPTION"
}
```

**Response:**
```json
{
  "status": "success",
  "document_id": "anomaly-123",
  "message": "Anomaly processed and saved"
}
```

### `POST /anomaly`
Direct endpoint for creating anomalies (testing).

**Request Body:**
```json
{
  "anomaly_id": "test-123",
  "project_id": "my-project",
  "cost_change": 150.50,
  "currency": "USD",
  "description": "Cost spike detected"
}
```

### `POST /reload-enrichment`
Reload enrichment data cache.

**Response:**
```json
{
  "status": "success",
  "projects_loaded": 150,
  "message": "Enrichment cache reloaded"
}
```

## Anomaly Data Structure

### Input (from Pub/Sub)
```json
{
  "anomaly_id": "abc123",
  "project_id": "my-gcp-project",
  "cost_change": 250.75,
  "currency": "USD",
  "percentage_change": 85.5,
  "service": "Compute Engine",
  "start_time": "2025-10-27T00:00:00Z",
  "end_time": "2025-10-28T00:00:00Z",
  "description": "Unusual cost increase detected"
}
```

### Output (stored in Firestore)
```json
{
  "anomaly_id": "abc123",
  "project_id": "my-gcp-project",
  "cost_change": 250.75,
  "currency": "USD",
  "percentage_change": 85.5,
  "service": "Compute Engine",
  "start_time": "2025-10-27T00:00:00Z",
  "end_time": "2025-10-28T00:00:00Z",
  "description": "Unusual cost increase detected",
  "appcode": "APP001",
  "lob": "Engineering",
  "processed_at": "2025-10-28T12:30:00Z",
  "handler_version": "1.0.0"
}
```

## Local Development

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Locally

```bash
# Set environment
export ENVIRONMENT=dev

# Run the service
python main.py
```

The service will start on `http://localhost:8080`

### Test with curl

```bash
# Health check
curl http://localhost:8080/health

# Test direct anomaly creation
curl -X POST http://localhost:8080/anomaly \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly_id": "test-123",
    "project_id": "my-project",
    "cost_change": 150.50,
    "currency": "USD"
  }'

# Test Pub/Sub push (base64 encode the JSON first)
echo '{"anomaly_id":"test-456","project_id":"my-project"}' | base64
curl -X POST http://localhost:8080/pubsub/push \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "data": "eyJhbm9tYWx5X2lkIjoidGVzdC00NTYiLCJwcm9qZWN0X2lkIjoibXktcHJvamVjdCJ9Cg==",
      "messageId": "test-msg-1",
      "publishTime": "2025-10-28T12:00:00Z"
    },
    "subscription": "test-sub"
  }'
```

## Deployment

### Deploy to Cloud Run

```bash
# Build and deploy
gcloud run deploy cost-anomalies-handler \
  --source . \
  --region asia-southeast1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars ENVIRONMENT=prod \
  --service-account anomaly-handler-sa@PROJECT_ID.iam.gserviceaccount.com \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 10
```

### Create Pub/Sub Push Subscription

```bash
# Get the Cloud Run service URL
SERVICE_URL=$(gcloud run services describe cost-anomalies-handler \
  --region asia-southeast1 \
  --format 'value(status.url)')

# Create push subscription
gcloud pubsub subscriptions create cost-anomalies-subscription \
  --topic=cost-anomalies-dev \
  --push-endpoint="${SERVICE_URL}/pubsub/push" \
  --ack-deadline=60 \
  --message-retention-duration=7d \
  --max-delivery-attempts=5
```

## IAM Permissions

### Service Account Permissions

```yaml
roles/datastore.user          # Read/write Firestore
roles/logging.logWriter        # Write logs
```

Grant permissions:
```bash
# Firestore access (both databases)
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:anomaly-handler-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

# Logging
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:anomaly-handler-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

### Pub/Sub Push Authentication

For authenticated push subscriptions:
```bash
gcloud run services add-iam-policy-binding cost-anomalies-handler \
  --region=asia-southeast1 \
  --member="serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## Monitoring

### Check Logs

```bash
gcloud run services logs read cost-anomalies-handler \
  --region asia-southeast1 \
  --limit 50
```

### Monitor Metrics

- **Request Count**: Number of anomalies processed
- **Error Rate**: Failed processing attempts
- **Latency**: Processing time per anomaly
- **Cache Hit Rate**: Enrichment cache effectiveness

## Troubleshooting

### No Anomalies Appearing

1. Check Pub/Sub subscription is delivering messages:
   ```bash
   gcloud pubsub subscriptions describe cost-anomalies-subscription
   ```

2. Check Cloud Run logs for errors:
   ```bash
   gcloud run services logs read cost-anomalies-handler --region asia-southeast1
   ```

3. Verify service is healthy:
   ```bash
   curl https://YOUR-SERVICE-URL/health
   ```

### Enrichment Data Not Loading

1. Verify Firestore database and collection names
2. Check service account has `datastore.user` role
3. Reload cache manually:
   ```bash
   curl -X POST https://YOUR-SERVICE-URL/reload-enrichment
   ```

### Pub/Sub Messages Failing

- Check message format matches expected structure
- Verify base64 encoding is correct
- Check for JSON parsing errors in logs
- Ensure anomaly data includes required fields

## Cost

- **Cloud Run**: ~$0.01 per 1000 requests
- **Firestore**: ~$0.18 per 100K writes
- **Pub/Sub**: ~$0.40 per million messages

**Estimated cost: ~$5-10/month** for typical usage

## Best Practices

1. **Caching**: Enrichment data is cached on first load
2. **Idempotency**: Uses anomaly_id as document ID to prevent duplicates
3. **Error Handling**: Returns proper HTTP codes for Pub/Sub retry logic
4. **Logging**: Comprehensive logging for debugging
5. **Health Checks**: Regular health monitoring via `/health` endpoint
