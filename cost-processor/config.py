"""
Configuration module for cost-processor job.
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

# BigQuery Configuration (Source)
SOURCE_DATASET_ID = os.environ.get('SOURCE_DATASET_ID', 'billing_data')
SOURCE_TABLE_ID = os.environ.get('SOURCE_TABLE_ID', 'daily_costs')
OUTPUT_DATASET_ID = os.environ.get('OUTPUT_DATASET_ID', 'billing_reports')
BQ_LOCATION = os.environ.get('BQ_LOCATION', 'US')

# Firestore Configuration
FIRESTORE_PROJECT_ID = os.environ.get('FIRESTORE_PROJECT_ID', GCP_PROJECT_ID)
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', '(default)')
FIRESTORE_COLLECTION_PREFIX = os.environ.get('FIRESTORE_COLLECTION_PREFIX', 'cost_reports')

# Processing Configuration
DAYS_BACK = int(os.environ.get('DAYS_BACK', '30'))
TOP_COST_DRIVERS_COUNT = int(os.environ.get('TOP_COST_DRIVERS_COUNT', '20'))
TOP_COST_DRIVERS_DAYS = int(os.environ.get('TOP_COST_DRIVERS_DAYS', '7'))

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'source_dataset_id': SOURCE_DATASET_ID,
    'source_table_id': SOURCE_TABLE_ID,
    'output_dataset_id': OUTPUT_DATASET_ID,
    'bq_location': BQ_LOCATION,
    'firestore_project_id': FIRESTORE_PROJECT_ID,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection_prefix': FIRESTORE_COLLECTION_PREFIX,
    'days_back': DAYS_BACK,
    'top_cost_drivers_count': TOP_COST_DRIVERS_COUNT,
    'top_cost_drivers_days': TOP_COST_DRIVERS_DAYS,
    'log_level': LOG_LEVEL,
}
