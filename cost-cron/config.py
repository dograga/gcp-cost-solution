"""
Configuration module for cost-cron job.
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

# BigQuery Configuration
BQ_DATASET_ID = os.environ.get('BQ_DATASET_ID', 'billing_data')
BQ_TABLE_ID = os.environ.get('BQ_TABLE_ID', 'daily_costs')
BQ_LOCATION = os.environ.get('BQ_LOCATION', 'US')

# Billing Export Configuration (if using billing export tables)
BILLING_EXPORT_DATASET = os.environ.get('BILLING_EXPORT_DATASET', 'billing_data')
BILLING_EXPORT_TABLE_PREFIX = os.environ.get('BILLING_EXPORT_TABLE_PREFIX', 'gcp_billing_export')

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'bq_dataset_id': BQ_DATASET_ID,
    'bq_table_id': BQ_TABLE_ID,
    'bq_location': BQ_LOCATION,
    'billing_export_dataset': BILLING_EXPORT_DATASET,
    'billing_export_table_prefix': BILLING_EXPORT_TABLE_PREFIX,
    'log_level': LOG_LEVEL,
}
