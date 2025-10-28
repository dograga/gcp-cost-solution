"""
Configuration module for cost-anomalies-handler.
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

# Firestore Configuration
FIRESTORE_DATABASE = os.environ.get('FIRESTORE_DATABASE', 'cost-db')
FIRESTORE_COLLECTION = os.environ.get('FIRESTORE_COLLECTION', 'cost_anomalies')

# Project Enrichment Configuration
ENRICHMENT_DATABASE = os.environ.get('ENRICHMENT_DATABASE', 'dashboard')
ENRICHMENT_COLLECTION = os.environ.get('ENRICHMENT_COLLECTION', 'projects')
ENRICHMENT_PROJECT_ID_FIELD = os.environ.get('ENRICHMENT_PROJECT_ID_FIELD', 'project_id')
ENRICHMENT_FIELDS = os.environ.get('ENRICHMENT_FIELDS', 'appcode,lob')
ENRICHMENT_FIELD_LIST = [field.strip() for field in ENRICHMENT_FIELDS.split(',') if field.strip()]

# Logging Configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Configuration summary
CONFIG = {
    'environment': ENVIRONMENT,
    'gcp_project_id': GCP_PROJECT_ID,
    'firestore_database': FIRESTORE_DATABASE,
    'firestore_collection': FIRESTORE_COLLECTION,
    'enrichment_database': ENRICHMENT_DATABASE,
    'enrichment_collection': ENRICHMENT_COLLECTION,
    'enrichment_project_id_field': ENRICHMENT_PROJECT_ID_FIELD,
    'enrichment_fields': ENRICHMENT_FIELD_LIST,
    'log_level': LOG_LEVEL,
}
