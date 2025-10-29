"""
Configuration module for invoice-ingestion job.
Loads environment-specific settings from .env files.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Determine environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Load environment-specific .env file
env_file = Path(__file__).parent / f'.env.{ENVIRONMENT}'
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded configuration from {env_file}")
else:
    print(f"Warning: {env_file} not found, using environment variables or defaults")

# GCP Project Configuration
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
if not GCP_PROJECT_ID:
    raise ValueError(f"GCP_PROJECT_ID must be set in .env.{ENVIRONMENT} or environment variables")

# Billing Account Configuration
BILLING_ACCOUNT_IDS = os.environ.get('BILLING_ACCOUNT_IDS', '')
BILLING_ACCOUNT_LIST = [acc.strip() for acc in BILLING_ACCOUNT_IDS.split(',') if acc.strip()] if BILLING_ACCOUNT_IDS else []

# BigQuery Billing Export Configuration
BILLING_DATASET = os.environ.get('BILLING_DATASET', 'billing_export')
BILLING_TABLE_PREFIX = os.environ.get('BILLING_TABLE_PREFIX', 'gcp_billing_export_v1')

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', 'cost-db')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'invoices')

# Project Enrichment Configuration
ENRICHMENT_DATABASE = os.environ.get('ENRICHMENT_DATABASE', 'dashboard')
ENRICHMENT_COLLECTION = os.environ.get('ENRICHMENT_COLLECTION', 'projects')
ENRICHMENT_PROJECT_ID_FIELD = os.environ.get('ENRICHMENT_PROJECT_ID_FIELD', 'project_id')
ENRICHMENT_FIELDS = os.environ.get('ENRICHMENT_FIELDS', 'appcode,lob')
ENRICHMENT_FIELD_LIST = [field.strip() for field in ENRICHMENT_FIELDS.split(',') if field.strip()]

# Invoice Processing Configuration
MONTHS_BACK = int(os.environ.get('MONTHS_BACK', '12'))
INCLUDE_LINE_ITEMS = os.environ.get('INCLUDE_LINE_ITEMS', 'True').lower() in ('true', '1', 'yes')

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'billing_account_ids': BILLING_ACCOUNT_LIST,
    'billing_dataset': BILLING_DATASET,
    'billing_table_prefix': BILLING_TABLE_PREFIX,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection': FIRESTORE_COLLECTION,
    'enrichment_database': ENRICHMENT_DATABASE,
    'enrichment_collection': ENRICHMENT_COLLECTION,
    'enrichment_project_id_field': ENRICHMENT_PROJECT_ID_FIELD,
    'enrichment_fields': ENRICHMENT_FIELD_LIST,
    'months_back': MONTHS_BACK,
    'include_line_items': INCLUDE_LINE_ITEMS,
    'log_level': LOG_LEVEL,
}
