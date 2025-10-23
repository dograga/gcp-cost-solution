# GCP Cost Recommendation Collection Cron Job

This Cloud Run job collects Google Cloud cost optimization recommendations from all accessible projects and stores them in Firestore. It's designed to run daily to capture active recommendations across multiple recommender types.

## Features

- **Flexible Scope**: Run at project, folder, or organization level
- **Multi-Project Support**: Automatically discovers and processes all projects within the specified scope
- **All Recommender Types**: By default, collects ALL available recommendation types from GCP (30+ types)
- **Comprehensive Coverage**: Includes recommendations for:
  - Compute Engine (VMs, disks, IPs, commitments, machine types)
  - Cloud SQL (idle, overprovisioned, out of disk)
  - IAM policies and project utilization
  - BigQuery (capacity commitments, partitioning)
  - Cloud Storage (lifecycle management)
  - GKE, Cloud Run, Cloud Functions
  - App Engine, Firestore, Spanner
  - And many more...
- **Firestore Integration**: Stores recommendations in Firestore for flexible querying and real-time updates
- **Flexible Filtering**: Optionally filter by specific recommender types or recommendation state
- **Multi-Region Support**: Checks all GCP regions globally
- **Batch Processing**: Efficiently saves recommendations using Firestore batch operations
- **Comprehensive Logging**: Detailed logs for monitoring and debugging
- **Environment-Specific Configuration**: Separate .env files for dev, uat, and production environments

## Prerequisites

1. **GCP Project** with billing enabled
2. **Service Account** with the following permissions:
   - `recommender.*.list` (for all recommender types you want to access)
   - `recommender.*.get`
   - `resourcemanager.projects.list`
   - `resourcemanager.projects.get`
   - `datastore.entities.create`
   - `datastore.entities.update`
   - `datastore.entities.get`
3. **Recommender API** enabled in your GCP project
4. **Firestore** database created in your GCP project

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | No | `dev` | Environment name (dev, uat, prd) |
| `GCP_PROJECT_ID` | Yes | - | GCP project ID where Firestore data will be stored |
| `SCOPE_TYPE` | No | `project` | Scope level: `project`, `folder`, or `organization` |
| `SCOPE_ID` | No | `GCP_PROJECT_ID` | Project ID, Folder ID, or Organization ID to collect recommendations from |
| `FIRESTORE_DATABASE` | No | `(default)` | Firestore database name |
| `FIRESTORE_COLLECTION` | No | `cost_recommendations` | Firestore collection name |
| `RECOMMENDER_TYPES` | No | Empty (all types) | Comma-separated list of specific recommender types to fetch. **Leave empty to fetch ALL types (recommended)** |
| `RECOMMENDATION_STATE_FILTER` | No | `ACTIVE` | Filter by recommendation state (ACTIVE, CLAIMED, SUCCEEDED, FAILED, DISMISSED) |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Supported Recommender Types

**By default, ALL available recommender types are collected.** The job automatically checks for 30+ recommender types including:

### Compute Engine
- `google.compute.instance.MachineTypeRecommender` - Right-size VM instances
- `google.compute.disk.IdleResourceRecommender` - Identify idle persistent disks
- `google.compute.instance.IdleResourceRecommender` - Identify idle VM instances
- `google.compute.address.IdleResourceRecommender` - Identify idle IP addresses
- `google.compute.image.IdleResourceRecommender` - Identify idle images
- `google.compute.commitment.UsageCommitmentRecommender` - Commitment usage recommendations
- `google.compute.instanceGroupManager.MachineTypeRecommender` - Instance group sizing

### Cloud SQL
- `google.cloudsql.instance.IdleRecommender` - Identify idle Cloud SQL instances
- `google.cloudsql.instance.OverprovisionedRecommender` - Right-size Cloud SQL instances
- `google.cloudsql.instance.OutOfDiskRecommender` - Disk space recommendations

### IAM & Resource Management
- `google.iam.policy.Recommender` - IAM policy recommendations
- `google.resourcemanager.projectUtilization.Recommender` - Project utilization

### BigQuery
- `google.bigquery.capacityCommitments.Recommender` - Capacity commitment recommendations
- `google.bigquery.table.PartitionClusterRecommender` - Table optimization

### Storage & Databases
- `google.storage.bucket.LifecycleRecommender` - Cloud Storage lifecycle management
- `google.spanner.instance.IdleRecommender` - Idle Spanner instances
- `google.firestore.index.Recommender` - Firestore index recommendations

### Containers & Serverless
- `google.container.DiagnosisRecommender` - GKE diagnostics
- `google.run.service.CostRecommender` - Cloud Run cost optimization
- `google.run.service.IdentityRecommender` - Cloud Run identity recommendations
- `google.cloudfunctions.PerformanceRecommender` - Cloud Functions performance
- `google.appengine.applicationIdleRecommender` - App Engine idle apps

### Monitoring & Logging
- `google.monitoring.productSuggestion.ComputeRecommender` - Monitoring suggestions
- `google.logging.productSuggestion.ContainerRecommender` - Logging suggestions

