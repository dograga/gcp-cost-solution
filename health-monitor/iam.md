# IAM Permissions for Health Monitor

This document outlines the Identity and Access Management (IAM) permissions required for the Health Monitor service to function correctly.

## Service Account

It is recommended to create a dedicated Service Account for this application, for example:
`health-monitor-sa@<PROJECT_ID>.iam.gserviceaccount.com`

## Required Roles & Permissions

The service account requires permissions to access Service Health events at the organization level and write to Firestore.

### 1. Service Health Access

**Role:** `roles/servicehealth.viewer` (Service Health Viewer)

**Scope:**
*   **Organization Level:** REQUIRED. The application fetches events for the entire organization (`organizations/{org_id}/locations/global`).

**Reason:**
*   Required to list organization events (`servicehealth.organizationEvents.list`).
*   Required to view event details (`servicehealth.organizationEvents.get`).

### 2. Firestore Access

**Role:** `roles/datastore.user` (Cloud Datastore User)

**Scope:**
*   **Project Level:** The project where the Firestore database is hosted (defined by `GCP_PROJECT_ID` in configuration).

**Reason:**
*   Required to read and write data to the Firestore database (`datastore.entities.create`, `datastore.entities.update`, `datastore.entities.delete`, `datastore.entities.list`).

### 3. Cloud Logging (Standard)

**Role:** `roles/logging.logWriter` (Logs Writer)

**Scope:**
*   **Project Level:** The project where the application is running.

**Reason:**
*   Required to write application logs to Cloud Logging.

## Summary Table

| Component | Role | Scope | Purpose |
|-----------|------|-------|---------|
| **Service Health** | `roles/servicehealth.viewer` | **Organization** | Fetch organization-wide health events |
| **Firestore** | `roles/datastore.user` | Project (Firestore) | Store event and region status data |
| **Logging** | `roles/logging.logWriter` | Project (App) | Write application logs |

## Deployment Note

When deploying to **Cloud Run Jobs**, ensure you attach this service account to the job:

```bash
gcloud run jobs create health-monitor \
  --image <IMAGE_URL> \
  --service-account health-monitor-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  ...
```

### Important: Organization Level Permissions
Unlike project-level permissions, the `roles/servicehealth.viewer` role **MUST** be granted at the Organization level. You can do this via the Cloud Console (IAM & Admin > IAM > Switch to Organization view) or using `gcloud`:

```bash
gcloud organizations add-iam-policy-binding <ORGANIZATION_ID> \
    --member="serviceAccount:health-monitor-sa@<PROJECT_ID>.iam.gserviceaccount.com" \
    --role="roles/servicehealth.viewer"
```
