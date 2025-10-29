# Cost BigQuery Processor

Cloud Run job that fetches cost data from BigQuery billing export and stores it in Firestore with project metadata enrichment.

## Overview

This module replaces the previous `cost-cron` and `cost-processor` modules with a unified solution that:
1. Fetches cost data from BigQuery billing export for the last X days
2. Enriches cost data with project metadata (appcode, lob)
3. Stores processed data in Firestore for dashboard consumption
4. Supports multiple aggregation levels (daily, project, service)

## Features

- **BigQuery Integration**: Direct queries to billing export tables
- **Flexible Date Range**: Configure days back to process (default: 7 days)
- **Multiple Aggregation Levels**: Daily detailed, daily summary, project total, or service breakdown
- **Project Enrichment**: Adds appcode, lob, and other metadata to cost records
- **Batch Processing**: Efficient Firestore batch writes (500 operations per batch)
- **Multi-Account Support**: Processes multiple billing accounts
- **Idempotent**: Uses unique document IDs to prevent duplicates

## Configuration

### Environment Variables (.env.dev)

```bash
# GCP Project
GCP_PROJECT_ID=evol-dev-456410

# BigQuery Configuration
BILLING_DATASET=billing_export
BILLING_TABLE_PREFIX=gcp_billing_export_v1
BILLING_ACCOUNT_IDS=

# Firestore Configuration
FIRESTORE_DATABASE=cost-db
FIRESTORE_COLLECTION=daily_costs

# Project Enrichment Configuration
ENRICHMENT_DATABASE=dashboard
ENRICHMENT_COLLECTION=projects
ENRICHMENT_PROJECT_ID_FIELD=project_id
ENRICHMENT_FIELDS=appcode,lob

# Processing Configuration
DAYS_BACK=7
AGGREGATION_LEVEL=daily
INCLUDE_DETAILS=True

# Logging
LOG_LEVEL=INFO
```

### Aggregation Levels

**1. `daily` with `INCLUDE_DETAILS=True` (Default)**
- Most detailed level
- Groups by: date, project, service, SKU
- Best for: Detailed cost analysis and drill-down

**2. `daily` with `INCLUDE_DETAILS=False`**
- Daily totals per project
- Groups by: date, project
- Best for: Daily cost trends per project

**3. `project`**
- Total cost per project for entire date range
- Groups by: project
- Best for: Project cost comparison

**4. `service`**
- Daily costs per service
- Groups by: date, project, service
- Best for: Service-level cost analysis

## Data Structure

### Firestore Document

```json
{
  "billing_account_id": "012345-ABCDEF-GHIJKL",
  "date": "2025-10-29",
  "project_id": "my-project",
  "project_name": "My Project",
  "service": "Compute Engine",
  "sku": "N1 Predefined Instance Core",
  "cost": 125.50,
  "currency": "USD",
  "usage_amount": 730.0,
  "usage_unit": "hour",
  "appcode": "APP001",
  "lob": "Engineering",
  "processed_at": "2025-10-29T12:00:00Z",
  "aggregation_level": "daily"
}
```

**Document ID Format:**
```
{billing_account}_{date}_{project}_{service}
```

Example: `012345_ABCDEF_2025-10-29_my-project_Compute_Engine`

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Run Locally

```bash
# Development environment
python main.py

# Production environment
ENVIRONMENT=prd python main.py
```

### Deploy as Cloud Run Job

```bash
gcloud run jobs create cost-bigquery-processor \
  --source . \
  --region asia-southeast1 \
  --set-env-vars ENVIRONMENT=prod \
  --service-account cost-processor-sa@PROJECT_ID.iam.gserviceaccount.com \
  --max-retries 3 \
  --task-timeout 30m \
  --memory 2Gi
```

### Schedule with Cloud Scheduler

Run daily at 2 AM:

```bash
gcloud scheduler jobs create http cost-processor-daily \
  --location asia-southeast1 \
  --schedule "0 2 * * *" \
  --uri "https://asia-southeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/cost-bigquery-processor:run" \
  --http-method POST \
  --oauth-service-account-email cost-processor-sa@PROJECT_ID.iam.gserviceaccount.com
```

### Manual Execution

```bash
gcloud run jobs execute cost-bigquery-processor \
  --region asia-southeast1
```

## IAM Permissions

### Required Roles

```yaml
roles/bigquery.dataViewer      # Read BigQuery billing data
roles/bigquery.jobUser         # Execute BigQuery queries
roles/datastore.user           # Read/write Firestore
roles/billing.viewer           # List billing accounts (optional)
```