### Filtering Specific Types

If you want to collect only specific recommender types, set the `RECOMMENDER_TYPES` environment variable:

```bash
# Example: Only collect Compute Engine and Cloud SQL recommendations
RECOMMENDER_TYPES=google.compute.instance.MachineTypeRecommender,google.cloudsql.instance.IdleRecommender
```

**Recommendation**: Leave `RECOMMENDER_TYPES` empty to collect all types and let your application filter what's relevant.

## Running at Different Scopes

The job can run at three different scope levels:

### 1. Project Level (Default)

Collect recommendations for a single project:

```bash
SCOPE_TYPE=project
SCOPE_ID=my-project-id
```

### 2. Folder Level

Collect recommendations for all projects within a folder:

```bash
SCOPE_TYPE=folder
SCOPE_ID=123456789  # or folders/123456789
```

**Required Permissions**:
- `resourcemanager.projects.list` on the folder
- `recommender.*.list` and `recommender.*.get` on all projects in the folder

### 3. Organization Level

Collect recommendations for all projects within an organization:

```bash
SCOPE_TYPE=organization
SCOPE_ID=987654321  # or organizations/987654321
```

**Required Permissions**:
- `resourcemanager.projects.list` on the organization
- `recommender.*.list` and `recommender.*.get` on all projects in the organization

### Finding Your Folder or Organization ID

```bash
# List folders
gcloud resource-manager folders list --organization=YOUR_ORG_ID

# Get organization ID
gcloud organizations list

# List projects in a folder
gcloud projects list --filter="parent.id=FOLDER_ID"
```

## Firestore Document Structure

Each recommendation is stored as a Firestore document with the following fields:

```
- recommendation_id (STRING) - Document ID
- recommendation_name (STRING)
- project_id (STRING)
- project_number (STRING)
- location (STRING)
- recommender_type (STRING)
- recommender_subtype (STRING)
- description (STRING)
- state (STRING)
- priority (STRING)
- last_refresh_time (STRING/ISO 8601)
- primary_impact_category (STRING)
- primary_impact_cost_projection (NUMBER) - Estimated cost savings
- primary_impact_currency (STRING)
- primary_impact_duration (STRING)
- target_resources (STRING) - JSON array of affected resources
- operation_groups (STRING) - JSON array of recommended operations
- associated_insights (STRING) - JSON array of related insights
- etag (STRING)
- xor_group_id (STRING)
- content (STRING)
- collected_at (STRING/ISO 8601)
```

## Deployment

### 1. Configure Environment

Copy the appropriate `.env` file and update with your values:

```bash
cd cost-recommendation

# For development
cp .env.example .env.dev
# Edit .env.dev with your development project settings

# For production
cp .env.example .env.prd
# Edit .env.prd with your production project settings
```

### 2. Build and Push Docker Image

**Note**: Use the common Dockerfile in the root directory with the `JOB_NAME` build argument.

```bash
# Navigate to the root directory
cd ..

# Set your project ID
export PROJECT_ID=your-project-id
export ENVIRONMENT=prd  # or dev, uat

# Build the image using the common Dockerfile
docker build --build-arg JOB_NAME=cost-recommendation -t gcr.io/${PROJECT_ID}/cost-recommendation-collector:latest .

# Push to Google Container Registry
docker push gcr.io/${PROJECT_ID}/cost-recommendation-collector:latest
```

### 3. Deploy as Cloud Run Job

```bash
gcloud run jobs create cost-recommendation-collector \
  --image gcr.io/${PROJECT_ID}/cost-recommendation-collector:latest \
  --region us-central1 \
  --service-account recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=${ENVIRONMENT} \
  --set-env-vars GCP_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars SCOPE_TYPE=project \
  --set-env-vars SCOPE_ID=${PROJECT_ID} \
  --set-env-vars FIRESTORE_DATABASE="(default)" \
  --set-env-vars FIRESTORE_COLLECTION=cost_recommendations \
  --max-retries 3 \
  --task-timeout 30m
```

**For Folder Level**:
```bash
gcloud run jobs create cost-recommendation-collector \
  --image gcr.io/${PROJECT_ID}/cost-recommendation-collector:latest \
  --region us-central1 \
  --service-account recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=${ENVIRONMENT} \
  --set-env-vars GCP_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars SCOPE_TYPE=folder \
  --set-env-vars SCOPE_ID=YOUR_FOLDER_ID \
  --set-env-vars FIRESTORE_DATABASE="(default)" \
  --set-env-vars FIRESTORE_COLLECTION=cost_recommendations \
  --max-retries 3 \
  --task-timeout 60m
```

**For Organization Level**:
```bash
gcloud run jobs create cost-recommendation-collector \
  --image gcr.io/${PROJECT_ID}/cost-recommendation-collector:latest \
  --region us-central1 \
  --service-account recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com \
  --set-env-vars ENVIRONMENT=${ENVIRONMENT} \
  --set-env-vars GCP_PROJECT_ID=${PROJECT_ID} \
  --set-env-vars SCOPE_TYPE=organization \
  --set-env-vars SCOPE_ID=YOUR_ORG_ID \
  --set-env-vars FIRESTORE_DATABASE="(default)" \
  --set-env-vars FIRESTORE_COLLECTION=cost_recommendations \
  --max-retries 3 \
  --task-timeout 120m
```

