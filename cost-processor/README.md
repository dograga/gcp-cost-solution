# GCP Cost Processor Job

This Cloud Run job processes billing data collected in BigQuery and generates comprehensive cost reports by project ID and services.

## Features

- **7 Automated Reports**: Generates multiple cost analysis reports
- **Project-Level Analysis**: Costs broken down by project and service
- **Trend Analysis**: Daily trends with moving averages
- **Top Cost Drivers**: Identifies highest-cost SKUs
- **Location Analysis**: Costs by geographic region/zone
- **Automatic Table Creation**: Creates all report tables automatically

## Generated Reports

1. **project_service_daily_costs** - Daily costs by project and service
2. **project_cost_summary** - Total costs aggregated by project
3. **service_cost_summary** - Total costs by service across all projects
4. **project_service_cost_summary** - Detailed breakdown with percentages
5. **daily_cost_trends** - Daily trends with 7-day moving averages
6. **top_cost_drivers** - Top 20 cost drivers by SKU (last 7 days)
7. **location_cost_summary** - Costs by geographic location

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | Yes | - | GCP project ID |
| `SOURCE_DATASET_ID` | No | `billing_data` | Source dataset with raw billing data |
| `SOURCE_TABLE_ID` | No | `daily_costs` | Source table name |
| `OUTPUT_DATASET_ID` | No | `billing_reports` | Output dataset for reports |
| `DAYS_BACK` | No | `30` | Number of days to include in reports |

## Deployment

### Build and Push Docker Image

```bash
cd cost-processor
export PROJECT_ID=your-project-id

docker build -t gcr.io/${PROJECT_ID}/cost-processor:latest .
docker push gcr.io/${PROJECT_ID}/cost-processor:latest
```

### Deploy as Cloud Run Job

```bash
gcloud run jobs create cost-processor \
  --image gcr.io/${PROJECT_ID}/cost-processor:latest \
  --region us-central1 \
  --service-account billing-processor@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars DAYS_BACK=30 \
  --max-retries 2 \
  --task-timeout 20m
```

### Schedule with Cloud Scheduler

```bash
# Run daily at 2 AM UTC (after cost collection job)
gcloud scheduler jobs create http cost-processor-daily \
  --location us-central1 \
  --schedule "0 2 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-processor:run" \
  --http-method POST \
  --oauth-service-account-email billing-processor@${PROJECT_ID}.iam.gserviceaccount.com
```

## Service Account Permissions

```bash
gcloud iam service-accounts create billing-processor \
  --display-name "Billing Data Processor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-processor@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:billing-processor@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

## Example Queries

### View Project Costs
```sql
SELECT * FROM `your-project.billing_reports.project_cost_summary`
ORDER BY total_cost DESC;
```

### View Service Breakdown for a Project
```sql
SELECT 
  service_description,
  total_cost,
  pct_of_project_cost
FROM `your-project.billing_reports.project_service_cost_summary`
WHERE project_id = 'your-project-id'
ORDER BY total_cost DESC;
```

### View Daily Trends
```sql
SELECT 
  date,
  total_cost,
  cost_7day_avg,
  cost_pct_change_from_prev_day
FROM `your-project.billing_reports.daily_cost_trends`
ORDER BY date DESC
LIMIT 30;
```
