# GCP Health Event Monitor

## Overview

This Cloud Run job monitors Google Cloud Service Health events for your organization and stores them in Firestore. It tracks regional health status and maintains a collection of active events.

## Features

- ✅ Monitors organization-level health events via Service Health API
- ✅ Filters events by region (Singapore, Jakarta, Mumbai, Delhi, Global)
- ✅ Filters events by GCP products/services (Compute, GKE, Storage, SQL, etc.)
- ✅ Maintains two Firestore collections:
  - **region_status**: Regional health status summary
  - **health_events**: Detailed event information
- ✅ Automatic cleanup of resolved events
- ✅ Upserts events using event ID (idempotent)
- ✅ Configurable via environment variables

## Collections

### 1. region_status Collection

Stores the health status of each monitored region.

**Document Structure:**
```json
{
  "region": "asia-southeast1",
  "status": "unhealthy",
  "event_count": 2,
  "last_updated": "2025-10-25T12:00:00Z"
}
```

**Fields:**
- `region`: Region identifier (e.g., "asia-southeast1", "global")
- `status`: "healthy" or "unhealthy" (unhealthy if event_count > 0)
- `event_count`: Number of active events affecting this region
- `last_updated`: Timestamp of last update

**Document ID:** Region name (e.g., "asia-southeast1")

### 2. health_events Collection

Stores detailed information about each active event.

**Document Structure:**
```json
{
  "event_id": "abc123",
  "event_name": "organizations/123/locations/global/organizationEvents/abc123",
  "title": "Service Disruption in asia-southeast1",
  "description": "We are experiencing elevated error rates...",
  "category": "INCIDENT",
  "state": "ACTIVE",
  "detailed_category": "SERVICE_OUTAGE",
  "detailed_state": "EMERGING",
  "start_time": "2025-10-25T10:00:00Z",
  "end_time": null,
  "update_time": "2025-10-25T11:30:00Z",
  "impacts": [
    {
      "product": "Google Compute Engine",
      "location": "asia-southeast1"
    }
  ],
  "locations": ["asia-southeast1"],
  "affected_regions": ["asia-southeast1"],
  "collected_at": "2025-10-25T12:00:00Z"
}
```

**Document ID:** Event ID (e.g., "abc123")

## Configuration

### Environment Variables (.env.dev)

```bash
# GCP Project
GCP_PROJECT_ID=your-project-id

# Organization Configuration
ORGANIZATION_ID=your-org-id

# Firestore Configuration
FIRESTORE_DATABASE=dashboard
REGION_STATUS_COLLECTION=region_status
EVENTS_COLLECTION=health_events

# Regions to Monitor (comma-separated)
REGIONS=asia-southeast1,asia-southeast2,asia-south1,asia-south2,global

# Event Categories (leave empty for all)
EVENT_CATEGORIES=

# Product Filtering (set to True to enable, False to disable)
FILTER_BY_PRODUCT=True

# Products/Services to Monitor (comma-separated, only used if FILTER_BY_PRODUCT=True)
PRODUCTS=Google Compute Engine,Google Kubernetes Engine,Cloud Storage,Cloud SQL,Cloud Networking,Cloud Security,Cloud Logging,Cloud DNS,Vertex AI,Cloud Identity,Cloud Billing,Cloud Pub/Sub,Cloud Memorystore,BigQuery,Cloud Dataproc

# Logging
LOG_LEVEL=INFO
```

### Region Mapping

| Region Code | Location |
|-------------|----------|
| asia-southeast1 | Singapore |
| asia-southeast2 | Jakarta, Indonesia |
| asia-south1 | Mumbai, India |
| asia-south2 | Delhi, India |
| global | Global events |

### Product/Service Mapping

The following GCP products/services are monitored:

| Product Name | Service |
|--------------|---------|
| Google Compute Engine | Compute VMs |
| Google Kubernetes Engine | GKE Clusters |
| Cloud Storage | Object Storage |
| Cloud SQL | Managed Databases |
| Cloud Networking | VPC, Load Balancers |
| Cloud Security | Security Services |
| Cloud Logging | Logging & Monitoring |
| Cloud DNS | DNS Management |
| Vertex AI | AI/ML Platform |
| Cloud Identity | Identity & Access |
| Cloud Billing | Billing Services |
| Cloud Pub/Sub | Messaging |
| Cloud Memorystore | Redis |
| BigQuery | Data Warehouse |
| Cloud Dataproc | Spark/Hadoop |