### 4. Schedule with Cloud Scheduler

```bash
# Create a schedule to run daily at 2 AM UTC
gcloud scheduler jobs create http cost-recommendation-collector-daily \
  --location us-central1 \
  --schedule "0 2 * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/cost-recommendation-collector:run" \
  --http-method POST \
  --oauth-service-account-email recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com
```

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment
export ENVIRONMENT=dev

# Run locally (requires Application Default Credentials)
python main.py
```

## Service Account Setup

Create a service account with necessary permissions:

```bash
# Create service account
gcloud iam service-accounts create recommendation-collector \
  --display-name "Cost Recommendation Collector"

# Grant recommender viewer role at organization level
gcloud organizations add-iam-policy-binding YOUR_ORG_ID \
  --member="serviceAccount:recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/recommender.viewer"

# Grant project viewer role to list projects (for folder/org level)
gcloud organizations add-iam-policy-binding YOUR_ORG_ID \
  --member="serviceAccount:recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/browser"

# For folder level, grant permissions on the folder
gcloud resource-manager folders add-iam-policy-binding YOUR_FOLDER_ID \
  --member="serviceAccount:recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/browser"

# Grant Firestore permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:recommendation-collector@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
```

**Note**: For folder or organization level collection, the service account needs permissions on all projects within that scope.

## Monitoring

View job execution logs:

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=cost-recommendation-collector" \
  --limit 50 \
  --format json
```

## Querying Recommendations

Example Firestore queries using the Python client:

```python
from google.cloud import firestore

db = firestore.Client()
collection_ref = db.collection('cost_recommendations')

# Get all active recommendations
active_recommendations = collection_ref.where('state', '==', 'ACTIVE').stream()
for doc in active_recommendations:
    print(f'{doc.id}: {doc.to_dict()}')

# Get recommendations for a specific project
project_recommendations = collection_ref.where('project_id', '==', 'your-project-id').stream()

# Get recommendations with cost savings (negative impact)
# Note: Firestore doesn't support < operator directly, so filter in code
all_docs = collection_ref.where('state', '==', 'ACTIVE').stream()
savings_recommendations = [
    doc.to_dict() for doc in all_docs 
    if doc.to_dict().get('primary_impact_cost_projection', 0) < 0
]

# Get recommendations by type
compute_recommendations = collection_ref.where(
    'recommender_type', '==', 'google.compute.instance.MachineTypeRecommender'
).stream()

# Get high priority recommendations
high_priority = collection_ref.where('priority', 'in', ['P1', 'P2']).stream()
```

You can also query Firestore from the GCP Console or use the REST API for more complex queries.

## Troubleshooting

### No projects found
- Verify the service account has `resourcemanager.projects.list` permission
- Check that projects are in ACTIVE state
- The job will fall back to the configured project if listing fails

### Permission denied for recommender API
- Verify the service account has `recommender.*.list` and `recommender.*.get` permissions
- Ensure the Recommender API is enabled in all projects
- Check organization-level policies

### No recommendations found
- Some recommender types may not be available in all locations
- Recommendations may not exist if resources are already optimized
- Check the state filter - try removing it to see all recommendations

### Firestore write errors
- Verify service account has `datastore.user` role or equivalent permissions
- Check that Firestore is enabled in your project
- Ensure the Firestore database exists
- Verify the collection name is correct

## Notes

- **Comprehensive Collection**: By default, the job checks 30+ recommender types across all GCP regions
- **All Regions Covered**: Checks global and 25+ regional locations (Americas, Europe, Asia Pacific, Australia, Middle East)
- **Efficient Processing**: Not all recommender types are available in all locations - the job handles this gracefully
- **Idempotent**: Documents are stored with `recommendation_id` as the document ID for idempotency
- **Batch Operations**: Firestore batch operations are used for efficient writes (500 documents per batch)
- **Auto-Retry**: Failed jobs will retry up to 3 times automatically
- **Cost Savings**: Cost projections are negative for savings (e.g., -100 means $100 in savings)
- **Mutual Exclusivity**: Some recommendations may be mutually exclusive (indicated by `xor_group_id`)
- **Upsert Behavior**: Re-running the job will update existing recommendations
- **Application Filtering**: The job collects ALL recommendations; your application decides which are valid/relevant

## Integration with Cost Analysis

This job is designed to work alongside the `cost-cron` job to provide a complete cost management solution:

1. **cost-cron**: Collects actual cost data from billing exports
2. **cost-recommendation**: Collects optimization recommendations

Together, they enable:
- Tracking actual costs vs. potential savings
- Identifying optimization opportunities
- Monitoring recommendation adoption
- Calculating ROI of cost optimization efforts
