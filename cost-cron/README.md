# GCP Cost Collection Cron Job

This Cloud Run job collects Google Cloud billing data from all accessible billing accounts and stores it in BigQuery. It's designed to run daily and collect the previous day's cost data (00:00 to 23:59).

## Features

- **Multi-Account Support**: Automatically discovers and processes all accessible billing accounts
- **BigQuery Integration**: Stores cost data in a partitioned BigQuery table for efficient querying
- **Dual Collection Methods**: 
  - Primary: Queries from billing export tables (recommended)
  - Fallback: Direct API collection when export is unavailable
- **Automatic Resource Creation**: Creates BigQuery dataset and table if they don't exist
- **Comprehensive Logging**: Detailed logs for monitoring and debugging

## Prerequisites

1. **GCP Project** with billing enabled
2. **Service Account** with the following permissions:
   - `billing.accounts.list`
   - `billing.accounts.get`
   - `billing.resourceCosts.get`
   - `bigquery.datasets.create`
   - `bigquery.tables.create`
   - `bigquery.tables.updateData`
3. **Billing Export** (recommended): Configure billing export to BigQuery for detailed cost data
   - Go to Billing → Billing Export → BigQuery Export
   - Enable "Detailed usage cost" export

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | Yes | - | GCP project ID where BigQuery table will be created |
| `BQ_DATASET_ID` | No | `billing_data` | BigQuery dataset name |
| `BQ_TABLE_ID` | No | `daily_costs` | BigQuery table name |

## BigQuery Schema

The job creates a table with the following schema:

```
- billing_account_id (STRING, REQUIRED)
- billing_account_name (STRING)
- date (DATE, REQUIRED) - Partitioned field
- project_id (STRING)
- project_name (STRING)
- service_description (STRING)
- sku_description (STRING)
- usage_start_time (TIMESTAMP)
- usage_end_time (TIMESTAMP)
- cost (FLOAT64)
- currency (STRING)
- usage_amount (FLOAT64)
- usage_unit (STRING)
- credits (FLOAT64)
- location_region (STRING)
- location_zone (STRING)
- labels (STRING)
- collected_at (TIMESTAMP, REQUIRED)
```

## Deployment

### 1. Build and Push Docker Image

```bash
cd cost-cron

# Set your project ID
export PROJECT_ID=your-project-id

# Build the image
docker build -t gcr.io/${PROJECT_ID}/cost-collector:latest .

# Push to Google Container Registry
docker push gcr.io/${PROJECT_ID}/cost-collector:latest
```

### 2. Deploy as Cloud Run Job

```bash
gcloud run jobs create cost-collector \
  --image gcr.io/${PROJECT_ID}/cost-collector:latest \
  --region us-central1 \
  --service-account billing-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars BQ_DATASET_ID=billing_data \
  --set-env-vars BQ_TABLE_ID=daily_costs \
  --max-retries 3 \
  --task-timeout 30m
```

### 3. Schedule with Cloud Scheduler

```bash
# Create a schedule to run daily at 1 AM UTC
gcloud scheduler jobs create http cost-collector-daily \
  --location us-central1 \
  --schedule "0 1 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-collector:run" \
  --http-method POST \
  --oauth-service-account-email billing-collector@${PROJECT_ID}.iam.gserviceaccount.com
```

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GCP_PROJECT_ID=your-project-id
export BQ_DATASET_ID=billing_data
export BQ_TABLE_ID=daily_costs

# Run locally (requires Application Default Credentials)
python main.py
```

## Service Account Setup

Create a service account with necessary permissions:

```bash
# Create service account
gcloud iam service-accounts create billing-collector \
  --display-name "Billing Data Collector"

# Grant billing viewer role
gcloud organizations add-iam-policy-binding YOUR_ORG_ID \
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

## Monitoring

View job execution logs:

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-collector" \
  --limit 50 \
  --format json
```

## Querying Cost Data

Example BigQuery queries:

```sql
-- Daily cost by project
SELECT 
  date,
  project_id,
  SUM(cost) as total_cost,
  currency
FROM `your-project.billing_data.daily_costs`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY date, project_id, currency
ORDER BY date DESC, total_cost DESC;

-- Cost by service
SELECT 
  service_description,
  SUM(cost) as total_cost,
  currency
FROM `your-project.billing_data.daily_costs`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY service_description, currency
ORDER BY total_cost DESC;
```

## Troubleshooting

### No billing accounts found
- Verify the service account has `billing.accounts.list` permission
- Check that billing accounts are open/active

### Billing export table not found
- Configure billing export in GCP Console
- Update the query in `query_billing_export_for_date()` to match your export table name

### Permission denied errors
- Verify service account has all required IAM roles
- Check organization-level policies

## Notes

- The job collects data for the previous day (yesterday 00:00 to 23:59)
- For detailed cost data, billing export to BigQuery must be configured
- The table is partitioned by date for efficient querying
- Failed jobs will retry up to 3 times automatically
