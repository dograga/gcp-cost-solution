# GCP Cost Anomalies Collector

A Cloud Run job that collects GCP cost anomalies from the Billing API and enriches them with project metadata (appcode, lob) from Firestore.

## Overview

This job:
1. Fetches cost anomalies from GCP Billing API for all accessible billing accounts
2. Enriches anomaly data with project metadata (appcode, lob) from a Firestore collection
3. Stores enriched anomalies in Firestore for analysis and reporting

## Features

- **Automatic Discovery**: Discovers all accessible billing accounts or uses configured list
- **Data Enrichment**: Enriches anomalies with project metadata using project_id mapping
- **Multi-Currency Support**: Automatic currency conversion to USD for consistent filtering across 20+ currencies
- **Flexible Filtering**: Filter by minimum impact amount (USD) and anomaly types
- **Batch Processing**: Efficient batch writes to Firestore
- **Environment Support**: Separate configurations for dev/uat/prd environments

## Configuration

### Environment Variables

Create environment-specific `.env` files (`.env.dev`, `.env.uat`, `.env.prd`):

```bash
# GCP Project
GCP_PROJECT_ID=your-project-id

# Organization Configuration
ORGANIZATION_ID=your-org-id

# Billing Account Configuration (comma-separated for multiple accounts)
# Leave empty to fetch all accessible billing accounts
BILLING_ACCOUNT_IDS=

# Firestore Configuration
FIRESTORE_DATABASE=cost-db
FIRESTORE_COLLECTION=cost_anomalies

# Project Enrichment Configuration
# Collection containing project metadata (appcode, lob, etc.)
ENRICHMENT_DATABASE=dashboard
ENRICHMENT_COLLECTION=projects
# Field name in enrichment documents that contains the project ID
ENRICHMENT_PROJECT_ID_FIELD=project_id
# Fields to enrich anomalies with
ENRICHMENT_FIELDS=appcode,lob

# Anomaly Filtering
# Minimum impact amount to include (in USD, all currencies converted to USD)
MIN_IMPACT_AMOUNT=100
# Anomaly types to include (comma-separated, leave empty for all)
ANOMALY_TYPES=

# Time Range Configuration
# Number of days back to fetch anomalies
DAYS_BACK=30

# Logging
LOG_LEVEL=INFO
```

### Currency Conversion

The `MIN_IMPACT_AMOUNT` filter uses automatic currency conversion to USD for consistent filtering across different currencies. The system includes exchange rates for 20+ currencies including:

- **Major currencies**: USD, EUR, GBP, JPY, CHF
- **Asia-Pacific**: SGD, AUD, NZD, HKD, CNY, INR, KRW, TWD
- **Americas**: CAD, BRL, MXN
- **Europe**: SEK, NOK, DKK
- **Other**: ZAR

For example, with `MIN_IMPACT_AMOUNT=100`:
- An anomaly of 100 USD would be included
- An anomaly of 93 EUR (~100 USD) would be included
- An anomaly of 15,000 JPY (~100 USD) would be included
- An anomaly of 5,000 JPY (~33 USD) would be excluded

**Note**: Exchange rates are approximate and fixed in the code. For production use with frequently changing rates, consider integrating a real-time exchange rate API.

### Enrichment Collection Structure

The enrichment collection (e.g., `projects`) should contain documents with:

```json
{
  "project_id": "my-gcp-project",
  "appcode": "APP001",
  "lob": "Engineering",
  // ... other fields
}
```

The `project_id` field is used to map anomalies to project metadata.

## Data Structure

### Collected Anomaly Fields

Each anomaly document contains:

- **anomaly_id**: Unique anomaly identifier
- **billing_account_id**: Billing account where anomaly was detected
- **project_id**: GCP project ID (if available)
- **service**: GCP service (e.g., "Compute Engine")
- **location**: Geographic location
- **cost_change**: Absolute cost change amount
- **percentage_change**: Percentage change in cost
- **currency_code**: Currency (e.g., "USD")
- **period_start**: Anomaly period start time
- **period_end**: Anomaly period end time
- **severity**: Anomaly severity level
- **type**: Anomaly type
- **description**: Anomaly description
- **detection_time**: When anomaly was detected
- **update_time**: Last update time
- **collected_at**: When data was collected
- **appcode**: Application code (enriched from projects collection)
- **lob**: Line of business (enriched from projects collection)

## Local Development

### Prerequisites

- Python 3.9+
- GCP credentials with appropriate permissions
- Access to Firestore databases

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export ENVIRONMENT=dev

# Run locally
python main.py
```

### Testing

```bash
# Test with debug logging
export LOG_LEVEL=DEBUG
export ENVIRONMENT=dev
python main.py
```

## Deployment

### Service Account Permissions

The service account needs:

```bash
# Billing permissions
roles/billing.viewer
roles/billing.accountViewer