Grant permissions:
```bash
# BigQuery access
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:cost-processor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:cost-processor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Firestore access
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:cost-processor-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## How It Works

1. **Discover Billing Accounts**
   - Uses configured list or auto-discovers from Billing API

2. **Calculate Date Range**
   - Fetches data for last X days (configured via `DAYS_BACK`)

3. **Query BigQuery**
   - Builds SQL query based on aggregation level
   - Queries billing export table: `{project}.{dataset}.gcp_billing_export_v1_{account_id}`

4. **Load Enrichment Data**
   - Fetches project metadata from Firestore enrichment collection

5. **Enrich Cost Records**
   - Adds appcode, lob, and other fields to each cost record

6. **Save to Firestore**
   - Batch writes to Firestore (500 operations per batch)
   - Uses merge=True for idempotency

7. **Generate Statistics**
   - Calculates totals, breakdowns, and top consumers

## Example Queries

### Daily Costs with Details

```sql
SELECT
    DATE(usage_start_time) as date,
    project.id as project_id,
    service.description as service,
    sku.description as sku,
    SUM(cost) as cost,
    currency
FROM `project.billing_export.gcp_billing_export_v1_012345_ABCDEF`
WHERE DATE(usage_start_time) >= '2025-10-22'
    AND DATE(usage_start_time) <= '2025-10-29'
GROUP BY date, project_id, service, sku, currency
ORDER BY date DESC, cost DESC
```

### Project Totals

```sql
SELECT
    project.id as project_id,
    SUM(cost) as cost,
    currency
FROM `project.billing_export.gcp_billing_export_v1_012345_ABCDEF`
WHERE DATE(usage_start_time) >= '2025-10-22'
    AND DATE(usage_start_time) <= '2025-10-29'
GROUP BY project_id, currency
ORDER BY cost DESC
```

## Monitoring

### Check Logs

```bash
gcloud run jobs logs read cost-bigquery-processor \
  --region asia-southeast1 \
  --limit 100
```

### Query Processed Data

```python
from google.cloud import firestore

db = firestore.Client(database='cost-db')
costs = db.collection('daily_costs')\
    .where('date', '==', '2025-10-29')\
    .stream()

total = sum(doc.to_dict()['cost'] for doc in costs)
print(f"Total cost for 2025-10-29: ${total:.2f}")
```

### Daily Cost Trend

```python
# Get last 7 days of costs
from datetime import datetime, timedelta

end_date = datetime.now().date()
start_date = end_date - timedelta(days=7)

costs = db.collection('daily_costs')\
    .where('date', '>=', str(start_date))\
    .where('date', '<=', str(end_date))\
    .stream()

daily_totals = {}
for doc in costs:
    data = doc.to_dict()
    date = data['date']
    cost = data['cost']
    daily_totals[date] = daily_totals.get(date, 0) + cost

for date in sorted(daily_totals.keys()):
    print(f"{date}: ${daily_totals[date]:.2f}")
```

### Top Projects by Cost

```python
# Get top 10 projects by cost
from collections import defaultdict

costs = db.collection('daily_costs')\
    .where('date', '==', '2025-10-29')\
    .stream()

project_totals = defaultdict(float)
for doc in costs:
    data = doc.to_dict()
    project_totals[data['project_id']] += data['cost']

top_projects = sorted(project_totals.items(), key=lambda x: x[1], reverse=True)[:10]
for project, cost in top_projects:
    print(f"{project}: ${cost:.2f}")
```

## Cost

- **BigQuery**: ~$5 per TB scanned (billing export queries are typically small)
- **Firestore**: ~$0.18 per 100K writes
- **Cloud Run**: ~$0.01 per execution (minimal compute)

**Estimated cost for daily schedule: ~$5-10/month**

## Comparison with Previous Modules

### Old Architecture (cost-cron + cost-processor)

```
cost-cron (Cloud Scheduler)
  ↓ triggers
cost-processor (Cloud Function)
  ↓ queries
BigQuery
  ↓ stores
Firestore
```

### New Architecture (cost-bigquery-processor)

```
Cloud Scheduler
  ↓ triggers
cost-bigquery-processor (Cloud Run Job)
  ↓ queries BigQuery + stores Firestore
Done
```

**Benefits:**
- ✅ Simpler architecture (1 module instead of 2)
- ✅ Direct BigQuery queries (no intermediate processing)
- ✅ Configurable date range (not limited to daily)
- ✅ Multiple aggregation levels
- ✅ Better error handling and retry logic
- ✅ Easier to maintain and deploy

## Troubleshooting

### No Data Found

Check if BigQuery billing export is enabled:
```bash
# List tables in billing dataset
bq ls --project_id=PROJECT_ID billing_export
```

### Permission Denied

Grant required IAM roles to service account

### High Costs

Reduce `DAYS_BACK` or change `AGGREGATION_LEVEL` to reduce query size

### Duplicate Records

Check document ID generation - should be unique per date/project/service combination

## Best Practices

1. **Schedule Wisely**: Run daily at off-peak hours (e.g., 2 AM)
2. **Monitor Costs**: Track BigQuery query costs
3. **Adjust Days Back**: Start with 7 days, increase if needed
4. **Use Aggregation**: Use appropriate aggregation level for your use case
5. **Archive Old Data**: Implement data retention policy in Firestore

## Future Enhancements

- [ ] Add support for cost anomaly detection
- [ ] Implement data retention/archival
- [ ] Add budget alerts integration
- [ ] Support for custom cost allocation tags
- [ ] Export to BigQuery for long-term analysis
- [ ] Add cost forecasting