**Note:** 
- Set `FILTER_BY_PRODUCT=True` to enable product filtering, `False` to disable
- Product filtering uses flexible matching (case-insensitive, partial matches)
- When disabled, all products are monitored regardless of the `PRODUCTS` list

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.dev .env.prod  # For production
   # Edit .env.prod with your values
   ```

3. **Run locally:**
   ```bash
   python main.py
   ```

## Deployment

### Deploy as Cloud Run Job

```bash
gcloud run jobs create health-monitor \
  --source . \
  --region asia-southeast1 \
  --set-env-vars ENVIRONMENT=prod \
  --service-account health-monitor-sa@PROJECT_ID.iam.gserviceaccount.com \
  --max-retries 3 \
  --task-timeout 10m
```

### Schedule with Cloud Scheduler

```bash
gcloud scheduler jobs create http health-monitor-schedule \
  --location asia-southeast1 \
  --schedule "*/15 * * * *" \
  --uri "https://asia-southeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/health-monitor:run" \
  --http-method POST \
  --oauth-service-account-email health-monitor-sa@PROJECT_ID.iam.gserviceaccount.com
```

**Recommended Schedule:** Every 15 minutes for near real-time monitoring

## Required IAM Permissions

The service account needs:

```yaml
roles/servicehealth.viewer          # Read organization events
roles/datastore.user                # Write to Firestore
```

Grant permissions:
```bash
# Service Health API access
gcloud organizations add-iam-policy-binding ORG_ID \
  --member="serviceAccount:health-monitor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/servicehealth.viewer"

# Firestore access
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:health-monitor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## How It Works

1. **Fetch Events**: Queries Service Health API for organization events
2. **Filter by Region**: Includes only events affecting monitored regions
3. **Filter by Product**: Includes only events affecting monitored GCP services (if specified)
4. **Save Events**: Upserts events to `health_events` collection using event ID
5. **Cleanup**: Removes events that are no longer active
6. **Update Status**: Calculates event count per region and updates `region_status`

## Event Lifecycle

```
Active Event → Saved to Firestore → Region marked unhealthy
     ↓
Event Resolved → Removed from Firestore → Region marked healthy (if no other events)
```

## Monitoring

### Check Regional Status

```python
from google.cloud import firestore

db = firestore.Client(database='dashboard')
regions = db.collection('region_status').stream()

for region in regions:
    data = region.to_dict()
    print(f"{data['region']}: {data['status']} ({data['event_count']} events)")
```

### Query Active Events

```python
events = db.collection('health_events').stream()

for event in events:
    data = event.to_dict()
    print(f"{data['title']} - {data['affected_regions']}")
```

## Logging

The job logs:
- Number of events collected
- Regions marked as unhealthy
- Events added/removed
- Any errors encountered

Example output:
```
2025-10-25 12:00:00 - INFO - Collected 3 events from Service Health API
2025-10-25 12:00:01 - INFO - Successfully saved 3 events to Firestore
2025-10-25 12:00:02 - INFO - Removed 1 old events from Firestore
2025-10-25 12:00:03 - INFO - Updated status for 5 regions
2025-10-25 12:00:03 - WARNING - Unhealthy regions: ['asia-southeast1', 'global']
```

## Troubleshooting

### No Events Found

- Verify organization ID is correct
- Check service account has `roles/servicehealth.viewer` on organization
- Ensure Service Health API is enabled

### Permission Denied

- Grant `roles/servicehealth.viewer` at organization level
- Grant `roles/datastore.user` at project level

### Events Not Appearing

- Check region filter in configuration
- Verify events affect monitored regions
- Check product filter - ensure the affected services are in your PRODUCTS list
- Verify events affect monitored products/services
- Check event state (only ACTIVE events are collected)

## Cost

- **Service Health API**: Free
- **Firestore**: ~$0.18 per 100K writes
- **Cloud Run**: ~$0.01 per run (minimal compute)

**Estimated cost for 15-min schedule: ~$2-3/month**

## Best Practices

1. ✅ Run every 15 minutes for timely alerts
2. ✅ Monitor logs for unhealthy regions
3. ✅ Set up alerts on region_status changes
4. ✅ Use INFO logging in production
5. ✅ Keep event history for analysis (optional: add archive collection)
