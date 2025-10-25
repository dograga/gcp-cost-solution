# Quick Start Guide

## 5-Minute Setup

### 1. Configure Environment

Edit `.env.dev`:
```bash
GCP_PROJECT_ID=evol-dev-456410
ORGANIZATION_ID=922071633244
FIRESTORE_DATABASE=dashboard
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Test Locally

```bash
python main.py
```

### 4. Check Results

**View Region Status:**
```python
from google.cloud import firestore

db = firestore.Client(project='evol-dev-456410', database='dashboard')

# Check region status
for doc in db.collection('region_status').stream():
    data = doc.to_dict()
    print(f"{data['region']}: {data['status']} - {data['event_count']} events")
```

**View Events:**
```python
# Check events
for doc in db.collection('health_events').stream():
    data = doc.to_dict()
    print(f"{data['title']} - Regions: {data['affected_regions']}")
```

## Expected Output

### Healthy State
```
2025-10-25 12:00:00 - INFO - Collected 0 events from Service Health API
2025-10-25 12:00:01 - INFO - No events to save
2025-10-25 12:00:02 - INFO - Updated status for 5 regions
2025-10-25 12:00:02 - INFO - All monitored regions are healthy
```

### Unhealthy State
```
2025-10-25 12:00:00 - INFO - Collected 3 events from Service Health API
2025-10-25 12:00:01 - INFO - Successfully saved 3 events to Firestore
2025-10-25 12:00:02 - INFO - Updated status for 5 regions
2025-10-25 12:00:02 - WARNING - Unhealthy regions: ['asia-southeast1', 'global']
```

## Firestore Collections

### region_status
```
Document ID: asia-southeast1
{
  "region": "asia-southeast1",
  "status": "unhealthy",
  "event_count": 2,
  "last_updated": "2025-10-25T12:00:00Z"
}
```

### health_events
```
Document ID: abc123
{
  "event_id": "abc123",
  "title": "Service Disruption",
  "category": "INCIDENT",
  "state": "ACTIVE",
  "affected_regions": ["asia-southeast1"],
  "start_time": "2025-10-25T10:00:00Z",
  ...
}
```

## Deploy to Cloud Run

```bash
# Quick deploy
gcloud run jobs deploy health-monitor \
  --source . \
  --region asia-southeast1 \
  --set-env-vars ENVIRONMENT=prod \
  --service-account health-monitor-sa@evol-dev-456410.iam.gserviceaccount.com

# Schedule (every 15 minutes)
gcloud scheduler jobs create http health-monitor-schedule \
  --location asia-southeast1 \
  --schedule "*/15 * * * *" \
  --uri "https://asia-southeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/evol-dev-456410/jobs/health-monitor:run" \
  --http-method POST \
  --oauth-service-account-email health-monitor-sa@evol-dev-456410.iam.gserviceaccount.com
```

## Next Steps

1. ✅ Set up monitoring alerts on region_status changes
2. ✅ Create dashboard to visualize regional health
3. ✅ Configure notification channels for unhealthy regions
4. ✅ Review logs regularly for patterns

## Troubleshooting

**No events collected?**
- Verify organization ID is correct
- Check service account has `roles/servicehealth.viewer`

**Permission denied?**
- Grant permissions at organization level (see DEPLOYMENT.md)

**Events not filtered correctly?**
- Check REGIONS configuration in .env.dev
- Verify region names match GCP region codes

## Support

See detailed documentation:
- [README.md](README.md) - Full documentation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [config.py](config.py) - Configuration options
