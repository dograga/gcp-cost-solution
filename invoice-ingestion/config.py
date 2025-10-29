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

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', 'cost-db')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'invoices')

# Invoice Processing Configuration
MONTHS_BACK = int(os.environ.get('MONTHS_BACK', '12'))

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'billing_account_ids': BILLING_ACCOUNT_LIST,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection': FIRESTORE_COLLECTION,
    'months_back': MONTHS_BACK,
    'log_level': LOG_LEVEL,
}
