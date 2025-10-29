# GCP Invoice Ingestion

Cloud Run job that fetches GCP monthly invoices and stores them in Firestore for chargeback purposes.

## Overview

This job:
1. Fetches monthly invoices from Cloud Billing API
2. Stores invoice summary data in Firestore for chargeback reporting

**Note:** For detailed cost breakdowns, use the `cost-bigquery-processor` module which queries BigQuery billing export directly.

## Features

- **Multi-Account Support**: Processes multiple billing accounts automatically
- **Historical Data**: Fetches invoices for configurable months back (default: 12 months)
- **Invoice Summary**: Captures total amount, subtotal, tax, credits, and dates
- **Idempotent**: Uses invoice_id as document ID to prevent duplicates
- **Batch Processing**: Efficient batch writes to Firestore (500 operations per batch)
- **Retry Logic**: Exponential backoff retry for transient failures and quota errors
- **Environment Support**: Separate configurations for dev/uat/prd environments
- **Chargeback Ready**: Invoice data structured for chargeback reporting

## Configuration

### Environment Variables

Create environment-specific `.env` files (`.env.dev`, `.env.uat`, `.env.prd`):

```bash
# GCP Project
GCP_PROJECT_ID=your-project-id

# Billing Account Configuration
# Comma-separated list, leave empty to fetch all accessible accounts
BILLING_ACCOUNT_IDS=

# Firestore Configuration
FIRESTORE_DATABASE=cost-db
FIRESTORE_COLLECTION=invoices

# Project Enrichment Configuration
ENRICHMENT_DATABASE=dashboard
ENRICHMENT_COLLECTION=projects
ENRICHMENT_PROJECT_ID_FIELD=project_id
ENRICHMENT_FIELDS=appcode,lob

# Invoice Processing Configuration
# Number of months back to fetch invoices
MONTHS_BACK=12
# Include invoice line items (True/False)
INCLUDE_LINE_ITEMS=True

# Logging
LOG_LEVEL=INFO
```

### Enrichment Collection Structure

The enrichment collection (e.g., `projects`) should contain documents with:

```json
{
  "project_id": "my-gcp-project",
  "appcode": "APP001",
  "lob": "Engineering"
}
```

## Data Structure

### Invoice Document

```json
{
  "invoice_id": "012345-ABCDEF-2025-10",
  "billing_account_id": "012345-ABCDEF-GHIJKL",
  "invoice_month": "2025-10",
  "currency": "USD",
  "total_amount": 15234.56,
  "subtotal": 15234.56,
  "tax": 0.0,
  "credits": 0.0,
  "status": "finalized",
  "issue_date": "2025-10-01",
  "due_date": "2025-11-30",
  "fetched_at": "2025-10-29T12:00:00Z",
  "line_items": [
    {
      "project_id": "my-project",
      "service": "Compute Engine",
      "sku": "N1 Predefined Instance Core",
      "cost": 1250.00,
      "currency": "USD",
      "appcode": "APP001",
      "lob": "Engineering"
    }
  ]
}
```

**Document ID:** `{billing_account_id}-{YYYY-MM}`

### Invoice Status

- `finalized` - Invoice for past months (closed)
- `pending` - Invoice for current month (still accumulating charges)

### Invoice Dates

**Issue Date & Due Date:**
- The system **prefers actual dates from the Cloud Billing API** when available
- `issue_date`: Date the invoice was issued by Google
- `due_date`: Official payment due date from Google's billing system
- **Fallback**: If API doesn't provide dates, estimates are calculated:
  - `issue_date`: First day of invoice month
  - `due_date`: 30 days after month end (may not match actual billing terms)

**Note:** Google's actual invoice due dates depend on your billing account terms and may vary. Always use the API-provided `due_date` when available (which is the default behavior).

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env.dev
   # Edit .env.dev with your values
   ```

3. **Run locally:**
   ```bash
   python main.py
   ```

## Deployment

### Deploy as Cloud Run Job

```bash
gcloud run jobs create invoice-ingestion \
  --source . \
  --region asia-southeast1 \
  --set-env-vars ENVIRONMENT=prod \
  --service-account invoice-ingestion-sa@PROJECT_ID.iam.gserviceaccount.com \
  --max-retries 3 \
  --task-timeout 30m \
  --memory 1Gi
```

### Schedule with Cloud Scheduler

Run monthly on the 2nd day of each month (after invoices are finalized):

```bash
gcloud scheduler jobs create http invoice-ingestion-schedule \
  --location asia-southeast1 \
  --schedule "0 2 2 * *" \
  --uri "https://asia-southeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/PROJECT_ID/jobs/invoice-ingestion:run" \
  --http-method POST \
  --oauth-service-account-email invoice-ingestion-sa@PROJECT_ID.iam.gserviceaccount.com
```

### Manual Execution

```bash
gcloud run jobs execute invoice-ingestion \
  --region asia-southeast1
```

## IAM Permissions

### Required Roles

```yaml
roles/billing.viewer             # Read billing data
roles/datastore.user             # Read/write Firestore
```

Grant permissions:
```bash
# Billing access (at organization level)
gcloud organizations add-iam-policy-binding ORG_ID \
  --member="serviceAccount:invoice-ingestion-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/billing.viewer"

# Firestore access
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:invoice-ingestion-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## BigQuery Integration

For detailed line items, enable BigQuery billing export:

1. **Enable billing export:**
   ```bash
   # In GCP Console: Billing > Billing export > BigQuery export
   # Or use Terraform/gcloud commands
   ```

