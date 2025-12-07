# IAM Permissions for Invoice Ingestion

This document outlines the Identity and Access Management (IAM) permissions required for the Invoice Ingestion service to function correctly.

## Service Account

It is recommended to create a dedicated Service Account for this application, for example:
`invoice-ingestion-sa@<PROJECT_ID>.iam.gserviceaccount.com`

## Required Roles & Permissions

The service account requires permissions to access Cloud Billing data and write to Firestore.

### 1. Cloud Billing Access

**Role:** `roles/billing.viewer` (Billing Account Viewer)

**Scope:**
*   **Organization Level:** Recommended if you want the service to automatically discover all open billing accounts in the organization.
*   **Billing Account Level:** If you prefer to restrict access to specific billing accounts, grant this role on each target Billing Account.

**Reason:**
*   Required to list billing accounts (`billing.accounts.list`).
*   Required to view invoices and their details (`billing.invoices.list`).

### 2. Firestore Access

**Role:** `roles/datastore.user` (Cloud Datastore User)

**Scope:**
*   **Project Level:** The project where the Firestore database is hosted (defined by `GCP_PROJECT_ID` in configuration).

**Reason:**
*   Required to read and write data to the Firestore database (`datastore.entities.create`, `datastore.entities.update`, `datastore.entities.get`).

### 3. Cloud Logging (Standard)

**Role:** `roles/logging.logWriter` (Logs Writer)

**Scope:**
*   **Project Level:** The project where the application is running.

**Reason:**
*   Required to write application logs to Cloud Logging.

## Summary Table

| Component | Role | Scope | Purpose |
|-----------|------|-------|---------|
| **Cloud Billing** | `roles/billing.viewer` | Organization or Billing Account | Fetch monthly invoices |
| **Firestore** | `roles/datastore.user` | Project (Firestore) | Store invoice data |
| **Logging** | `roles/logging.logWriter` | Project (App) | Write application logs |

## Deployment Note

When deploying to **Cloud Run Jobs**, ensure you attach this service account to the job:

```bash
gcloud run jobs create invoice-ingestion \
  --image <IMAGE_URL> \
  --service-account invoice-ingestion-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  ...
```
