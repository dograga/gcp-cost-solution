# GCP Cost Solution

A comprehensive solution for collecting, processing, and reporting Google Cloud Platform billing costs across multiple billing accounts. The solution consists of two Cloud Run jobs that work together to provide detailed cost analytics.

## Architecture

```
┌─────────────────────┐
│  GCP Billing API    │
│  Billing Accounts   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   cost-cron Job     │  (Runs daily at 1 AM UTC)
│  - Collects costs   │
│  - Stores in BQ     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    BigQuery         │
│  billing_data       │
│  - daily_costs      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ cost-processor Job  │  (Runs daily at 2 AM UTC)
│  - Processes data   │
│  - Creates reports  │
└──────┬──────────────┘
       │
       ├──────────────────┐
       ▼                  ▼
┌─────────────┐    ┌──────────────┐
│  BigQuery   │    │  Firestore   │
│  Reports    │    │  Reports     │
└─────────────┘    └──────────────┘
```

## Components

### 1. cost-cron
Collects billing data from all accessible GCP billing accounts and stores it in BigQuery.

**Features:**
- Discovers all billing accounts automatically
- Collects previous day's cost data (00:00 to 23:59)
- Stores raw billing data in BigQuery
- Supports billing export integration

### 2. cost-processor
Processes collected billing data and generates comprehensive cost reports.

**Features:**
- Creates 7 different cost analysis reports
- Stores reports in both BigQuery and Firestore
- Provides project-level and service-level breakdowns
- Tracks cost trends and top cost drivers

## Environment Configuration

Both jobs support environment-specific configuration using `.env` files:

- `.env.dev` - Development environment
- `.env.uat` - UAT/Staging environment
- `.env.prd` - Production environment

Set the `ENVIRONMENT` variable to select which configuration to use:
```bash
export ENVIRONMENT=prd  # or dev, uat
```

### Configuration Files

Each job has a `config.py` that loads settings from the appropriate `.env` file.

**cost-cron configuration:**
- `GCP_PROJECT_ID` - GCP project for BigQuery storage
- `BQ_DATASET_ID` - BigQuery dataset name
- `BQ_TABLE_ID` - BigQuery table name
- `BQ_LOCATION` - BigQuery location (US, EU, etc.)
- `LOG_LEVEL` - Logging level (DEBUG, INFO, etc.)

**cost-processor configuration:**
- `GCP_PROJECT_ID` - GCP project for BigQuery
- `SOURCE_DATASET_ID` - Source dataset with raw billing data
- `SOURCE_TABLE_ID` - Source table name
- `OUTPUT_DATASET_ID` - Output dataset for reports
- `FIRESTORE_PROJECT_ID` - Firestore project ID
- `FIRESTORE_DATABASE` - Firestore database name
- `FIRESTORE_COLLECTION_PREFIX` - Prefix for Firestore collections
- `DAYS_BACK` - Number of days to include in reports
- `LOG_LEVEL` - Logging level

## Generated Reports

### BigQuery Reports

1. **project_service_daily_costs** - Daily costs by project and service
2. **project_cost_summary** - Total costs aggregated by project
3. **service_cost_summary** - Total costs by service across all projects
4. **project_service_cost_summary** - Detailed breakdown with percentage of project cost
5. **daily_cost_trends** - Daily trends with 7-day moving averages
6. **top_cost_drivers** - Top cost drivers by SKU
7. **location_cost_summary** - Costs by geographic location

### Firestore Collections

The following reports are also saved to Firestore for fast API access:

- `cost_reports_{env}_project_cost_summary`
- `cost_reports_{env}_service_cost_summary`
- `cost_reports_{env}_project_service_cost_summary`
- `cost_reports_{env}_daily_cost_trends`
- `cost_reports_{env}_top_cost_drivers`
- `cost_reports_{env}_location_cost_summary`
- `cost_reports_metadata` - Metadata about each report

## Deployment

### Prerequisites

1. **GCP Project** with billing enabled
2. **Service Accounts** with appropriate permissions
3. **Billing Export** configured (recommended for detailed data)

### Service Account Permissions

**For cost-cron:**
```bash
# Billing permissions
roles/billing.viewer
roles/billing.accountViewer

# BigQuery permissions
roles/bigquery.dataEditor
roles/bigquery.jobUser
```

**For cost-processor:**
```bash
# BigQuery permissions
roles/bigquery.dataEditor
roles/bigquery.jobUser

# Firestore permissions
roles/datastore.user
```

### Deploy cost-cron