2. **Update `fetch_line_items()` method** to query BigQuery:
   ```python
   def fetch_line_items(self, billing_account_id: str, month: str):
       query = f"""
       SELECT
           project.id as project_id,
           service.description as service,
           sku.description as sku,
           SUM(cost) as cost,
           currency
       FROM `{project}.{dataset}.gcp_billing_export_v1_{billing_account_id}`
       WHERE DATE_TRUNC(usage_start_time, MONTH) = '{month}-01'
       GROUP BY project_id, service, sku, currency
       """
       # Execute query and return results
   ```

## How It Works

1. **Discover Billing Accounts**: Lists all accessible billing accounts or uses configured list
2. **Generate Month List**: Creates list of months to fetch (e.g., last 12 months)
3. **Fetch Invoices**: Calls Cloud Billing API `list_invoices()` for each account
4. **Parse Invoice Data**: Extracts invoice details (amounts, dates, currency, etc.)
5. **Fetch Line Items**: Optionally fetches detailed line items from BigQuery billing export
6. **Enrich Data**: Enriches line items with project metadata (appcode, lob)
7. **Save to Firestore**: Stores invoices with enriched line items using `merge=True`
8. **Generate Statistics**: Calculates totals and monthly breakdowns

## Monitoring

### Check Logs

```bash
gcloud run jobs logs read invoice-ingestion \
  --region asia-southeast1 \
  --limit 100
```

### Query Invoices

```python
from google.cloud import firestore

db = firestore.Client(database='cost-db')
invoices = db.collection('invoices').stream()

for invoice in invoices:
    data = invoice.to_dict()
    print(f"{data['invoice_month']}: ${data['total_amount']:.2f}")
```

### Monthly Totals

```python
# Get total for specific month
month_invoices = db.collection('invoices')\
    .where('invoice_month', '==', '2025-10')\
    .stream()

total = sum(inv.to_dict()['total_amount'] for inv in month_invoices)
print(f"Total for 2025-10: ${total:.2f}")
```

### By Billing Account

```python
# Get invoices for specific billing account
account_invoices = db.collection('invoices')\
    .where('billing_account_id', '==', '012345-ABCDEF-GHIJKL')\
    .order_by('invoice_month', direction=firestore.Query.DESCENDING)\
    .limit(12)\
    .stream()

for inv in account_invoices:
    data = inv.to_dict()
    print(f"{data['invoice_month']}: ${data['total_amount']:.2f}")
```

## Logging

The job logs:
- Number of billing accounts processed
- Number of invoices fetched
- Enrichment statistics
- Save statistics
- Any errors encountered

Example output:
```
2025-10-29 12:00:00 - INFO - Starting Invoice Ingestion Job
2025-10-29 12:00:01 - INFO - Found billing account: 012345-ABCDEF (Production)
2025-10-29 12:00:02 - INFO - Fetching invoices for 12 months: 2025-10 to 2024-11
2025-10-29 12:00:05 - INFO - Loaded enrichment data for 150 projects
2025-10-29 12:00:10 - INFO - Fetched 12 invoices for account 012345-ABCDEF
2025-10-29 12:00:11 - INFO - Enriched 1250 out of 1250 line items
2025-10-29 12:00:15 - INFO - Successfully saved 12 invoices to Firestore
2025-10-29 12:00:15 - INFO - Invoice Ingestion Job Completed Successfully
```

## Troubleshooting

### No Invoices Found

- Verify billing account IDs are correct
- Check service account has `roles/billing.viewer` on organization
- Ensure Cloud Billing API is enabled

### Permission Denied

- Grant `roles/billing.viewer` at organization level
- Grant `roles/datastore.user` at project level

### Missing Line Items

- Enable BigQuery billing export
- Update `fetch_line_items()` to query BigQuery table
- Verify BigQuery dataset and table names

### Enrichment Data Not Loading

- Check enrichment database and collection names
- Verify project documents have correct field names
- Ensure service account has Firestore read access

## Cost

- **Cloud Billing API**: Free
- **Firestore**: ~$0.18 per 100K writes
- **Cloud Run**: ~$0.01 per execution (minimal compute)
- **BigQuery** (if used): ~$5 per TB scanned

**Estimated cost for monthly schedule: ~$2-5/month**

## Error Handling & Retry Logic

### Firestore Batch Commits

The job implements robust retry logic for Firestore batch commits:

**Retryable Errors:**
- `ResourceExhausted` - Quota exceeded
- `DeadlineExceeded` - Request timeout
- `ServiceUnavailable` - Temporary service issues

**Retry Strategy:**
- Maximum 3 retry attempts per batch
- Exponential backoff: 1s, 2s, 4s (with jitter)
- Failed batches are logged with invoice IDs for manual recovery

**Example Retry Flow:**
```
Attempt 1: Quota exceeded → Wait 1.2s
Attempt 2: Quota exceeded → Wait 2.5s
Attempt 3: Success → Batch committed
```

### Partial Failure Handling

- Each batch is tracked independently
- Failed batches don't affect successful batches
- Statistics report: `{saved: 450, errors: 50}`
- Failed invoice IDs are logged for reprocessing

## Best Practices

1. **Schedule Monthly**: Run on 2nd day of month after invoices finalize
2. **Monitor Costs**: Track invoice totals for anomalies
3. **Backup Data**: Export Firestore data regularly
4. **Audit Trail**: Keep historical invoices for compliance
5. **Alert on Spikes**: Set up alerts for unusual cost increases
6. **Retry Failed Batches**: Check logs for failed invoice IDs and reprocess if needed

## Future Enhancements

- [ ] Add invoice PDF generation
- [ ] Email notifications for new invoices
- [ ] Cost allocation by department/team
- [ ] Budget vs actual comparison
- [ ] Trend analysis and forecasting
- [ ] Integration with accounting systems
