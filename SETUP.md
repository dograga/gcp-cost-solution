# Setup Guide

This guide will walk you through setting up the GCP Cost Solution from scratch.

## Prerequisites

- GCP Organization or Billing Account access
- `gcloud` CLI installed and configured
- Docker installed (for building images)
- Python 3.11+ (for local development)

## Step 1: Create GCP Projects

Create separate projects for each environment (optional but recommended):

```bash
# Development
gcloud projects create your-dev-project-id --name="Cost Solution Dev"

# UAT
gcloud projects create your-uat-project-id --name="Cost Solution UAT"

# Production
gcloud projects create your-prod-project-id --name="Cost Solution Prod"
```

## Step 2: Enable Required APIs

For each project:

```bash
export PROJECT_ID=your-project-id

gcloud config set project ${PROJECT_ID}

# Enable required APIs
gcloud services enable cloudbilling.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

## Step 3: Configure Billing Export (Recommended)

For detailed cost data, configure billing export:

1. Go to [GCP Console → Billing](https://console.cloud.google.com/billing)
2. Select your billing account
3. Go to "Billing export" → "BigQuery export"
4. Click "Edit settings" for "Detailed usage cost"
5. Select project and dataset (e.g., `billing_data`)
6. Click "Save"

## Step 4: Create Service Accounts

### For cost-cron job:

```bash
export PROJECT_ID=your-project-id

# Create service account
gcloud iam service-accounts create billing-collector \
  --display-name="Billing Data Collector" \
  --project=${PROJECT_ID}

# Grant billing viewer permissions at organization level
export ORG_ID=your-org-id
gcloud organizations add-iam-policy-binding ${ORG_ID} \
  --member="serviceAccount:billing-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/billing.viewer"

# Grant BigQuery permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

### For cost-processor job:

```bash
# Create service account
gcloud iam service-accounts create billing-processor \
  --display-name="Billing Data Processor" \
  --project=${PROJECT_ID}

# Grant BigQuery permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-processor@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-processor@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Grant Firestore permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-processor@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## Step 5: Initialize Firestore

```bash
# Create Firestore database (if not already created)
gcloud firestore databases create --location=us-central --project=${PROJECT_ID}
```

## Step 6: Configure Environment Files

### For cost-cron:

```bash
cd cost-cron

# Copy example file
cp .env.example .env.prd

# Edit .env.prd with your values
# Update GCP_PROJECT_ID and other settings
```

Example `.env.prd`:
```bash
GCP_PROJECT_ID=your-prod-project-id
BQ_DATASET_ID=billing_data
BQ_TABLE_ID=daily_costs
BQ_LOCATION=US
BILLING_EXPORT_DATASET=billing_data
BILLING_EXPORT_TABLE_PREFIX=gcp_billing_export
LOG_LEVEL=INFO
```

### For cost-processor:

```bash
cd cost-processor

# Copy example file
cp .env.example .env.prd

# Edit .env.prd with your values
```

Example `.env.prd`:
```bash
GCP_PROJECT_ID=your-prod-project-id
SOURCE_DATASET_ID=billing_data
SOURCE_TABLE_ID=daily_costs
OUTPUT_DATASET_ID=billing_reports
BQ_LOCATION=US
FIRESTORE_PROJECT_ID=your-prod-project-id
FIRESTORE_DATABASE=(default)
FIRESTORE_COLLECTION_PREFIX=cost_reports
DAYS_BACK=30
TOP_COST_DRIVERS_COUNT=20
TOP_COST_DRIVERS_DAYS=7
LOG_LEVEL=INFO
```

## Step 7: Build and Deploy

### Deploy cost-cron:

```bash
cd cost-cron
export PROJECT_ID=your-prod-project-id

# Build and push Docker image
docker build -t gcr.io/${PROJECT_ID}/cost-cron:latest .
docker push gcr.io/${PROJECT_ID}/cost-cron:latest

# Deploy Cloud Run Job
gcloud run jobs create cost-cron \
  --image gcr.io/${PROJECT_ID}/cost-cron:latest \
  --region us-central1 \
  --service-account billing-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=prd \
  --max-retries 3 \
  --task-timeout 30m \
  --project ${PROJECT_ID}

# Test the job manually
gcloud run jobs execute cost-cron --region us-central1 --project ${PROJECT_ID}
```

### Deploy cost-processor:

```bash
cd cost-processor
export PROJECT_ID=your-prod-project-id

