# Deployment Guide - Health Event Monitor

## Prerequisites

1. **Enable Required APIs:**
   ```bash
   gcloud services enable servicehealth.googleapis.com
   gcloud services enable run.googleapis.com
   gcloud services enable firestore.googleapis.com
   gcloud services enable cloudscheduler.googleapis.com
   ```

2. **Create Service Account:**
   ```bash
   gcloud iam service-accounts create health-monitor-sa \
     --display-name="Health Event Monitor Service Account"
   ```

3. **Grant Permissions:**
   ```bash
   # Service Health API access (organization level)
   gcloud organizations add-iam-policy-binding YOUR_ORG_ID \
     --member="serviceAccount:health-monitor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/servicehealth.viewer"
   
   # Firestore access (project level)
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:health-monitor-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --role="roles/datastore.user"
   ```

## Deployment Steps

### 1. Configure Environment

Edit `.env.dev` with your values:
```bash
GCP_PROJECT_ID=your-project-id
ORGANIZATION_ID=your-org-id
FIRESTORE_DATABASE=dashboard
```

### 2. Deploy to Cloud Run

```bash
# Set variables
export PROJECT_ID=your-project-id
export REGION=asia-southeast1

# Deploy as Cloud Run Job
gcloud run jobs deploy health-monitor \
  --source . \
  --region $REGION \
  --set-env-vars ENVIRONMENT=prod \
  --service-account health-monitor-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --max-retries 3 \
  --task-timeout 10m \
  --memory 512Mi \
  --cpu 1
```

### 3. Test the Job

```bash
# Execute the job manually
gcloud run jobs execute health-monitor --region $REGION

# Check logs
gcloud run jobs executions logs read \
  --job health-monitor \
  --region $REGION \
  --limit 50
```

### 4. Schedule with Cloud Scheduler

```bash
# Create scheduler job (runs every 15 minutes)
gcloud scheduler jobs create http health-monitor-schedule \
  --location $REGION \
  --schedule "*/15 * * * *" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/health-monitor:run" \
  --http-method POST \
  --oauth-service-account-email health-monitor-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --time-zone "Asia/Singapore"
```

### 5. Verify Deployment

```bash
# Check Firestore collections
gcloud firestore databases list

# Query region status
gcloud firestore documents list \
  --database=dashboard \
  --collection-ids=region_status
```

## Configuration Options

### Schedule Frequencies

| Frequency | Cron Expression | Use Case |
|-----------|----------------|----------|
| Every 5 min | `*/5 * * * *` | Critical monitoring |
| Every 15 min | `*/15 * * * *` | Standard monitoring (recommended) |
| Every 30 min | `*/30 * * * *` | Light monitoring |
| Hourly | `0 * * * *` | Periodic checks |

### Resource Configuration

For different scales:

**Small (< 50 events):**
```bash
--memory 512Mi --cpu 1
```

**Medium (50-200 events):**
```bash
--memory 1Gi --cpu 1
```

**Large (200+ events):**
```bash
--memory 2Gi --cpu 2
```

## Environment-Specific Deployment

### Development
```bash
gcloud run jobs deploy health-monitor-dev \
  --source . \
  --region $REGION \
  --set-env-vars ENVIRONMENT=dev \
  --service-account health-monitor-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

### Production
```bash
gcloud run jobs deploy health-monitor-prod \
  --source . \
  --region $REGION \
  --set-env-vars ENVIRONMENT=prod \
  --service-account health-monitor-sa@${PROJECT_ID}.iam.gserviceaccount.com
```

## Monitoring & Alerts

### Set Up Log-Based Alerts

1. **Alert on Unhealthy Regions:**
   ```bash
   gcloud logging metrics create unhealthy_regions \
     --description="Count of unhealthy regions" \
     --log-filter='resource.type="cloud_run_job"
     resource.labels.job_name="health-monitor"
     jsonPayload.message=~"Unhealthy regions"'
   ```

2. **Alert on Job Failures:**
   ```bash
   gcloud logging metrics create health_monitor_failures \
     --description="Health monitor job failures" \
     --log-filter='resource.type="cloud_run_job"
     resource.labels.job_name="health-monitor"
     severity="ERROR"'
   ```

### Create Alert Policies

```bash
# Alert when regions become unhealthy
gcloud alpha monitoring policies create \
  --notification-channels=YOUR_CHANNEL_ID \
  --display-name="Unhealthy Regions Alert" \
  --condition-display-name="Region Health Check" \
  --condition-threshold-value=1 \
  --condition-threshold-duration=60s
```

## Updating the Job

```bash
# Update code
gcloud run jobs update health-monitor \
  --source . \
  --region $REGION

# Update environment variables
gcloud run jobs update health-monitor \
  --region $REGION \
  --set-env-vars REGIONS=asia-southeast1,asia-southeast2,global
```

## Rollback

```bash
# List revisions
gcloud run jobs revisions list --job health-monitor --region $REGION

# Rollback to previous revision
gcloud run jobs update health-monitor \
  --region $REGION \
  --revision REVISION_NAME
```

## Troubleshooting

### Check Job Status
```bash
gcloud run jobs describe health-monitor --region $REGION
```

### View Recent Executions
```bash
gcloud run jobs executions list \
  --job health-monitor \
  --region $REGION \
  --limit 10
```

### Check Logs
```bash
# Real-time logs
gcloud run jobs executions logs tail \
  --job health-monitor \
  --region $REGION

# Historical logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=health-monitor" \
  --limit 50 \
  --format json
```

### Common Issues

**Issue: Permission Denied**
```
Solution: Verify service account has roles/servicehealth.viewer at org level
```

**Issue: No Events Found**
```
Solution: Check organization ID and verify Service Health API is enabled
```

**Issue: Firestore Write Errors**
```
Solution: Verify service account has roles/datastore.user
```

## Cost Optimization

1. **Adjust Schedule**: Run less frequently if real-time monitoring isn't critical
2. **Reduce Timeout**: Set `--task-timeout 5m` if job completes faster
3. **Right-size Resources**: Use `--memory 512Mi` if handling few events

## Security Best Practices

1. ✅ Use dedicated service account with minimal permissions
2. ✅ Enable VPC Service Controls (optional)
3. ✅ Use Secret Manager for sensitive configs (if needed)
4. ✅ Enable audit logging
5. ✅ Restrict Firestore access with security rules

## Cleanup

To remove the deployment:

```bash
# Delete Cloud Scheduler job
gcloud scheduler jobs delete health-monitor-schedule --location $REGION

# Delete Cloud Run job
gcloud run jobs delete health-monitor --region $REGION

# Delete service account (optional)
gcloud iam service-accounts delete health-monitor-sa@${PROJECT_ID}.iam.gserviceaccount.com
```