# Firestore permissions (for both databases)
roles/datastore.user
```

### Build and Deploy

```bash
# Build Docker image
export PROJECT_ID=your-project-id
docker build -t gcr.io/${PROJECT_ID}/cost-anomalies:latest .
docker push gcr.io/${PROJECT_ID}/cost-anomalies:latest

# Deploy Cloud Run Job
gcloud run jobs create cost-anomalies \
  --image gcr.io/${PROJECT_ID}/cost-anomalies:latest \
  --region us-central1 \
  --service-account anomaly-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=prd \
  --max-retries 2 \
  --task-timeout 20m

# Schedule daily execution (e.g., 3 AM UTC)
gcloud scheduler jobs create http cost-anomalies-daily \
  --location us-central1 \
  --schedule "0 3 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-anomalies:run" \
  --http-method POST \
  --oauth-service-account-email anomaly-collector@${PROJECT_ID}.iam.gserviceaccount.com
```

### Manual Execution

```bash
# Run the job manually
gcloud run jobs execute cost-anomalies --region us-central1
```

## Querying Anomalies

### Firestore Examples (Python)

```python
from google.cloud import firestore

db = firestore.Client(database='cost-db')

# Get all anomalies
anomalies = db.collection('cost_anomalies').stream()
for anomaly in anomalies:
    data = anomaly.to_dict()
    print(f"Project: {data['project_id']}, Cost Change: ${data['cost_change']:.2f}")

# Get anomalies for specific project
project_anomalies = db.collection('cost_anomalies') \
    .where('project_id', '==', 'my-project-id') \
    .order_by('cost_change', direction=firestore.Query.DESCENDING) \
    .stream()

# Get anomalies by appcode
appcode_anomalies = db.collection('cost_anomalies') \
    .where('appcode', '==', 'APP001') \
    .stream()

# Get high-impact anomalies
high_impact = db.collection('cost_anomalies') \
    .where('cost_change', '>=', 1000) \
    .stream()
```

### Query by LOB

```python
# Get all anomalies for a specific line of business
lob_anomalies = db.collection('cost_anomalies') \
    .where('lob', '==', 'Engineering') \
    .stream()

total_impact = 0
for anomaly in lob_anomalies:
    data = anomaly.to_dict()
    total_impact += abs(data.get('cost_change', 0))

print(f"Total cost impact for Engineering: ${total_impact:,.2f}")
```

## Monitoring

### View Logs

```bash
# View recent logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-anomalies" \
  --limit 50 \
  --format json

# View errors only
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-anomalies AND severity>=ERROR" \
  --limit 20
```

### Check Execution Status

```bash
# List recent executions
gcloud run jobs executions list --job cost-anomalies --region us-central1

# View specific execution
gcloud run jobs executions describe EXECUTION_NAME --region us-central1
```

## Troubleshooting

### No anomalies found
- Verify billing accounts are accessible
- Check that anomalies exist in the specified time range
- Review MIN_IMPACT_AMOUNT filter setting

### Enrichment data not loading
- Verify ENRICHMENT_DATABASE and ENRICHMENT_COLLECTION are correct
- Check that project documents have the correct ENRICHMENT_PROJECT_ID_FIELD
- Ensure service account has read access to enrichment collection

### Permission denied errors
- Verify service account has required roles
- Check that both Firestore databases are accessible
- Ensure billing account access is granted

### Missing enrichment fields
- Verify ENRICHMENT_FIELDS configuration matches field names in project documents
- Check that project documents contain the specified fields
- Review logs for enrichment statistics

## Architecture

```
┌─────────────────────┐
│  GCP Billing API    │
│  Anomaly Service    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ cost-anomalies Job  │
│  - Fetch anomalies  │
│  - Enrich data      │
└──────┬──────────────┘
       │
       ├──────────────────┐
       ▼                  ▼
┌─────────────┐    ┌──────────────┐
│ Firestore   │    │  Firestore   │
│ (cost-db)   │    │ (dashboard)  │
│ Anomalies   │◄───│  Projects    │
└─────────────┘    └──────────────┘
                   (Enrichment Data)
```

## Best Practices

1. **Regular Execution**: Schedule daily to catch new anomalies
2. **Alert Setup**: Create alerts for high-impact anomalies
3. **Data Retention**: Implement data lifecycle policies in Firestore
4. **Enrichment Updates**: Keep project metadata current
5. **Filter Tuning**: Adjust MIN_IMPACT_AMOUNT based on your needs
6. **Access Control**: Use minimal permissions for service account

## Integration

This job integrates with:
- **cost-processor**: Provides project-level cost context
- **cost-recommendation**: Combines with recommendations for optimization
- **Dashboards**: Anomaly data can be visualized alongside cost reports

## License

MIT License