# Build and push Docker image
docker build -t gcr.io/${PROJECT_ID}/cost-processor:latest .
docker push gcr.io/${PROJECT_ID}/cost-processor:latest

# Deploy Cloud Run Job
gcloud run jobs create cost-processor \
  --image gcr.io/${PROJECT_ID}/cost-processor:latest \
  --region us-central1 \
  --service-account billing-processor@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=prd \
  --max-retries 2 \
  --task-timeout 20m \
  --project ${PROJECT_ID}

# Test the job manually (after cost-cron has run)
gcloud run jobs execute cost-processor --region us-central1 --project ${PROJECT_ID}
```

## Step 8: Schedule Jobs

### Schedule cost-cron (daily at 1 AM UTC):

```bash
gcloud scheduler jobs create http cost-cron-daily \
  --location us-central1 \
  --schedule "0 1 * * *" \
  --time-zone "UTC" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-cron:run" \
  --http-method POST \
  --oauth-service-account-email billing-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --project ${PROJECT_ID}
```

### Schedule cost-processor (daily at 2 AM UTC):

```bash
gcloud scheduler jobs create http cost-processor-daily \
  --location us-central1 \
  --schedule "0 2 * * *" \
  --time-zone "UTC" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-processor:run" \
  --http-method POST \
  --oauth-service-account-email billing-processor@${PROJECT_ID}.iam.gserviceaccount.com \
  --project ${PROJECT_ID}
```

## Step 9: Verify Setup

### Check BigQuery:

```bash
# List datasets
bq ls --project_id=${PROJECT_ID}

# Check if tables exist (after first run)
bq ls ${PROJECT_ID}:billing_data
bq ls ${PROJECT_ID}:billing_reports
```

### Check Firestore:

```bash
# List collections (after first processor run)
gcloud firestore collections list --project=${PROJECT_ID}
```

### View Logs:

```bash
# cost-cron logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-cron" \
  --limit 20 \
  --project ${PROJECT_ID}

# cost-processor logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-processor" \
  --limit 20 \
  --project ${PROJECT_ID}
```

## Step 10: Query Reports

### BigQuery Console:

Go to [BigQuery Console](https://console.cloud.google.com/bigquery) and run:

```sql
-- View project costs
SELECT * FROM `your-project.billing_reports.project_cost_summary`
ORDER BY total_cost DESC
LIMIT 10;

-- View daily trends
SELECT 
  date,
  total_cost,
  active_projects
FROM `your-project.billing_reports.daily_cost_trends`
ORDER BY date DESC
LIMIT 30;
```

### Firestore Console:

Go to [Firestore Console](https://console.cloud.google.com/firestore) and browse collections:
- `cost_reports_project_cost_summary`
- `cost_reports_service_cost_summary`
- `cost_reports_metadata`

## Troubleshooting

### Job fails with permission errors:
- Verify service account has all required roles
- Check organization-level billing permissions
- Ensure APIs are enabled

### No data in BigQuery:
- Check if billing export is configured
- Verify cost-cron job completed successfully
- Check logs for errors

### Firestore empty:
- Ensure cost-processor ran after cost-cron
- Check Firestore permissions
- Verify Firestore database is created

### Configuration not loading:
- Verify `.env.{ENVIRONMENT}` file exists in the Docker image
- Check `ENVIRONMENT` variable is set correctly
- Review container logs for config loading messages

## Multi-Environment Setup

To deploy to multiple environments (dev, uat, prd):

1. Create separate projects for each environment
2. Create environment-specific .env files (.env.dev, .env.uat, .env.prd)
3. Deploy with different ENVIRONMENT variables:

```bash
# Development
gcloud run jobs create cost-cron-dev \
  --image gcr.io/${DEV_PROJECT_ID}/cost-cron:latest \
  --set-env-vars ENVIRONMENT=dev \
  ...

# UAT
gcloud run jobs create cost-cron-uat \
  --image gcr.io/${UAT_PROJECT_ID}/cost-cron:latest \
  --set-env-vars ENVIRONMENT=uat \
  ...

# Production
gcloud run jobs create cost-cron \
  --image gcr.io/${PROD_PROJECT_ID}/cost-cron:latest \
  --set-env-vars ENVIRONMENT=prd \
  ...
```

## Next Steps

1. Set up monitoring and alerting for job failures
2. Create dashboards in Looker Studio or Data Studio
3. Set up cost anomaly detection
4. Configure budget alerts
5. Create API endpoints to serve Firestore data

## Support

For issues or questions, check:
- Job execution logs in Cloud Logging
- BigQuery job history
- Cloud Run job execution history