```bash
cd cost-cron

# Update .env files with your configuration
# Edit .env.dev, .env.uat, .env.prd

# Build and push
export PROJECT_ID=your-project-id
docker build -t gcr.io/${PROJECT_ID}/cost-cron:latest .
docker push gcr.io/${PROJECT_ID}/cost-cron:latest

# Deploy for production
gcloud run jobs create cost-cron \
  --image gcr.io/${PROJECT_ID}/cost-cron:latest \
  --region us-central1 \
  --service-account billing-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=prd \
  --max-retries 3 \
  --task-timeout 30m

# Schedule daily at 1 AM UTC
gcloud scheduler jobs create http cost-cron-daily \
  --location us-central1 \
  --schedule "0 1 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-cron:run" \
  --http-method POST \
  --oauth-service-account-email billing-collector@${PROJECT_ID}.iam.gserviceaccount.com
```

### Deploy cost-processor

```bash
cd cost-processor

# Update .env files with your configuration
# Edit .env.dev, .env.uat, .env.prd

# Build and push
export PROJECT_ID=your-project-id
docker build -t gcr.io/${PROJECT_ID}/cost-processor:latest .
docker push gcr.io/${PROJECT_ID}/cost-processor:latest

# Deploy for production
gcloud run jobs create cost-processor \
  --image gcr.io/${PROJECT_ID}/cost-processor:latest \
  --region us-central1 \
  --service-account billing-processor@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=prd \
  --max-retries 2 \
  --task-timeout 20m

# Schedule daily at 2 AM UTC (after cost-cron)
gcloud scheduler jobs create http cost-processor-daily \
  --location us-central1 \
  --schedule "0 2 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-processor:run" \
  --http-method POST \
  --oauth-service-account-email billing-processor@${PROJECT_ID}.iam.gserviceaccount.com
```

## Local Development

### cost-cron

```bash
cd cost-cron

# Install dependencies
pip install -r requirements.txt

# Set environment
export ENVIRONMENT=dev

# Run locally
python main.py
```

### cost-processor

```bash
cd cost-processor

# Install dependencies
pip install -r requirements.txt

# Set environment
export ENVIRONMENT=dev

# Run locally
python main.py
```

## Querying Reports

### BigQuery Examples

```sql
-- View project costs
SELECT * FROM `your-project.billing_reports.project_cost_summary`
ORDER BY total_cost DESC;

-- View service breakdown for a project
SELECT 
  service_description,
  total_cost,
  pct_of_project_cost
FROM `your-project.billing_reports.project_service_cost_summary`
WHERE project_id = 'your-project-id'
ORDER BY total_cost DESC;

-- View daily trends
SELECT 
  date,
  total_cost,
  cost_7day_avg,
  cost_pct_change_from_prev_day
FROM `your-project.billing_reports.daily_cost_trends`
ORDER BY date DESC
LIMIT 30;
```

### Firestore Examples (Python)

```python
from google.cloud import firestore

db = firestore.Client()

# Get project cost summary
projects = db.collection('cost_reports_prd_project_cost_summary').stream()
for project in projects:
    data = project.to_dict()
    print(f"{data['project_id']}: ${data['total_cost']:.2f}")

# Get service costs for a specific project
project_services = db.collection('cost_reports_prd_project_service_cost_summary') \
    .where('project_id', '==', 'your-project-id') \
    .order_by('total_cost', direction=firestore.Query.DESCENDING) \
    .stream()

for service in project_services:
    data = service.to_dict()
    print(f"{data['service_description']}: ${data['total_cost']:.2f} ({data['pct_of_project_cost']:.1f}%)")
```

## Monitoring

### View Logs

```bash
# cost-cron logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-cron" \
  --limit 50 \
  --format json

# cost-processor logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-processor" \
  --limit 50 \
  --format json
```

### Check Job Status

```bash
# List job executions
gcloud run jobs executions list --job cost-cron --region us-central1
gcloud run jobs executions list --job cost-processor --region us-central1
```

## Troubleshooting

### No billing accounts found
- Verify service account has `billing.accounts.list` permission
- Check that billing accounts are open/active

### Billing export table not found
- Configure billing export in GCP Console: Billing → Billing Export → BigQuery Export
- Update `BILLING_EXPORT_DATASET` in .env files

### Firestore permission denied
- Verify service account has `roles/datastore.user` role
- Check Firestore database is created and accessible

### Configuration not loading
- Verify `.env.{ENVIRONMENT}` file exists
- Check `ENVIRONMENT` variable is set correctly
- Review logs for configuration loading messages

## Best Practices

1. **Use Billing Export**: Configure billing export to BigQuery for detailed cost data
2. **Monitor Costs**: Set up alerts on the daily_cost_trends report
3. **Regular Reviews**: Review top_cost_drivers weekly to identify optimization opportunities
4. **Access Control**: Use separate service accounts for each job with minimal permissions
5. **Environment Separation**: Use different projects/datasets for dev/uat/prd
6. **Backup**: Enable BigQuery table snapshots for critical reports

## License

MIT License
